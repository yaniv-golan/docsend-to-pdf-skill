from __future__ import annotations

import base64
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import click
import requests

from docsend_to_pdf.__init__ import __version__
from docsend_to_pdf.client import (
    accept_nda,
    download_image,
    fetch_page,
    fetch_page_data,
    is_video_document,
    parse_page_response,
    submit_email,
    submit_verification,
)
from docsend_to_pdf.pdf_builder import build_pdf, process_image
from docsend_to_pdf.types import GateKind, is_short_url, parse_url

MAX_GATE_TRANSITIONS = 4


# ---------------------------------------------------------------------------
# Session serialization
# ---------------------------------------------------------------------------

def serialize_session(state: dict, state_file: Optional[str] = None) -> str:
    """Base64-encode state dict. Optionally write JSON to state_file.

    Returns the base64 blob string.
    """
    json_bytes = json.dumps(state).encode("utf-8")
    blob = base64.b64encode(json_bytes).decode("ascii")
    if state_file is not None:
        Path(state_file).write_text(json.dumps(state, indent=2))
    return blob


def deserialize_session(blob: Optional[str] = None, state_file: Optional[str] = None) -> dict:
    """Decode state from blob or read from file.

    Raises ValueError if neither source is provided.
    Raises FileNotFoundError if state_file does not exist.
    """
    if blob is None and state_file is None:
        raise ValueError("Must provide either blob or state_file")
    if state_file is not None:
        p = Path(state_file)
        if not p.exists():
            raise FileNotFoundError(f"State file not found: {state_file}")
        return json.loads(p.read_text())
    # blob path
    json_bytes = base64.b64decode(blob)
    return json.loads(json_bytes)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_output(**kwargs) -> str:
    """Return JSON string, stripping None values."""
    payload = {k: v for k, v in kwargs.items() if v is not None}
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_filename(title: str) -> str:
    """Convert a title string to a safe filename component."""
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"[\s]+", "-", safe.strip())
    return safe.lower() or "document"


def _build_session_state(
    url: str,
    session: requests.Session,
    csrf_token: str,
    gates_cleared: list,
    pending_gate: str,
    email: str,
) -> dict:
    """Build a serializable state dict from session components."""
    return {
        "url": url,
        "cookies": dict(session.cookies),
        "csrf_token": csrf_token,
        "gates_cleared": gates_cleared,
        "pending_gate": pending_gate,
        "email": email,
    }


def _restore_session(state: dict) -> requests.Session:
    """Create a requests.Session with cookies and browser-like headers restored from state."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    for name, value in state.get("cookies", {}).items():
        sess.cookies.set(name, value)
    return sess


def _extract_csrf_from_result(result, fallback: str) -> str:
    """Extract CSRF token from an Authenticated or NeedsInput result, falling back if empty."""
    token = getattr(result, "csrf_token", "")
    return token if token else fallback


# ---------------------------------------------------------------------------
# Gate state machine
# ---------------------------------------------------------------------------

def _run_conversion(
    url: str,
    email: Optional[str],
    passcode: Optional[str],
    verification_code: Optional[str],
    accept_nda_flag: bool,
    output_path: Optional[str],
    json_mode: bool,
    quiet: bool,
    session_blob: Optional[str],
    state_file: Optional[str],
) -> int:
    """Run the full conversion flow. Returns exit code (0 = success, 1 = error, 2 = needs input)."""

    def _progress(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr)

    def _output(msg: str) -> None:
        print(msg)

    # -----------------------------------------------------------------------
    # Restore or create session
    # -----------------------------------------------------------------------
    gates_cleared: list = []
    csrf_token = ""
    current_email = email or ""

    if session_blob or state_file:
        try:
            state = deserialize_session(blob=session_blob, state_file=state_file)
        except (FileNotFoundError, ValueError) as exc:
            if json_mode:
                _output(format_output(status="error", message=str(exc)))
            else:
                print(f"Error: {exc}", file=sys.stderr)
            return 1
        url = state.get("url", url)
        gates_cleared = state.get("gates_cleared", [])
        csrf_token = state.get("csrf_token", "")
        current_email = email or state.get("email", "")
        http_session = _restore_session(state)
        _progress(f"Resuming session for {url}")
    else:
        http_session = requests.Session()
        http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    # Resolve /v/ short URLs by following the redirect to /view/
    if is_short_url(url):
        _progress(f"Resolving short URL: {url}")
        try:
            resp = http_session.get(url, allow_redirects=True, timeout=15)
            if resp.status_code == 404:
                msg = "Link not found or expired"
                if json_mode:
                    _output(format_output(status="error", message=msg))
                else:
                    print(f"Error: {msg}", file=sys.stderr)
                return 1
            if resp.url and "/view/" in resp.url:
                url = resp.url
                _progress(f"Resolved to: {url}")
        except requests.RequestException:
            pass  # Fall through — parse_url will try with the original

    # Parse and normalize the URL
    try:
        parsed = parse_url(url)
    except ValueError as exc:
        if json_mode:
            _output(format_output(status="error", message=str(exc)))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    norm_url = parsed.normalized
    doc_id = parsed.doc_id

    # -----------------------------------------------------------------------
    # Fetch initial page
    # -----------------------------------------------------------------------
    _progress(f"Fetching {norm_url} ...")
    try:
        page_resp = fetch_page(http_session, norm_url)
    except requests.RequestException as exc:
        if json_mode:
            _output(format_output(status="error", message=str(exc)))
        else:
            print(f"Network error: {exc}", file=sys.stderr)
        return 1

    csrf_token = page_resp.csrf_token or csrf_token
    title = page_resp.title
    gate = page_resp.gate

    # -----------------------------------------------------------------------
    # Gate state machine
    # -----------------------------------------------------------------------
    for _transition in range(MAX_GATE_TRANSITIONS):
        kind = gate.kind

        if kind == GateKind.NONE:
            # Authenticated — break to download
            break

        if kind == GateKind.REJECTED:
            msg = gate.text or "Access denied"
            if json_mode:
                _output(format_output(status="error", message=msg))
            else:
                print(f"Error: {msg}", file=sys.stderr)
            return 1

        if kind in (GateKind.EMAIL, GateKind.PASSCODE):
            if not current_email:
                # Need email from user — emit needs_email and pause
                state = _build_session_state(
                    norm_url, http_session, csrf_token, gates_cleared, "email", current_email
                )
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    kwargs: dict = {"status": "needs_email"}
                    if state_file:
                        kwargs["state_file"] = state_file
                    else:
                        kwargs["session"] = blob
                    _output(format_output(**kwargs))
                else:
                    print("Email required. Re-run with --email <address>", file=sys.stderr)
                return 2

            _progress(f"Submitting email: {current_email}")
            try:
                _html, gate_result = submit_email(
                    http_session,
                    norm_url,
                    csrf_token,
                    current_email,
                    passcode=passcode,
                )
            except requests.RequestException as exc:
                if json_mode:
                    _output(format_output(status="error", message=str(exc)))
                else:
                    print(f"Network error: {exc}", file=sys.stderr)
                return 1

            csrf_token = _extract_csrf_from_result(gate_result, csrf_token)
            gates_cleared.append("email")

            from docsend_to_pdf.types import Authenticated, NeedsInput
            if isinstance(gate_result, Authenticated):
                gate_result_as_page_count = gate_result.page_count
                gate = type("_FakeGate", (), {"kind": GateKind.NONE})()
                # Store page_count from authenticated result
                _authenticated_page_count = gate_result.page_count
                break
            else:
                gate = gate_result.gate
            continue

        if kind == GateKind.NDA:
            if not accept_nda_flag:
                state = _build_session_state(
                    norm_url, http_session, csrf_token, gates_cleared, "nda", current_email
                )
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    kwargs = {"status": "needs_nda", "nda_text": gate.text}
                    if state_file:
                        kwargs["state_file"] = state_file
                    else:
                        kwargs["session"] = blob
                    _output(format_output(**kwargs))
                else:
                    print("NDA acceptance required. Re-run with --accept-nda", file=sys.stderr)
                return 2

            _progress("Accepting NDA ...")
            try:
                _html, gate_result = accept_nda(http_session, norm_url, csrf_token)
            except requests.RequestException as exc:
                if json_mode:
                    _output(format_output(status="error", message=str(exc)))
                else:
                    print(f"Network error: {exc}", file=sys.stderr)
                return 1

            csrf_token = _extract_csrf_from_result(gate_result, csrf_token)
            gates_cleared.append("nda")

            from docsend_to_pdf.types import Authenticated as _Auth2, NeedsInput as _NI2
            if isinstance(gate_result, _Auth2):
                _authenticated_page_count = gate_result.page_count
                gate = type("_FakeGate", (), {"kind": GateKind.NONE})()
                break
            else:
                gate = gate_result.gate
            continue

        if kind == GateKind.VERIFICATION:
            if not verification_code:
                target_email = gate.text or current_email
                state = _build_session_state(
                    norm_url, http_session, csrf_token, gates_cleared, "verification", current_email
                )
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    kwargs = {"status": "needs_verification", "email": target_email}
                    if state_file:
                        kwargs["state_file"] = state_file
                    else:
                        kwargs["session"] = blob
                    _output(format_output(**kwargs))
                else:
                    hint = f" (sent to {target_email})" if target_email else ""
                    print(
                        f"Verification code required{hint}. Re-run with --verification-code <code>",
                        file=sys.stderr,
                    )
                return 2

            _progress("Submitting verification code ...")
            try:
                _html, gate_result = submit_verification(
                    http_session, norm_url, csrf_token, verification_code
                )
            except requests.RequestException as exc:
                if json_mode:
                    _output(format_output(status="error", message=str(exc)))
                else:
                    print(f"Network error: {exc}", file=sys.stderr)
                return 1

            csrf_token = _extract_csrf_from_result(gate_result, csrf_token)
            gates_cleared.append("verification")

            from docsend_to_pdf.types import Authenticated as _Auth3, NeedsInput as _NI3
            if isinstance(gate_result, _Auth3):
                _authenticated_page_count = gate_result.page_count
                gate = type("_FakeGate", (), {"kind": GateKind.NONE})()
                break
            else:
                gate = gate_result.gate
            continue

        # Unknown gate kind — bail
        _progress(f"Unknown gate: {kind}")
        break

    # After the loop, check if we're still gated
    if gate.kind != GateKind.NONE:
        msg = f"Could not clear gate after {MAX_GATE_TRANSITIONS} transitions"
        if json_mode:
            _output(format_output(status="error", message=msg))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # Check for video documents (not convertible to PDF)
    # -----------------------------------------------------------------------
    try:
        auth_resp = http_session.get(norm_url, timeout=30)
        if is_video_document(auth_resp.text):
            msg = "This is a video document, not a slide deck. Video documents cannot be converted to PDF."
            if json_mode:
                _output(format_output(status="error", message=msg))
            else:
                print(f"Error: {msg}", file=sys.stderr)
            return 1
        # Update page count from fresh authenticated page
        fresh_resp = parse_page_response(auth_resp.text)
        if fresh_resp.page_count:
            page_resp = fresh_resp
    except requests.RequestException:
        pass  # Non-critical — proceed with existing data

    # -----------------------------------------------------------------------
    # Determine page count
    # -----------------------------------------------------------------------
    page_count = page_resp.page_count
    if not page_count:
        # Try from Authenticated result during gate clearing
        try:
            page_count = _authenticated_page_count  # type: ignore[name-defined]
        except NameError:
            pass

    if not page_count:
        # Fallback: probe page_data endpoints until we get a non-200
        _progress("Probing page count...")
        for i in range(1, 500):
            try:
                pd = fetch_page_data(http_session, norm_url, i)
                if pd is None:
                    break
                page_count = i
            except Exception:
                break

    if not page_count:
        msg = "Could not determine page count"
        if json_mode:
            _output(format_output(status="error", message=msg))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    if page_count:
        _progress(f"Downloading {page_count} pages ...")
    else:
        _progress("Downloading pages ...")

    # -----------------------------------------------------------------------
    # Fetch page data — discover all pages via page_data endpoint
    # -----------------------------------------------------------------------
    page_data_map: dict[int, str] = {}

    if page_count and page_count > 1:
        # Trusted page count — fetch all in parallel
        def _fetch_one(n: int) -> tuple[int, Optional[str]]:
            try:
                pd = fetch_page_data(http_session, norm_url, n)
                return n, (pd.image_url if pd else None)
            except Exception:
                return n, None

        with ThreadPoolExecutor(max_workers=4) as executor:
            for num, img_url in executor.map(_fetch_one, range(1, page_count + 1)):
                if img_url:
                    page_data_map[num] = img_url
    else:
        # Unknown or suspicious page count — probe sequentially
        _progress("Probing page count...")
        for n in range(1, 500):
            try:
                pd = fetch_page_data(http_session, norm_url, n)
                if pd is None:
                    break
                page_data_map[n] = pd.image_url
            except Exception:
                break

    page_count = len(page_data_map)

    if not page_data_map:
        msg = "Failed to fetch any page data"
        if json_mode:
            _output(format_output(status="error", message=msg))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    # Download image bytes in parallel
    image_bytes_map: dict[int, bytes] = {}

    def _download_one(page_num: int, img_url: str) -> tuple[int, Optional[bytes]]:
        try:
            return page_num, download_image(http_session, img_url)
        except Exception:
            return page_num, None

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures2 = {
            executor.submit(_download_one, n, u): n for n, u in page_data_map.items()
        }
        for future in as_completed(futures2):
            num, raw = future.result()
            if raw is not None:
                image_bytes_map[num] = raw

    if not image_bytes_map:
        msg = (
            f"Failed to download page images ({page_count} pages found but all "
            f"returned errors). The document's image CDN may be misconfigured "
            f"or temporarily unavailable."
        )
        if json_mode:
            _output(format_output(status="error", message=msg))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # Build PDF
    # -----------------------------------------------------------------------
    sorted_nums = sorted(image_bytes_map.keys())
    actual_pages = len(sorted_nums)
    images = [process_image(image_bytes_map[n]) for n in sorted_nums]

    # Determine output path
    if not output_path:
        if title:
            safe = _safe_filename(title)
            output_path = f"{safe}.pdf"
        else:
            output_path = f"docsend-{doc_id}.pdf"

    _progress(f"Building PDF: {output_path}")
    try:
        build_pdf(images, output_path)
    except Exception as exc:
        if json_mode:
            _output(format_output(status="error", message=str(exc)))
        else:
            print(f"Error building PDF: {exc}", file=sys.stderr)
        return 1

    # -----------------------------------------------------------------------
    # Success output
    # -----------------------------------------------------------------------
    if json_mode:
        _output(
            format_output(
                status="complete",
                output=output_path,
                pages=actual_pages,
                title=title,
            )
        )
    else:
        _progress(f"Done! Saved {actual_pages} pages to {output_path}")
        if not quiet:
            print(output_path)

    return 0


# ---------------------------------------------------------------------------
# Click CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.argument("url", required=False)
@click.option("--email", default=None, help="Email address for authentication gate")
@click.option("--passcode", default=None, help="Passcode for passcode gate")
@click.option("--verification-code", default=None, help="Verification code from email")
@click.option("--accept-nda", "accept_nda_flag", is_flag=True, help="Accept NDA automatically")
@click.option("--session", "session_blob", default=None, help="Base64 session blob from prior run")
@click.option("--state-file", default=None, help="Path to state file from prior run")
@click.option("-o", "--output", "output_path", default=None, help="Output PDF path")
@click.option("--json", "json_mode", is_flag=True, help="Emit JSON output")
@click.option("--quiet", is_flag=True, help="Suppress progress messages")
@click.version_option(version=__version__)
def main(
    url: Optional[str],
    email: Optional[str],
    passcode: Optional[str],
    verification_code: Optional[str],
    accept_nda_flag: bool,
    session_blob: Optional[str],
    state_file: Optional[str],
    output_path: Optional[str],
    json_mode: bool,
    quiet: bool,
) -> None:
    """Convert a DocSend link to a PDF file."""
    # URL is required unless resuming with --session or --state-file
    if not url and not session_blob and not state_file:
        raise click.UsageError("URL argument is required unless resuming with --session or --state-file")

    exit_code = _run_conversion(
        url=url or "",
        email=email,
        passcode=passcode,
        verification_code=verification_code,
        accept_nda_flag=accept_nda_flag,
        output_path=output_path,
        json_mode=json_mode,
        quiet=quiet,
        session_blob=session_blob,
        state_file=state_file,
    )
    sys.exit(exit_code)
