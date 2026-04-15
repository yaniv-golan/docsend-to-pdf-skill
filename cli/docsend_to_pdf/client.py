from __future__ import annotations

import re
from typing import Optional, Tuple

import requests

from docsend_to_pdf.types import (
    Authenticated,
    Gate,
    GateKind,
    GateResult,
    NeedsInput,
    PageData,
    PageResponse,
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_csrf_token(html: str) -> str:
    """Extract CSRF token, preferring the meta tag (Rails X-CSRF-Token source).

    DocSend uses Rails CSRF protection. The meta tag csrf-token is the canonical
    source that works with both form body and X-CSRF-Token header. The form's
    authenticity_token may differ and cause 401s when used alone.
    """
    # Prefer meta tag: <meta name="csrf-token" content="...">
    m = re.search(
        r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token["\']',
            html,
        )
    if not m:
        # Fallback to form hidden input
        m = re.search(
            r'name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']',
            html,
        )
    if not m:
        m = re.search(
            r'value=["\']([^"\']+)["\'][^>]+name=["\']authenticity_token["\']',
            html,
        )
    if not m:
        return ""
    return m.group(1)


def _extract_title(html: str) -> Optional[str]:
    """Extract title from <title>, stripping 'DocSend - ' prefix."""
    m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if not m:
        return None
    title = m.group(1).strip()
    prefix = "DocSend - "
    if title.startswith(prefix):
        title = title[len(prefix):]
    return title if title else None


def _extract_page_count(html: str) -> Optional[int]:
    """Extract page count from '.page-label' text like '1 of 12', fallback to data-page-num count."""
    # Try "1 of 12" pattern inside .page-label
    m = re.search(r'class=["\'][^"\']*page-label[^"\']*["\'][^>]*>\s*\d+\s+of\s+(\d+)', html)
    if m:
        return int(m.group(1))
    # Fallback: count data-page-num attributes
    matches = re.findall(r'data-page-num=["\'](\d+)["\']', html)
    if matches:
        return len(matches)
    return None


def _extract_text_from_class(html: str, class_name: str) -> str:
    """Extract text content from an element with the given class name."""
    # Match opening tag with the class, then capture content until </div>
    pattern = rf'class=["\'][^"\']*{re.escape(class_name)}[^"\']*["\'][^>]*>(.*?)</div>'
    m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    # Strip HTML tags from the captured content
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_verification_email(html: str) -> str:
    """Extract the email address shown in the verification gate."""
    m = re.search(r"<strong>([^<@]+@[^<]+)</strong>", html)
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Gate detection
# ---------------------------------------------------------------------------

def detect_gate(html: str) -> Gate:
    """Detect which gate is active by inspecting HTML.

    Priority order:
    1. Rejection (alert_content with "not authorized" or "restricted")
    2. Verification (link_auth_form[verification_code])
    3. NDA (nda-agreement class)
    4. Passcode (link_auth_form[passcode])
    5. Email (link_auth_form[email])
    6. None (authenticated)
    """
    # 1. Rejection
    alert_m = re.search(
        r'class=["\'][^"\']*alert_content[^"\']*["\'][^>]*>(.*?)</div>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if alert_m:
        alert_text = re.sub(r"<[^>]+>", " ", alert_m.group(1)).strip()
        lower = alert_text.lower()
        if "not authorized" in lower or "restricted" in lower:
            return Gate(kind=GateKind.REJECTED, text=alert_text)

    # 2. Verification
    if re.search(r'name=["\']link_auth_form\[verification_code\]["\']', html):
        email = _extract_verification_email(html)
        return Gate(kind=GateKind.VERIFICATION, text=email)

    # 3. NDA
    if re.search(r'class=["\'][^"\']*nda-agreement[^"\']*["\']', html):
        text = _extract_text_from_class(html, "nda-agreement__content")
        return Gate(kind=GateKind.NDA, text=text)

    # 4. Passcode
    if re.search(r'name=["\']link_auth_form\[passcode\]["\']', html):
        return Gate(kind=GateKind.PASSCODE)

    # 5. Email (check for rejection via error class on the email field)
    if re.search(r'name=["\']link_auth_form\[email\]["\']', html):
        # If the email input or its label has class="error", the submitted
        # email was rejected (deliverability check or domain restriction).
        if re.search(
            r'(?:id=["\']link_auth_form_email["\'][^>]*class=["\'][^"\']*error|'
            r'class=["\'][^"\']*error[^"\']*["\'][^>]*id=["\']link_auth_form_email["\'])',
            html,
        ):
            # Extract the error message if available
            err_m = re.search(
                r'<ul[^>]*class=["\'][^"\']*error-message[^"\']*["\'][^>]*>(.*?)</ul>',
                html, re.DOTALL,
            )
            err_text = ""
            if err_m:
                err_text = re.sub(r"<[^>]+>", " ", err_m.group(1)).strip()
            return Gate(kind=GateKind.REJECTED, text=err_text or "Email rejected")
        return Gate(kind=GateKind.EMAIL)

    # 6. Authenticated / None
    return Gate(kind=GateKind.NONE)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_page_response(html: str) -> PageResponse:
    """Parse HTML into a structured PageResponse."""
    gate = detect_gate(html)
    csrf_token = _extract_csrf_token(html)
    title = _extract_title(html)
    # Only extract page count when not gated
    page_count = _extract_page_count(html) if gate.kind == GateKind.NONE else None
    return PageResponse(
        gate=gate,
        csrf_token=csrf_token,
        title=title,
        page_count=page_count,
    )


def _parse_gate_result(html: str) -> Tuple[str, GateResult]:
    """Parse HTML after a form submission into (html, GateResult)."""
    csrf_token = _extract_csrf_token(html)
    gate = detect_gate(html)
    if gate.kind == GateKind.NONE:
        page_count = _extract_page_count(html) or 0
        return html, Authenticated(csrf_token=csrf_token, page_count=page_count)
    return html, NeedsInput(gate=gate)


# ---------------------------------------------------------------------------
# HTTP functions
# ---------------------------------------------------------------------------

def _post_headers(url: str, csrf_token: str) -> dict:
    """Build headers required for DocSend form POSTs (Rails CSRF protection)."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": origin,
        "Referer": url,
    }


def is_video_document(html: str) -> bool:
    """Check if the document is a video (not a slide deck)."""
    return bool(re.search(r'video_player_wrapper|video-player|data-video-url', html))


def fetch_page(session: requests.Session, url: str) -> PageResponse:
    """GET the DocSend view page and return a parsed PageResponse."""
    resp = session.get(url)
    resp.raise_for_status()
    return parse_page_response(resp.text)


def submit_email(
    session: requests.Session,
    url: str,
    csrf_token: str,
    email: str,
    passcode: Optional[str] = None,
) -> Tuple[str, GateResult]:
    """Submit email (and optionally passcode) to authenticate."""
    data: dict = {
        "authenticity_token": csrf_token,
        "_method": "patch",
        "link_auth_form[email]": email,
    }
    if passcode is not None:
        data["link_auth_form[passcode]"] = passcode
    resp = session.post(url, data=data, headers=_post_headers(url, csrf_token))
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def submit_verification(
    session: requests.Session,
    url: str,
    csrf_token: str,
    code: str,
) -> Tuple[str, GateResult]:
    """Submit verification code."""
    data = {
        "authenticity_token": csrf_token,
        "link_auth_form[verification_code]": code,
    }
    resp = session.post(url, data=data, headers=_post_headers(url, csrf_token))
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def accept_nda(
    session: requests.Session,
    url: str,
    csrf_token: str,
) -> Tuple[str, GateResult]:
    """Accept the NDA to proceed."""
    data = {"authenticity_token": csrf_token}
    resp = session.post(url, data=data, headers=_post_headers(url, csrf_token))
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def fetch_page_data(
    session: requests.Session,
    url: str,
    page_num: int,
) -> Optional[PageData]:
    """Fetch page data JSON for a specific page number."""
    page_url = f"{url}/page_data/{page_num}"
    resp = session.get(page_url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    image_url = data.get("imageUrl") or data.get("image_url", "")
    if not image_url:
        return None
    return PageData(image_url=image_url, page_num=page_num)


def download_image(session: requests.Session, image_url: str) -> bytes:
    """Download an image and return raw bytes."""
    resp = session.get(image_url, timeout=60)
    if resp.status_code == 403:
        raise PermissionError(
            f"Access denied downloading page image (CloudFront 403). "
            f"The document's image CDN may be misconfigured or restricted."
        )
    resp.raise_for_status()
    return resp.content
