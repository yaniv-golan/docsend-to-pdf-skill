# DocSend to PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool and Claude Code skill that converts DocSend shared links to PDF files, handling all access gates with a two-phase resumable design.

**Architecture:** Three-layer Python CLI (client → pdf_builder → cli orchestration) wrapped by a Claude Code skill. The CLI communicates via structured JSON on stdout. Gates are navigated as a state machine with session persistence for two-phase resume.

**Tech Stack:** Python 3.9+, requests, Pillow, click. Claude Code skill (SKILL.md + references).

**Spec:** `docs/superpowers/specs/2026-04-15-docsend-to-pdf-design.md`

---

## File Structure

```
cli/
  pyproject.toml                          # Package metadata and dependencies
  docsend_to_pdf/
    __init__.py                           # Version constant
    __main__.py                           # python -m entry point
    types.py                              # All dataclasses and type definitions
    client.py                             # HTTP interaction with DocSend
    pdf_builder.py                        # RGBA→RGB compositing + PDF assembly
    cli.py                                # Click CLI, orchestration, session serialization
  tests/
    conftest.py                           # Shared fixtures
    fixtures/                             # Recorded HTML + JSON responses
      email_gate.html                     # DocSend page with email gate
      passcode_gate.html                  # DocSend page with email+passcode gate
      nda_gate.html                       # DocSend page with NDA gate
      verification_gate.html              # DocSend page with verification gate
      rejected.html                       # DocSend page with allowed-viewers rejection
      authenticated.html                  # DocSend page after successful auth
      page_data_1.json                    # Sample page_data response
    test_types.py                         # URL parsing tests
    test_client.py                        # Gate detection + HTTP interaction tests
    test_pdf_builder.py                   # Image processing + PDF assembly tests
    test_cli.py                           # CLI orchestration + session tests
docsend-to-pdf/                           # Plugin root
  skills/
    docsend-to-pdf/
      SKILL.md                            # Trigger + orchestration instructions
      references/
        cli-usage.md                      # Full JSON contract reference
.claude-plugin/
  plugin.json                             # Claude Code plugin manifest
.cursor-plugin/
  plugin.json                             # Cursor plugin manifest
.agents/
  skills/
    docsend-to-pdf/
      SKILL.md                            # Portable copy (no absolute paths)
      references/
        cli-usage.md                      # Portable copy
marketplace.json                          # Claude marketplace manifest
LICENSE                                   # MIT
README.md                                 # Multi-platform install + usage
CHANGELOG.md                              # Version history
.github/
  workflows/
    release.yml                           # Tag-based release workflow
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `cli/pyproject.toml`
- Create: `cli/docsend_to_pdf/__init__.py`
- Create: `cli/docsend_to_pdf/__main__.py`
- Create: `LICENSE`
- Create: `.gitignore`

- [ ] **Step 0: Resolve author metadata**

Before writing any files, ask the user for their author name and email. These values are needed in `marketplace.json`, `SKILL.md` metadata, `LICENSE`, and `pyproject.toml`. Store as variables and use consistently across all tasks:
- `AUTHOR_NAME` — e.g., "Jane Smith"
- `AUTHOR_EMAIL` — e.g., "jane@example.com"
- `GITHUB_OWNER` — e.g., "janesmith" (for README install instructions)

- [ ] **Step 1: Create the CLI package structure**

```bash
mkdir -p cli/docsend_to_pdf cli/tests/fixtures
```

- [ ] **Step 2: Write `cli/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "docsend-to-pdf"
version = "0.1.0"
description = "Convert DocSend links to PDF files"
license = "MIT"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28",
    "Pillow>=9.0",
    "click>=8.0",
]

[project.scripts]
docsend-to-pdf = "docsend_to_pdf.cli:main"
```

- [ ] **Step 3: Write `cli/docsend_to_pdf/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write `cli/docsend_to_pdf/__main__.py`**

```python
from docsend_to_pdf.cli import main

main()
```

- [ ] **Step 5: Write `LICENSE`**

Standard MIT license file with current year and author name.

- [ ] **Step 6: Write `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
*.pdf
```

- [ ] **Step 7: Initialize git repo and install the package in dev mode**

```bash
git init
pip install -e "./cli[dev]" 2>/dev/null || pip install -e ./cli
```

- [ ] **Step 8: Commit**

```bash
git add cli/pyproject.toml cli/docsend_to_pdf/__init__.py cli/docsend_to_pdf/__main__.py LICENSE .gitignore
git commit -m "chore: scaffold CLI package structure"
```

---

### Task 2: Types Module

**Files:**
- Create: `cli/docsend_to_pdf/types.py`
- Create: `cli/tests/test_types.py`

- [ ] **Step 1: Write the failing test for URL parsing**

Create `cli/tests/test_types.py`:

```python
import pytest
from docsend_to_pdf.types import DocSendURL, parse_url


class TestParseUrl:
    def test_standard_url(self):
        result = parse_url("https://docsend.com/view/abc123")
        assert result.doc_id == "abc123"
        assert result.normalized == "https://docsend.com/view/abc123"

    def test_subdomain_url(self):
        result = parse_url("https://company.docsend.com/view/xyz789")
        assert result.doc_id == "xyz789"
        assert result.normalized == "https://company.docsend.com/view/xyz789"

    def test_dropbox_variant(self):
        result = parse_url("https://www.docsend.dropbox.com/view/def456")
        assert result.doc_id == "def456"
        assert result.normalized == "https://www.docsend.dropbox.com/view/def456"

    def test_trailing_slash(self):
        result = parse_url("https://docsend.com/view/abc123/")
        assert result.doc_id == "abc123"

    def test_with_query_params(self):
        result = parse_url("https://docsend.com/view/abc123?ref=email")
        assert result.doc_id == "abc123"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid DocSend URL"):
            parse_url("https://google.com/doc/123")

    def test_missing_id_raises(self):
        with pytest.raises(ValueError, match="Not a valid DocSend URL"):
            parse_url("https://docsend.com/view/")

    def test_preserves_original(self):
        url = "https://docsend.com/view/abc123?ref=email"
        result = parse_url(url)
        assert result.original == url
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd cli && python -m pytest tests/test_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'docsend_to_pdf.types'`

- [ ] **Step 3: Write `cli/docsend_to_pdf/types.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Union


# URL pattern: (optional subdomain.)docsend(.dropbox)?.com/view/{id}
_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)?docsend(?:\.dropbox)?\.com/view/([a-zA-Z0-9]+)"
)


@dataclass(frozen=True)
class DocSendURL:
    original: str
    normalized: str
    doc_id: str


def parse_url(url: str) -> DocSendURL:
    """Validate and normalize a DocSend share URL."""
    m = _URL_RE.match(url)
    if not m:
        raise ValueError(f"Not a valid DocSend URL: {url}")
    doc_id = m.group(1)
    # Normalized = everything up to and including the doc ID
    normalized = m.group(0)
    return DocSendURL(original=url, normalized=normalized, doc_id=doc_id)


class GateKind(Enum):
    NONE = auto()
    EMAIL = auto()
    PASSCODE = auto()
    NDA = auto()
    VERIFICATION = auto()
    REJECTED = auto()


@dataclass(frozen=True)
class Gate:
    kind: GateKind
    text: str = ""  # NDA text or rejection message or email for verification


@dataclass(frozen=True)
class PageResponse:
    gate: Gate
    csrf_token: str
    title: str | None = None
    page_count: int | None = None


@dataclass(frozen=True)
class PageData:
    image_url: str
    page_num: int


@dataclass(frozen=True)
class Authenticated:
    csrf_token: str
    page_count: int


@dataclass(frozen=True)
class NeedsInput:
    gate: Gate


GateResult = Union[Authenticated, NeedsInput]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd cli && python -m pytest tests/test_types.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/docsend_to_pdf/types.py cli/tests/test_types.py
git commit -m "feat: add types module with URL parsing and gate types"
```

---

### Task 3: HTML Fixtures

Create realistic HTML fixtures for each gate type. These are used by the client tests in Task 4.

**Files:**
- Create: `cli/tests/fixtures/email_gate.html`
- Create: `cli/tests/fixtures/passcode_gate.html`
- Create: `cli/tests/fixtures/nda_gate.html`
- Create: `cli/tests/fixtures/verification_gate.html`
- Create: `cli/tests/fixtures/rejected.html`
- Create: `cli/tests/fixtures/authenticated.html`
- Create: `cli/tests/fixtures/page_data_1.json`
- Create: `cli/tests/conftest.py`

- [ ] **Step 1: Write `cli/tests/fixtures/email_gate.html`**

This mimics a DocSend page that requires an email address. Key elements: a form with `link_auth_form[email]` input and an `authenticity_token` hidden field. The `#prompt` element is present (indicates unauthenticated).

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Document</title></head>
<body>
  <div id="prompt">
    <div class="contact-card_description">Acme Corp</div>
    <div class="contact-card_email">sender@acme.com</div>
    <form action="/view/abc123" method="post">
      <input type="hidden" name="authenticity_token" value="csrf-token-123" />
      <input type="hidden" name="_method" value="patch" />
      <input type="text" name="link_auth_form[email]" placeholder="Email address" />
      <button type="submit">Continue</button>
    </form>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write `cli/tests/fixtures/passcode_gate.html`**

Same as email gate but with an additional passcode field.

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Document</title></head>
<body>
  <div id="prompt">
    <form action="/view/abc123" method="post">
      <input type="hidden" name="authenticity_token" value="csrf-token-456" />
      <input type="hidden" name="_method" value="patch" />
      <input type="text" name="link_auth_form[email]" placeholder="Email address" />
      <input type="password" name="link_auth_form[passcode]" placeholder="Passcode" />
      <button type="submit">Continue</button>
    </form>
  </div>
</body>
</html>
```

- [ ] **Step 3: Write `cli/tests/fixtures/nda_gate.html`**

Page after email gate cleared, now showing NDA acceptance.

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Document</title></head>
<body>
  <div id="prompt">
    <div class="nda-agreement">
      <div class="nda-agreement__content">
        By viewing this document, you agree to keep its contents confidential.
      </div>
      <form action="/view/abc123/nda" method="post">
        <input type="hidden" name="authenticity_token" value="csrf-token-789" />
        <button type="submit" class="nda-agreement__accept">I agree</button>
      </form>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Write `cli/tests/fixtures/verification_gate.html`**

Page requiring email verification code.

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Document</title></head>
<body>
  <div id="prompt">
    <div class="email-verification">
      <p>We sent a verification code to <strong>user@example.com</strong></p>
      <form action="/view/abc123/verify" method="post">
        <input type="hidden" name="authenticity_token" value="csrf-token-verify" />
        <input type="text" name="link_auth_form[verification_code]" placeholder="Enter code" />
        <button type="submit">Verify</button>
      </form>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 5: Write `cli/tests/fixtures/rejected.html`**

Page showing allowed-viewers rejection.

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Document</title></head>
<body>
  <div class="row flash flash-notice">
    <div class="alert_content alert_content--with-close">
      This link is restricted. Your email address is not authorized to view this document.
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 6: Write `cli/tests/fixtures/authenticated.html`**

Page after successful authentication — shows the document viewer with page count.

```html
<!DOCTYPE html>
<html>
<head><title>DocSend - Series A Deck</title></head>
<body>
  <div class="document-viewer">
    <div class="page-label">1 of 12</div>
    <div class="document-thumb-container" data-page-num="1"></div>
    <div class="document-thumb-container" data-page-num="2"></div>
    <div class="document-thumb-container" data-page-num="3"></div>
    <div class="document-thumb-container" data-page-num="4"></div>
    <div class="document-thumb-container" data-page-num="5"></div>
    <div class="document-thumb-container" data-page-num="6"></div>
    <div class="document-thumb-container" data-page-num="7"></div>
    <div class="document-thumb-container" data-page-num="8"></div>
    <div class="document-thumb-container" data-page-num="9"></div>
    <div class="document-thumb-container" data-page-num="10"></div>
    <div class="document-thumb-container" data-page-num="11"></div>
    <div class="document-thumb-container" data-page-num="12"></div>
    <meta name="csrf-token" content="csrf-token-auth" />
  </div>
</body>
</html>
```

- [ ] **Step 7: Write `cli/tests/fixtures/page_data_1.json`**

```json
{
  "imageUrl": "https://d1234.cloudfront.net/pages/abc123/page1.png?token=xyz"
}
```

- [ ] **Step 8: Write `cli/tests/conftest.py`**

```python
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_path():
    """Return a function that resolves fixture file paths."""
    def _get(name: str) -> Path:
        return FIXTURES_DIR / name
    return _get


@pytest.fixture
def fixture_html():
    """Return a function that reads fixture HTML files."""
    def _get(name: str) -> str:
        return (FIXTURES_DIR / name).read_text()
    return _get


@pytest.fixture
def fixture_json():
    """Return a function that reads fixture JSON files."""
    import json
    def _get(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())
    return _get
```

- [ ] **Step 9: Commit**

```bash
git add cli/tests/conftest.py cli/tests/fixtures/
git commit -m "test: add HTML and JSON fixtures for all gate types"
```

---

### Task 4: Client Module — Gate Detection

**Files:**
- Create: `cli/docsend_to_pdf/client.py`
- Create: `cli/tests/test_client.py`

- [ ] **Step 1: Write the failing tests for gate detection**

Create `cli/tests/test_client.py`:

```python
import pytest
from docsend_to_pdf.client import detect_gate, parse_page_response
from docsend_to_pdf.types import GateKind


class TestDetectGate:
    def test_email_gate(self, fixture_html):
        html = fixture_html("email_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.EMAIL

    def test_passcode_gate(self, fixture_html):
        html = fixture_html("passcode_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.PASSCODE

    def test_nda_gate(self, fixture_html):
        html = fixture_html("nda_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.NDA
        assert "confidential" in gate.text.lower()

    def test_verification_gate(self, fixture_html):
        html = fixture_html("verification_gate.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.VERIFICATION
        assert "user@example.com" in gate.text

    def test_rejected(self, fixture_html):
        html = fixture_html("rejected.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.REJECTED
        assert "not authorized" in gate.text.lower()

    def test_authenticated(self, fixture_html):
        html = fixture_html("authenticated.html")
        gate = detect_gate(html)
        assert gate.kind == GateKind.NONE


class TestParsePageResponse:
    def test_extracts_csrf_token(self, fixture_html):
        html = fixture_html("email_gate.html")
        resp = parse_page_response(html)
        assert resp.csrf_token == "csrf-token-123"

    def test_extracts_page_count_when_authenticated(self, fixture_html):
        html = fixture_html("authenticated.html")
        resp = parse_page_response(html)
        assert resp.page_count == 12

    def test_page_count_none_when_gated(self, fixture_html):
        html = fixture_html("email_gate.html")
        resp = parse_page_response(html)
        assert resp.page_count is None

    def test_extracts_title(self, fixture_html):
        html = fixture_html("authenticated.html")
        resp = parse_page_response(html)
        assert resp.title == "Series A Deck"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && python -m pytest tests/test_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'docsend_to_pdf.client'`

- [ ] **Step 3: Write `cli/docsend_to_pdf/client.py` — gate detection and page parsing**

```python
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Optional

import requests

from docsend_to_pdf.types import (
    Authenticated,
    DocSendURL,
    Gate,
    GateKind,
    GateResult,
    NeedsInput,
    PageData,
    PageResponse,
)


def detect_gate(html: str) -> Gate:
    """Detect which access gate (if any) is active in the HTML response."""
    # Check for rejection first (highest priority)
    if "not authorized" in html.lower() or "restricted" in html.lower():
        if "alert_content" in html or "flash-notice" in html:
            msg = _extract_text_from_class(html, "alert_content")
            return Gate(kind=GateKind.REJECTED, text=msg)

    # Check for verification gate
    if "link_auth_form[verification_code]" in html:
        email = _extract_verification_email(html)
        return Gate(kind=GateKind.VERIFICATION, text=email)

    # Check for NDA gate
    if "nda-agreement" in html:
        nda_text = _extract_text_from_class(html, "nda-agreement__content")
        return Gate(kind=GateKind.NDA, text=nda_text)

    # Check for passcode gate (has both email and passcode fields)
    if "link_auth_form[passcode]" in html:
        return Gate(kind=GateKind.PASSCODE)

    # Check for email gate
    if "link_auth_form[email]" in html:
        return Gate(kind=GateKind.EMAIL)

    # No gate — authenticated
    return Gate(kind=GateKind.NONE)


def parse_page_response(html: str) -> PageResponse:
    """Parse a DocSend page HTML into a structured response."""
    gate = detect_gate(html)
    csrf_token = _extract_csrf_token(html)
    title = _extract_title(html)
    page_count = _extract_page_count(html)
    return PageResponse(
        gate=gate,
        csrf_token=csrf_token,
        title=title,
        page_count=page_count,
    )


def fetch_page(session: requests.Session, url: DocSendURL) -> PageResponse:
    """GET the DocSend view page and parse the response."""
    resp = session.get(url.normalized, timeout=30)
    resp.raise_for_status()
    return parse_page_response(resp.text)


def submit_email(
    session: requests.Session,
    url: DocSendURL,
    csrf_token: str,
    email: str,
    passcode: str | None = None,
) -> tuple[str, GateResult]:
    """POST the email/passcode form. Returns (new_html, GateResult)."""
    data = {
        "authenticity_token": csrf_token,
        "_method": "patch",
        "link_auth_form[email]": email,
    }
    if passcode:
        data["link_auth_form[passcode]"] = passcode
    resp = session.post(url.normalized, data=data, timeout=30)
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def submit_verification(
    session: requests.Session,
    url: DocSendURL,
    csrf_token: str,
    code: str,
) -> tuple[str, GateResult]:
    """POST the verification code."""
    data = {
        "authenticity_token": csrf_token,
        "link_auth_form[verification_code]": code,
    }
    resp = session.post(f"{url.normalized}/verify", data=data, timeout=30)
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def accept_nda(
    session: requests.Session,
    url: DocSendURL,
    csrf_token: str,
) -> tuple[str, GateResult]:
    """POST the NDA acceptance."""
    data = {"authenticity_token": csrf_token}
    resp = session.post(f"{url.normalized}/nda", data=data, timeout=30)
    resp.raise_for_status()
    return _parse_gate_result(resp.text)


def fetch_page_data(
    session: requests.Session,
    url: DocSendURL,
    page_num: int,
) -> PageData | None:
    """GET page data for a specific page number. Returns None if page doesn't exist."""
    resp = session.get(f"{url.normalized}/page_data/{page_num}", timeout=30)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return PageData(image_url=data["imageUrl"], page_num=page_num)


def download_image(session: requests.Session, image_url: str) -> bytes:
    """Download a page image from CloudFront."""
    resp = session.get(image_url, timeout=60)
    resp.raise_for_status()
    return resp.content


# --- Private helpers ---


def _parse_gate_result(html: str) -> tuple[str, GateResult]:
    """Parse a POST response into a GateResult."""
    resp = parse_page_response(html)
    if resp.gate.kind == GateKind.NONE:
        return html, Authenticated(
            csrf_token=resp.csrf_token,
            page_count=resp.page_count or 0,
        )
    return html, NeedsInput(gate=resp.gate)


def _extract_csrf_token(html: str) -> str:
    """Extract CSRF token from authenticity_token input or meta tag."""
    # Try hidden input first
    m = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
    if m:
        return m.group(1)
    # Try meta tag
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    # Try reversed attribute order
    m = re.search(r'content="([^"]+)"\s+name="csrf-token"', html)
    if m:
        return m.group(1)
    return ""


def _extract_title(html: str) -> str | None:
    """Extract document title from the <title> tag, stripping 'DocSend - ' prefix."""
    m = re.search(r"<title>(?:DocSend\s*-\s*)?(.+?)</title>", html)
    if m:
        title = m.group(1).strip()
        if title and title.lower() != "document":
            return title
    return None


def _extract_page_count(html: str) -> int | None:
    """Extract page count from .page-label text like '1 of 12'."""
    m = re.search(r"(\d+)\s+of\s+(\d+)", html)
    if m:
        return int(m.group(2))
    # Fallback: count data-page-num attributes
    pages = re.findall(r'data-page-num="(\d+)"', html)
    if pages:
        return max(int(p) for p in pages)
    return None


def _extract_text_from_class(html: str, class_name: str) -> str:
    """Extract text content from an element with the given class."""
    pattern = rf'class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:div|p|span)>'
    m = re.search(pattern, html, re.DOTALL)
    if m:
        # Strip HTML tags from the content
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def _extract_verification_email(html: str) -> str:
    """Extract the email address from the verification page."""
    m = re.search(r"<strong>([^<]+@[^<]+)</strong>", html)
    if m:
        return m.group(1).strip()
    return ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd cli && python -m pytest tests/test_client.py -v
```

Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/docsend_to_pdf/client.py cli/tests/test_client.py
git commit -m "feat: add client module with gate detection and page parsing"
```

---

### Task 5: PDF Builder Module

**Files:**
- Create: `cli/docsend_to_pdf/pdf_builder.py`
- Create: `cli/tests/test_pdf_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `cli/tests/test_pdf_builder.py`:

```python
import io
from pathlib import Path

import pytest
from PIL import Image

from docsend_to_pdf.pdf_builder import process_image, build_pdf


def _make_rgba_png(width: int = 100, height: int = 80, alpha: int = 128) -> bytes:
    """Create a minimal RGBA PNG as bytes."""
    img = Image.new("RGBA", (width, height), (255, 0, 0, alpha))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_rgb_png(width: int = 100, height: int = 80) -> bytes:
    """Create a minimal RGB PNG as bytes (no alpha)."""
    img = Image.new("RGB", (width, height), (0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestProcessImage:
    def test_rgba_to_rgb(self):
        png_bytes = _make_rgba_png()
        result = process_image(png_bytes)
        assert result.mode == "RGB"

    def test_composites_on_white(self):
        # Fully transparent red on white should be white
        png_bytes = _make_rgba_png(alpha=0)
        result = process_image(png_bytes)
        # Check center pixel is white
        pixel = result.getpixel((50, 40))
        assert pixel == (255, 255, 255)

    def test_opaque_preserved(self):
        # Fully opaque red should stay red
        png_bytes = _make_rgba_png(alpha=255)
        result = process_image(png_bytes)
        pixel = result.getpixel((50, 40))
        assert pixel == (255, 0, 0)

    def test_handles_rgb_input(self):
        png_bytes = _make_rgb_png()
        result = process_image(png_bytes)
        assert result.mode == "RGB"


class TestBuildPdf:
    def test_single_page(self, tmp_path: Path):
        img = process_image(_make_rgba_png())
        output = tmp_path / "test.pdf"
        build_pdf([img], str(output))
        assert output.exists()
        assert output.stat().st_size > 0

    def test_multi_page(self, tmp_path: Path):
        images = [process_image(_make_rgba_png()) for _ in range(3)]
        output = tmp_path / "multi.pdf"
        build_pdf(images, str(output))
        assert output.exists()
        assert output.stat().st_size > 0

    def test_empty_raises(self, tmp_path: Path):
        output = tmp_path / "empty.pdf"
        with pytest.raises(ValueError, match="No images"):
            build_pdf([], str(output))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && python -m pytest tests/test_pdf_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'docsend_to_pdf.pdf_builder'`

- [ ] **Step 3: Write `cli/docsend_to_pdf/pdf_builder.py`**

```python
from __future__ import annotations

import io

from PIL import Image


def process_image(png_bytes: bytes) -> Image.Image:
    """Load a PNG and composite RGBA onto a white RGB background."""
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def build_pdf(images: list[Image.Image], output_path: str) -> None:
    """Assemble a list of RGB images into a multi-page PDF."""
    if not images:
        raise ValueError("No images to assemble into PDF")
    first, *rest = images
    first.save(
        output_path,
        format="PDF",
        save_all=True,
        append_images=rest,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd cli && python -m pytest tests/test_pdf_builder.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/docsend_to_pdf/pdf_builder.py cli/tests/test_pdf_builder.py
git commit -m "feat: add PDF builder with RGBA compositing and multi-page assembly"
```

---

### Task 6: CLI Module — Session Serialization

**Files:**
- Create: `cli/docsend_to_pdf/cli.py`
- Create: `cli/tests/test_cli.py`

Start with session serialization/deserialization and JSON output — the CLI's internal plumbing — before wiring up the full command.

- [ ] **Step 1: Write the failing tests for session handling**

Create `cli/tests/test_cli.py`:

```python
import base64
import json
from pathlib import Path

import pytest

from docsend_to_pdf.cli import serialize_session, deserialize_session, format_output


class TestSessionSerialization:
    def test_round_trip_blob(self):
        state = {
            "url": "https://docsend.com/view/abc",
            "cookies": {"_docsend_session": "sess123"},
            "csrf_token": "tok",
            "gates_cleared": ["email"],
            "pending_gate": "verification",
            "email": "me@co.com",
        }
        blob = serialize_session(state)
        # Should be valid base64
        decoded = json.loads(base64.b64decode(blob))
        assert decoded["url"] == state["url"]
        # Round trip
        result = deserialize_session(blob=blob)
        assert result == state

    def test_round_trip_file(self, tmp_path: Path):
        state = {
            "url": "https://docsend.com/view/xyz",
            "cookies": {},
            "csrf_token": "tok2",
            "gates_cleared": [],
            "pending_gate": "email",
            "email": "",
        }
        state_file = tmp_path / "state.json"
        blob = serialize_session(state, state_file=str(state_file))
        assert state_file.exists()
        result = deserialize_session(state_file=str(state_file))
        assert result == state

    def test_deserialize_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            deserialize_session(state_file=str(tmp_path / "nope.json"))

    def test_deserialize_no_source_raises(self):
        with pytest.raises(ValueError, match="either blob or state_file"):
            deserialize_session()


class TestFormatOutput:
    def test_complete(self):
        result = format_output(
            status="complete", pages=12, output="deck.pdf", title="My Deck"
        )
        parsed = json.loads(result)
        assert parsed["status"] == "complete"
        assert parsed["pages"] == 12
        assert parsed["output"] == "deck.pdf"
        assert parsed["title"] == "My Deck"

    def test_needs_email_with_blob(self):
        result = format_output(status="needs_email", session="abc123")
        parsed = json.loads(result)
        assert parsed["status"] == "needs_email"
        assert parsed["session"] == "abc123"

    def test_needs_verification_with_state_file(self):
        result = format_output(
            status="needs_verification",
            email="me@co.com",
            state_file="/tmp/state.json",
        )
        parsed = json.loads(result)
        assert parsed["status"] == "needs_verification"
        assert parsed["email"] == "me@co.com"
        assert parsed["state_file"] == "/tmp/state.json"
        assert "session" not in parsed

    def test_error(self):
        result = format_output(status="error", message="Link expired")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["message"] == "Link expired"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && python -m pytest tests/test_cli.py -v
```

Expected: ImportError.

- [ ] **Step 3: Write session serialization and output formatting in `cli/docsend_to_pdf/cli.py`**

```python
from __future__ import annotations

import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import click
import requests

from docsend_to_pdf import __version__
from docsend_to_pdf.client import (
    accept_nda,
    download_image,
    fetch_page,
    fetch_page_data,
    submit_email,
    submit_verification,
)
from docsend_to_pdf.pdf_builder import build_pdf, process_image
from docsend_to_pdf.types import (
    Authenticated,
    DocSendURL,
    GateKind,
    NeedsInput,
    parse_url,
)


def serialize_session(
    state: dict, state_file: str | None = None
) -> str:
    """Serialize session state to base64 blob, and optionally write to file."""
    data = json.dumps(state)
    if state_file:
        Path(state_file).write_text(data)
    return base64.b64encode(data.encode()).decode()


def deserialize_session(
    blob: str | None = None, state_file: str | None = None
) -> dict:
    """Deserialize session state from base64 blob or file."""
    if state_file:
        path = Path(state_file)
        if not path.exists():
            raise FileNotFoundError(f"State file not found: {state_file}")
        return json.loads(path.read_text())
    if blob:
        return json.loads(base64.b64decode(blob))
    raise ValueError("Must provide either blob or state_file")


def format_output(**kwargs: Any) -> str:
    """Format a JSON output object, stripping None values."""
    return json.dumps({k: v for k, v in kwargs.items() if v is not None})


def _build_session_state(
    url: DocSendURL,
    session: requests.Session,
    csrf_token: str,
    gates_cleared: list[str],
    pending_gate: str,
    email: str,
) -> dict:
    """Build the session state dict from current state."""
    return {
        "url": url.normalized,
        "cookies": dict(session.cookies),
        "csrf_token": csrf_token,
        "gates_cleared": gates_cleared,
        "pending_gate": pending_gate,
        "email": email,
    }


def _restore_session(state: dict) -> requests.Session:
    """Restore a requests.Session from serialized state."""
    session = requests.Session()
    for name, value in state.get("cookies", {}).items():
        session.cookies.set(name, value)
    return session


MAX_GATE_TRANSITIONS = 4


def _run_conversion(
    url: DocSendURL,
    email: str | None,
    passcode: str | None,
    verification_code: str | None,
    accept_nda_flag: bool,
    output_path: str | None,
    json_mode: bool,
    quiet: bool,
    session_blob: str | None,
    state_file: str | None,
) -> int:
    """Core conversion logic. Returns exit code."""
    # Restore or create session
    gates_cleared: list[str] = []
    csrf_token = ""
    restored_email = ""

    if session_blob or state_file:
        state = deserialize_session(blob=session_blob, state_file=state_file)
        http_session = _restore_session(state)
        url = parse_url(state["url"])
        gates_cleared = state.get("gates_cleared", [])
        csrf_token = state.get("csrf_token", "")
        restored_email = state.get("email", "")
        if not email:
            email = restored_email
    else:
        http_session = requests.Session()

    # Fetch the page
    if not quiet:
        print(f"Fetching {url.normalized}...", file=sys.stderr)

    page_resp = fetch_page(http_session, url)
    csrf_token = page_resp.csrf_token or csrf_token
    current_gate = page_resp.gate

    # Navigate gates
    for _ in range(MAX_GATE_TRANSITIONS):
        if current_gate.kind == GateKind.NONE:
            break

        if current_gate.kind == GateKind.REJECTED:
            output = format_output(status="error", message=current_gate.text)
            if json_mode:
                print(output)
            else:
                print(f"Error: {current_gate.text}", file=sys.stderr)
            return 1

        if current_gate.kind in (GateKind.EMAIL, GateKind.PASSCODE):
            if not email:
                state = _build_session_state(
                    url, http_session, csrf_token, gates_cleared,
                    "email" if current_gate.kind == GateKind.EMAIL else "passcode",
                    "",
                )
                status = "needs_email" if current_gate.kind == GateKind.EMAIL else "needs_passcode"
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    if state_file:
                        print(format_output(status=status, state_file=state_file))
                    else:
                        print(format_output(status=status, session=blob))
                else:
                    print(f"This link requires {'an email' if status == 'needs_email' else 'a passcode'}.", file=sys.stderr)
                return 2

            if current_gate.kind == GateKind.PASSCODE and not passcode:
                state = _build_session_state(
                    url, http_session, csrf_token, gates_cleared, "passcode", email,
                )
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    if state_file:
                        print(format_output(status="needs_passcode", state_file=state_file))
                    else:
                        print(format_output(status="needs_passcode", session=blob))
                else:
                    print("This link requires a passcode.", file=sys.stderr)
                return 2

            if not quiet:
                print("Submitting email...", file=sys.stderr)
            _, result = submit_email(http_session, url, csrf_token, email, passcode)
            gates_cleared.append("email")
            if isinstance(result, Authenticated):
                current_gate = result
                break
            current_gate = result.gate
            csrf_token = _extract_csrf_from_result(result, csrf_token)
            continue

        if current_gate.kind == GateKind.NDA:
            if not accept_nda_flag:
                state = _build_session_state(
                    url, http_session, csrf_token, gates_cleared, "nda", email or "",
                )
                blob = serialize_session(state, state_file=state_file)
                if json_mode:
                    if state_file:
                        print(format_output(status="needs_nda", nda_text=current_gate.text, state_file=state_file))
                    else:
                        print(format_output(status="needs_nda", nda_text=current_gate.text, session=blob))
                else:
                    print(f"NDA required:\n{current_gate.text}", file=sys.stderr)
                return 2

            if not quiet:
                print("Accepting NDA...", file=sys.stderr)
            _, result = accept_nda(http_session, url, csrf_token)
            gates_cleared.append("nda")
            if isinstance(result, Authenticated):
                current_gate = result
                break
            current_gate = result.gate
            csrf_token = _extract_csrf_from_result(result, csrf_token)
            continue

        if current_gate.kind == GateKind.VERIFICATION:
            if not verification_code:
                state = _build_session_state(
                    url, http_session, csrf_token, gates_cleared,
                    "verification", email or restored_email,
                )
                blob = serialize_session(state, state_file=state_file)
                verification_email = current_gate.text or email or restored_email
                if json_mode:
                    if state_file:
                        print(format_output(status="needs_verification", email=verification_email, state_file=state_file))
                    else:
                        print(format_output(status="needs_verification", email=verification_email, session=blob))
                else:
                    print(f"Verification code sent to {verification_email}.", file=sys.stderr)
                return 2

            if not quiet:
                print("Submitting verification code...", file=sys.stderr)
            _, result = submit_verification(http_session, url, csrf_token, verification_code)
            gates_cleared.append("verification")
            if isinstance(result, Authenticated):
                current_gate = result
                break
            current_gate = result.gate
            csrf_token = _extract_csrf_from_result(result, csrf_token)
            continue

    else:
        if json_mode:
            print(format_output(status="error", message="Too many gate transitions"))
        else:
            print("Error: Too many gate transitions", file=sys.stderr)
        return 1

    # At this point we're authenticated
    # Determine page count
    if isinstance(current_gate, Authenticated):
        page_count = current_gate.page_count
    else:
        page_count = page_resp.page_count

    if not page_count:
        # Fallback: probe pages
        page_count = 0
        for i in range(1, 500):
            pd = fetch_page_data(http_session, url, i)
            if pd is None:
                break
            page_count = i
        if page_count == 0:
            if json_mode:
                print(format_output(status="error", message="Could not determine page count"))
            else:
                print("Error: Could not determine page count", file=sys.stderr)
            return 1

    if not quiet:
        print(f"Downloading {page_count} pages...", file=sys.stderr)

    # Fetch page data and download images
    def _download_page(page_num: int) -> bytes | None:
        pd = fetch_page_data(http_session, url, page_num)
        if pd is None:
            return None
        return download_image(http_session, pd.image_url)

    with ThreadPoolExecutor(max_workers=4) as pool:
        raw_images = list(pool.map(_download_page, range(1, page_count + 1)))

    images = []
    for i, raw in enumerate(raw_images):
        if raw is None:
            if json_mode:
                print(format_output(status="error", message=f"Failed to download page {i+1}"))
            else:
                print(f"Error: Failed to download page {i+1}", file=sys.stderr)
            return 1
        images.append(process_image(raw))

    # Determine output path
    title = page_resp.title
    if not output_path:
        if title:
            safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
            output_path = f"{safe_title}.pdf" if safe_title else f"docsend-{url.doc_id}.pdf"
        else:
            output_path = f"docsend-{url.doc_id}.pdf"

    if not quiet:
        print(f"Building PDF: {output_path}", file=sys.stderr)

    build_pdf(images, output_path)

    if json_mode:
        print(format_output(status="complete", pages=page_count, output=output_path, title=title))
    else:
        print(f"Saved {page_count}-page PDF to {output_path}")

    return 0


def _extract_csrf_from_result(result: NeedsInput, fallback: str) -> str:
    """Extract CSRF token from a NeedsInput result, or use fallback."""
    # The gate itself doesn't carry CSRF; it's re-parsed from the next fetch.
    # For now, use the fallback. The next fetch_page will get a fresh one.
    return fallback


@click.command()
@click.argument("url", required=False)
@click.option("--email", help="Email for gate authentication")
@click.option("--passcode", help="Passcode if link is passcode-protected")
@click.option("--verification-code", help="Email verification code")
@click.option("--accept-nda", "accept_nda_flag", is_flag=True, help="Accept NDA/agreement gate")
@click.option("--session", "session_blob", help="Resume with base64 session blob")
@click.option("--state-file", help="Persist/read session state to/from file")
@click.option("-o", "--output", "output_path", help="Output PDF path")
@click.option("--json", "json_mode", is_flag=True, help="Structured JSON output")
@click.option("--quiet", is_flag=True, help="Suppress progress output")
@click.version_option(version=__version__)
def main(
    url: str | None,
    email: str | None,
    passcode: str | None,
    verification_code: str | None,
    accept_nda_flag: bool,
    session_blob: str | None,
    state_file: str | None,
    output_path: str | None,
    json_mode: bool,
    quiet: bool,
) -> None:
    """Convert a DocSend link to PDF."""
    # URL is required unless resuming
    if not url and not session_blob and not state_file:
        raise click.UsageError("URL is required unless resuming with --session or --state-file")

    if url:
        try:
            parsed_url = parse_url(url)
        except ValueError as e:
            if json_mode:
                print(format_output(status="error", message=str(e)))
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Will be restored from session
        parsed_url = parse_url("https://docsend.com/view/placeholder")

    try:
        exit_code = _run_conversion(
            url=parsed_url,
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
    except requests.RequestException as e:
        if json_mode:
            print(format_output(status="error", message=str(e)))
        else:
            print(f"Error: {e}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd cli && python -m pytest tests/test_cli.py -v
```

Expected: All 7 tests PASS (the session/format tests). The full CLI integration depends on mocked HTTP — that's Task 7.

- [ ] **Step 5: Commit**

```bash
git add cli/docsend_to_pdf/cli.py cli/tests/test_cli.py
git commit -m "feat: add CLI with session serialization, gate state machine, and PDF download"
```

---

### Task 7: CLI Integration Tests

**Files:**
- Modify: `cli/tests/test_cli.py`

Test the full `_run_conversion` function with mocked HTTP responses, verifying the gate state machine and JSON output contract.

- [ ] **Step 1: Add integration tests to `cli/tests/test_cli.py`**

Append to the existing file:

```python
from unittest.mock import MagicMock, patch, PropertyMock
import io
from PIL import Image

from docsend_to_pdf.cli import _run_conversion
from docsend_to_pdf.types import parse_url


def _make_test_png() -> bytes:
    """Create a small valid PNG for testing."""
    img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestRunConversionEmailGate:
    """Test that the CLI correctly stops at the email gate and outputs JSON."""

    def test_needs_email_json(self, fixture_html, capsys, tmp_path):
        html = fixture_html("email_gate.html")

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session.cookies = MagicMock()
        mock_session.cookies.__iter__ = MagicMock(return_value=iter([]))

        with patch("docsend_to_pdf.cli.requests.Session", return_value=mock_session):
            url = parse_url("https://docsend.com/view/abc123")
            exit_code = _run_conversion(
                url=url, email=None, passcode=None, verification_code=None,
                accept_nda_flag=False, output_path=None, json_mode=True,
                quiet=True, session_blob=None, state_file=None,
            )

        assert exit_code == 2
        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "needs_email"
        assert "session" in output


class TestRunConversionSuccess:
    """Test the full happy path with mocked responses."""

    def test_no_gate_downloads_and_builds_pdf(self, fixture_html, fixture_json, capsys, tmp_path):
        auth_html = fixture_html("authenticated.html")
        page_data = fixture_json("page_data_1.json")
        test_png = _make_test_png()

        mock_session = MagicMock()
        mock_session.cookies = MagicMock()
        mock_session.cookies.__iter__ = MagicMock(return_value=iter([]))

        # GET /view/abc123 returns authenticated page
        auth_resp = MagicMock()
        auth_resp.text = auth_html
        auth_resp.status_code = 200
        auth_resp.raise_for_status = MagicMock()

        # GET /page_data/N returns page data for pages 1-12, 404 for 13+
        def mock_get(url, **kwargs):
            if "page_data/" in url:
                page_num = int(url.split("page_data/")[1])
                resp = MagicMock()
                if page_num <= 12:
                    resp.status_code = 200
                    resp.json.return_value = page_data
                    resp.raise_for_status = MagicMock()
                    return resp
                else:
                    resp.status_code = 404
                    return resp
            if "cloudfront.net" in url:
                resp = MagicMock()
                resp.content = test_png
                resp.status_code = 200
                resp.raise_for_status = MagicMock()
                return resp
            return auth_resp

        mock_session.get.side_effect = mock_get

        output_path = str(tmp_path / "output.pdf")

        with patch("docsend_to_pdf.cli.requests.Session", return_value=mock_session):
            url = parse_url("https://docsend.com/view/abc123")
            exit_code = _run_conversion(
                url=url, email=None, passcode=None, verification_code=None,
                accept_nda_flag=False, output_path=output_path, json_mode=True,
                quiet=True, session_blob=None, state_file=None,
            )

        assert exit_code == 0
        output = json.loads(capsys.readouterr().out.strip())
        assert output["status"] == "complete"
        assert output["pages"] == 12
        assert Path(output_path).exists()
```

- [ ] **Step 2: Run all CLI tests**

```bash
cd cli && python -m pytest tests/test_cli.py -v
```

Expected: All tests PASS (session tests + integration tests).

- [ ] **Step 3: Run full test suite**

```bash
cd cli && python -m pytest -v
```

Expected: All tests across all modules PASS.

- [ ] **Step 4: Commit**

```bash
git add cli/tests/test_cli.py
git commit -m "test: add integration tests for CLI gate handling and PDF download"
```

---

### Task 8: Skill — SKILL.md and References

**Files:**
- Create: `docsend-to-pdf/skills/docsend-to-pdf/SKILL.md`
- Create: `docsend-to-pdf/skills/docsend-to-pdf/references/cli-usage.md`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p docsend-to-pdf/skills/docsend-to-pdf/references
```

- [ ] **Step 2: Write `docsend-to-pdf/skills/docsend-to-pdf/SKILL.md`**

```markdown
---
name: docsend-to-pdf
description: >-
  Converts DocSend shared links to downloadable PDF files. Use when the user
  shares a docsend.com or docsend.dropbox.com URL, asks to "download this
  deck", "save this DocSend as PDF", "convert this DocSend link", or wants
  to extract a document from DocSend. Also triggers on bare DocSend URLs
  pasted without explicit instructions. Handles all access gates including
  email, passcode, NDA acceptance, and email verification — can optionally
  check user's connected email for verification codes with permission.
  Does NOT handle Papermark, Google Docs, Pitch.com, or other document
  sharing platforms.
metadata:
  version: "0.1.0"
  author: "<author>"
---

# DocSend to PDF

Convert DocSend shared links to downloadable PDF files.

## Prerequisites

Check if the CLI is installed:

```bash
python -m docsend_to_pdf --version
```

If not installed, install from this plugin's `cli/` directory. Try in order:

1. `pipx install ${CLAUDE_PLUGIN_ROOT}/cli/`
2. `pip install --user ${CLAUDE_PLUGIN_ROOT}/cli/`
3. `pip install ${CLAUDE_PLUGIN_ROOT}/cli/`

Report failure clearly if all attempts fail.

## Invocation

Run the CLI with `--json` for structured output:

```bash
python -m docsend_to_pdf "<url>" --email "<email>" --json -o "<output>.pdf"
```

If the user hasn't provided an email, omit `--email` — the CLI will report what it needs.

## Response Handling

Parse the JSON output from stdout. Handle each `status` value:

| Status | Action |
|---|---|
| `complete` | Report success: "`Downloaded <pages>-page deck to <output>`". Mention the title if present. |
| `needs_email` | Ask user for their email address. Re-invoke with `--email <email> --session <session>`. |
| `needs_passcode` | Ask user for the passcode. Re-invoke with `--passcode <code> --session <session>`. |
| `needs_nda` | Show the `nda_text` to the user. Ask: "This document requires accepting an NDA. Shall I accept it?" If yes, re-invoke with `--accept-nda --session <session>`. |
| `needs_verification` | See Verification Flow below. |
| `error` | Report the `message` to the user. |

Always pass `--session <session>` (from the previous JSON output) when re-invoking to resume.

## Verification Flow

When status is `needs_verification`:

1. Check your available tools for any email-related MCP (tools containing "mail", "email", or "inbox" in their names).

2. **If email access is available**, ask the user:
   > "DocSend sent a verification code to **<email>**. I can either:
   > (A) You paste the code here
   > (B) I check your email for the code (requires your approval)"

3. **If no email access**, ask the user to paste the code.

4. Once you have the code, re-invoke: `python -m docsend_to_pdf --verification-code <code> --session <session> --json -o "<output>.pdf"`

**Never access the user's email without explicit approval in that moment.**

## Error Recovery

If the CLI exits with code 1 and no JSON on stdout, report the stderr output. Common causes:
- Network timeout — suggest retrying
- Invalid URL — ask user to verify the link
- Missing Python dependency — suggest `pip install` commands

## Reference

For the full JSON contract, all CLI flags, and example invocations for each gate scenario, read `references/cli-usage.md`.
```

- [ ] **Step 3: Write `docsend-to-pdf/skills/docsend-to-pdf/references/cli-usage.md`**

```markdown
# DocSend to PDF — CLI Reference

## Contents

- [Command](#command)
- [Arguments and Options](#arguments-and-options)
- [Exit Codes](#exit-codes)
- [JSON Output Contract](#json-output-contract)
- [Session Blob Format](#session-blob-format)
- [URL Patterns](#url-patterns)
- [Example Invocations](#example-invocations)

## Command

```
docsend-to-pdf <url> [options]
python -m docsend_to_pdf <url> [options]
```

## Arguments and Options

| Flag | Description |
|---|---|
| `<url>` | DocSend URL. Not needed when resuming with `--session` or `--state-file`. |
| `--email <email>` | Email for gate authentication |
| `--passcode <code>` | Passcode for passcode-protected links |
| `--verification-code <code>` | Email verification code for Verified Visitors |
| `--accept-nda` | Accept NDA/agreement gate |
| `--session <blob>` | Resume with base64 session blob from previous JSON output |
| `--state-file <path>` | Persist/read session state to/from a file |
| `-o, --output <path>` | Output PDF path (default: `<title>.pdf` or `docsend-<id>.pdf`) |
| `--json` | Structured JSON output to stdout |
| `--quiet` | Suppress progress messages on stderr |
| `--version` | Show version |
| `--help` | Show help |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success — PDF written |
| 1 | Error — network failure, auth rejected, invalid URL |
| 2 | Needs input — gate requires a value from the user |

## JSON Output Contract

Every invocation with `--json` produces exactly one JSON object on stdout.

### Success

```json
{"status": "complete", "pages": 12, "output": "deck.pdf", "title": "Series A Deck"}
```

### Needs Email

```json
{"status": "needs_email", "session": "<base64-blob>"}
```

### Needs Passcode

```json
{"status": "needs_passcode", "session": "<base64-blob>"}
```

### Needs Verification Code

```json
{"status": "needs_verification", "email": "user@example.com", "session": "<base64-blob>"}
```

### Needs NDA Acceptance

```json
{"status": "needs_nda", "nda_text": "Agreement text here...", "session": "<base64-blob>"}
```

### Error

```json
{"status": "error", "message": "Link not found or expired"}
```

### State File Mode

When `--state-file` is used, `session` is replaced with `state_file`:

```json
{"status": "needs_verification", "email": "user@example.com", "state_file": "/tmp/state.json"}
```

## Session Blob Format

The `session` field is a base64-encoded JSON object:

```json
{
  "url": "https://docsend.com/view/abc123",
  "cookies": {"_docsend_session": "..."},
  "csrf_token": "...",
  "gates_cleared": ["email"],
  "pending_gate": "verification",
  "email": "user@example.com"
}
```

## URL Patterns

All of these are valid DocSend URLs:

- `https://docsend.com/view/abc123`
- `https://company.docsend.com/view/abc123`
- `https://www.docsend.dropbox.com/view/abc123`

## Example Invocations

### Happy path (no gate)

```bash
python -m docsend_to_pdf "https://docsend.com/view/abc123" --json -o deck.pdf
# → {"status": "complete", "pages": 12, "output": "deck.pdf", "title": "Series A Deck"}
```

### Email gate — two phases

```bash
# Phase 1: discover gate
python -m docsend_to_pdf "https://docsend.com/view/abc123" --json
# → {"status": "needs_email", "session": "eyJ1cmwiOi..."}

# Phase 2: provide email
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --session "eyJ1cmwiOi..." --json -o deck.pdf
# → {"status": "complete", "pages": 8, "output": "deck.pdf", "title": "Pitch Deck"}
```

### Email + verification — three phases

```bash
# Phase 1: provide email, hits verification
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --json
# → {"status": "needs_verification", "email": "me@co.com", "session": "eyJ1cmwiOi..."}

# Phase 2: provide verification code
python -m docsend_to_pdf --session "eyJ1cmwiOi..." --verification-code "123456" --json -o deck.pdf
# → {"status": "complete", "pages": 15, "output": "deck.pdf", "title": "Board Deck"}
```

### NDA gate

```bash
# Phase 1: hits NDA
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --json
# → {"status": "needs_nda", "nda_text": "By viewing...", "session": "eyJ1cmwiOi..."}

# Phase 2: accept NDA
python -m docsend_to_pdf --session "eyJ1cmwiOi..." --accept-nda --json -o deck.pdf
# → {"status": "complete", "pages": 20, "output": "deck.pdf", "title": "Confidential Memo"}
```

### Using state file instead of blob

```bash
# Phase 1
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --state-file /tmp/ds.json --json
# → {"status": "needs_verification", "email": "me@co.com", "state_file": "/tmp/ds.json"}

# Phase 2 (URL not needed — stored in state file)
python -m docsend_to_pdf --state-file /tmp/ds.json --verification-code "123456" --json -o deck.pdf
# → {"status": "complete", "pages": 15, "output": "deck.pdf", "title": "Board Deck"}
```
```

- [ ] **Step 4: Commit**

```bash
git add docsend-to-pdf/
git commit -m "feat: add Claude Code skill with SKILL.md and CLI reference"
```

---

### Task 9: Plugin Manifests and Packaging

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.cursor-plugin/plugin.json`
- Create: `marketplace.json`
- Create: `.agents/skills/docsend-to-pdf/SKILL.md` (portable copy)
- Create: `.agents/skills/docsend-to-pdf/references/cli-usage.md` (portable copy)

- [ ] **Step 1: Create directories**

```bash
mkdir -p .claude-plugin .cursor-plugin .agents/skills/docsend-to-pdf/references
```

- [ ] **Step 2: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "docsend-to-pdf",
  "version": "0.1.0",
  "description": "Convert DocSend links to PDF files",
  "skills": "./docsend-to-pdf/skills"
}
```

- [ ] **Step 3: Write `.cursor-plugin/plugin.json`**

```json
{
  "name": "docsend-to-pdf",
  "version": "0.1.0",
  "description": "Convert DocSend links to PDF files",
  "skills": "./docsend-to-pdf/skills"
}
```

- [ ] **Step 4: Write `marketplace.json`**

```json
{
  "name": "docsend-to-pdf-marketplace",
  "display_name": "DocSend to PDF",
  "description": "Convert DocSend shared links to downloadable PDF files with full gate handling",
  "version": "0.1.0",
  "license": "MIT",
  "plugins": [
    {
      "name": "docsend-to-pdf",
      "path": "./docsend-to-pdf"
    }
  ]
}
```

- [ ] **Step 5: Create portable `.agents/skills/` copy**

Copy the canonical SKILL.md and apply these exact replacements:

```bash
cp docsend-to-pdf/skills/docsend-to-pdf/SKILL.md .agents/skills/docsend-to-pdf/SKILL.md
cp docsend-to-pdf/skills/docsend-to-pdf/references/cli-usage.md .agents/skills/docsend-to-pdf/references/cli-usage.md
```

Then edit `.agents/skills/docsend-to-pdf/SKILL.md` — replace the Prerequisites section:

**Before (canonical):**
```
1. `pipx install ${CLAUDE_PLUGIN_ROOT}/cli/`
2. `pip install --user ${CLAUDE_PLUGIN_ROOT}/cli/`
3. `pip install ${CLAUDE_PLUGIN_ROOT}/cli/`
```

**After (portable):**
```
1. `pipx install <path-to-repo>/cli/` (clone the repo first if needed: `git clone https://github.com/<GITHUB_OWNER>/docsend-to-pdf-skill && pipx install ./docsend-to-pdf-skill/cli/`)
2. `pip install --user <path-to-repo>/cli/`
3. `pip install <path-to-repo>/cli/`
```

Also remove the `metadata.author` field from the portable copy's frontmatter (it's plugin-specific).

`references/cli-usage.md` is copied as-is (no absolute paths).

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/ .cursor-plugin/ .agents/ marketplace.json
git commit -m "feat: add plugin manifests and cross-platform skill copy"
```

---

### Task 10: README, CHANGELOG, and Release Workflow

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write `README.md`**

Include:
- Title: "DocSend to PDF"
- Badges (use shield.io format):
  - `![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)`
  - `![Agent Skills](https://img.shields.io/badge/Agent%20Skills-compatible-blue)`
  - `![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-purple)`
  - `![Cursor](https://img.shields.io/badge/Cursor-plugin-blue)`
- One-paragraph description of what it does
- **Installation** section with subsections for:
  - Claude Code: `claude plugin add <GITHUB_OWNER>/docsend-to-pdf-skill`
  - Cursor: install from `.cursor-plugin/`
  - Agent Skills / Codex CLI: `npx skills add <GITHUB_OWNER>/docsend-to-pdf-skill`
  - Standalone CLI: `pipx install ./cli` or `pip install ./cli`
- **Usage** section with:
  - CLI examples (basic, with email, two-phase)
  - Skill trigger phrases
- **How it works** — brief explanation: fetches page images via DocSend's internal API, composites onto white background, assembles PDF
- **Access gates** — table of supported gates
- **GitHub Pages setup** — note: "To enable the 'Install in Claude Desktop' button, go to repo Settings → Pages → Source: GitHub Actions."
- **License** — MIT

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

## [0.1.0] - 2026-04-15

### Added
- Initial release
- Python CLI tool with all DocSend gate types (email, passcode, NDA, verification, allowed viewers)
- Two-phase resumable design (session blob and state file modes)
- Structured JSON output for programmatic use
- Claude Code skill with conversational gate handling
- Optional email integration for verification code retrieval
- Cross-platform packaging (Claude Code, Cursor, Agent Skills)
```

- [ ] **Step 3: Write `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Extract version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Update version strings
        run: |
          VERSION=${{ steps.version.outputs.VERSION }}
          sed -i "s/version = \".*\"/version = \"$VERSION\"/" cli/pyproject.toml
          sed -i "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" cli/docsend_to_pdf/__init__.py
          for f in .claude-plugin/plugin.json .cursor-plugin/plugin.json marketplace.json; do
            sed -i "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" "$f"
          done
          # Update SKILL.md metadata.version in both canonical and portable copies
          for f in docsend-to-pdf/skills/docsend-to-pdf/SKILL.md .agents/skills/docsend-to-pdf/SKILL.md; do
            sed -i "s/version: \".*\"/version: \"$VERSION\"/" "$f"
          done

      - name: Build CLI package
        run: |
          pip install build
          python -m build cli/

      - name: Create skill zip
        run: |
          cd docsend-to-pdf/skills/docsend-to-pdf
          zip -r ../../../dist/docsend-to-pdf-skill.zip .

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: |
            cli/dist/*.whl
            dist/docsend-to-pdf-skill.zip
```

- [ ] **Step 4: Commit**

```bash
git add README.md CHANGELOG.md .github/
git commit -m "docs: add README, CHANGELOG, and GitHub Actions release workflow"
```

---

### Task 11: Final Verification

- [ ] **Step 1: Run the full test suite**

```bash
cd cli && python -m pytest -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify CLI runs**

```bash
python -m docsend_to_pdf --version
python -m docsend_to_pdf --help
```

Expected: Version prints `0.1.0`. Help shows all options.

- [ ] **Step 3: Verify JSON output on invalid URL**

```bash
python -m docsend_to_pdf "https://google.com/foo" --json 2>/dev/null
```

Expected: `{"status": "error", "message": "Not a valid DocSend URL: https://google.com/foo"}`

- [ ] **Step 4: Verify project structure matches spec**

```bash
find . -name '*.py' -o -name '*.md' -o -name '*.json' -o -name '*.toml' -o -name '*.yml' -o -name '*.html' | sort
```

Verify all files from the spec's project structure exist.

- [ ] **Step 5: Verify plugin manifests are valid JSON and versions match**

```bash
python3 -c "
import json, re
# Check JSON validity
for f in ['.claude-plugin/plugin.json', '.cursor-plugin/plugin.json', 'marketplace.json']:
    data = json.load(open(f))
    print(f'{f}: version={data[\"version\"]}')

# Check SKILL.md metadata version
for f in ['docsend-to-pdf/skills/docsend-to-pdf/SKILL.md', '.agents/skills/docsend-to-pdf/SKILL.md']:
    text = open(f).read()
    m = re.search(r'version: \"(.+?)\"', text)
    print(f'{f}: version={m.group(1) if m else \"NOT FOUND\"}')

# Check pyproject.toml version
text = open('cli/pyproject.toml').read()
m = re.search(r'version = \"(.+?)\"', text)
print(f'cli/pyproject.toml: version={m.group(1) if m else \"NOT FOUND\"}')
print('All valid!')
"
```

All versions should show `0.1.0`.

- [ ] **Step 6: Commit any fixes**

If any verification step revealed issues, fix and commit.

---

### Task 12: Skill Eval and Description Optimization

Use the skill-creator-plus framework to verify trigger accuracy and optimize the description.

**Files:**
- Create: `evals/evals.json`

- [ ] **Step 1: Create test prompts**

Create `evals/evals.json` with realistic test queries — both should-trigger and should-not-trigger:

```json
{
  "skill_name": "docsend-to-pdf",
  "evals": [
    {
      "id": 1,
      "prompt": "here's the pitch deck from acme corp: https://docsend.com/view/abc123xyz",
      "expected_output": "CLI invoked with the URL, PDF downloaded or gate interaction started",
      "should_trigger": true
    },
    {
      "id": 2,
      "prompt": "can you download this deck and save it as a pdf? https://company.docsend.com/view/def456",
      "expected_output": "CLI invoked with subdomain URL",
      "should_trigger": true
    },
    {
      "id": 3,
      "prompt": "https://docsend.com/view/ghi789",
      "expected_output": "Skill triggers on bare URL without instructions",
      "should_trigger": true
    },
    {
      "id": 4,
      "prompt": "save this docsend as pdf, the passcode is 'secret123': https://docsend.com/view/jkl012",
      "expected_output": "CLI invoked with --passcode",
      "should_trigger": true
    },
    {
      "id": 5,
      "prompt": "check out this dropbox docsend link https://www.docsend.dropbox.com/view/mno345",
      "expected_output": "CLI invoked with dropbox variant URL",
      "should_trigger": true
    },
    {
      "id": 6,
      "prompt": "convert this papermark deck to pdf: https://papermark.io/view/abc123",
      "expected_output": "Should NOT trigger — Papermark is a different platform",
      "should_trigger": false
    },
    {
      "id": 7,
      "prompt": "download this google doc as pdf: https://docs.google.com/document/d/abc123",
      "expected_output": "Should NOT trigger — Google Docs, not DocSend",
      "should_trigger": false
    },
    {
      "id": 8,
      "prompt": "can you send a document via docsend for me?",
      "expected_output": "Should NOT trigger — user wants to SEND, not download",
      "should_trigger": false
    },
    {
      "id": 9,
      "prompt": "here's the pitch.com presentation: https://pitch.com/public/abc-123",
      "expected_output": "Should NOT trigger — Pitch.com, not DocSend",
      "should_trigger": false
    },
    {
      "id": 10,
      "prompt": "what is docsend and how does it work?",
      "expected_output": "Should NOT trigger — informational question, not a conversion request",
      "should_trigger": false
    }
  ]
}
```

- [ ] **Step 2: Review test prompts with user**

Present the 10 test queries to the user. Ask if they want to add, remove, or modify any. Incorporate feedback.

- [ ] **Step 3: Run skill trigger evaluation**

Use the skill-creator-plus eval framework to test each query against the skill's description. Verify:
- All should-trigger queries activate the skill
- All should-not-trigger queries do NOT activate the skill
- Record trigger rates

- [ ] **Step 4: Optimize description if needed**

If trigger accuracy is below 90%, run the skill-creator-plus description optimization loop:

```bash
python -m scripts.run_loop \
  --eval-set evals/evals.json \
  --skill-path docsend-to-pdf/skills/docsend-to-pdf \
  --model <model-id> \
  --max-iterations 5 \
  --verbose
```

Apply the `best_description` from the results to both the canonical and portable SKILL.md copies.

- [ ] **Step 5: Update portable copy if description changed**

If the description was optimized, sync the change to `.agents/skills/docsend-to-pdf/SKILL.md`.

- [ ] **Step 6: Commit**

```bash
git add evals/ docsend-to-pdf/ .agents/
git commit -m "test: add skill trigger evals and optimize description"
```
