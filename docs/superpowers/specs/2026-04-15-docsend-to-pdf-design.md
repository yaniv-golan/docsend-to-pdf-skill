# DocSend to PDF — Design Spec

**Date**: 2026-04-15
**Status**: Draft
**License**: MIT

## Overview

A Python CLI tool and Claude Code skill that reliably converts DocSend shared links into downloadable PDF files. The CLI handles all DocSend access gates (email, passcode, NDA, email verification) and produces image-based PDFs from DocSend's server-rendered page images. The skill wraps the CLI for conversational use, adding gate interaction UX and optional email integration for verification code retrieval.

## How DocSend Works

DocSend converts uploaded documents into per-page PNG images served from CloudFront CDN. The viewer is image-based — no PDF.js, no canvas, no selectable text in the DOM.

### Key endpoint

```
GET https://docsend.com/view/{id}/page_data/{page_number}
```

Returns JSON containing an `imageUrl` field pointing to a CloudFront-hosted PNG. This is an undocumented internal API used by the viewer itself. All existing tools exploit this endpoint.

### URL patterns

| Pattern | Description |
|---|---|
| `https://docsend.com/view/{id}` | Standard share link |
| `https://{subdomain}.docsend.com/view/{id}` | Custom subdomain |
| `https://*.docsend.dropbox.com/view/{id}` | Dropbox-branded variant |

### Access gates

| Gate | Detection | Bypass method |
|---|---|---|
| Email | Form with `link_auth_form[email]` | POST any email + CSRF token |
| Passcode | Form with `link_auth_form[passcode]` | POST passcode alongside email |
| NDA/Agreement | Agreement content block with accept button | POST acceptance |
| Email Verification | Verification code input after email submission | Submit code sent to email |
| Allowed Viewers | Error message after email submission | Requires whitelisted email (cannot bypass) |

Gates can be **chained** — a single link may require email, then NDA, then verification.

### Output characteristics

- Pages are RGBA PNGs (need compositing onto white background for PDF)
- No selectable text — output PDF is image-based
- OCR would be needed as a post-processing step for text extraction (out of scope)

## Architecture

Three layers, each independently testable.

### Layer 1: `client.py` — HTTP interaction with DocSend

Handles all communication with DocSend. Pure functions that take a `requests.Session` and return structured results. No file I/O.

**Functions:**

- `parse_url(url: str) -> DocSendURL` — validates and normalizes URL variants. Extracts document ID. Raises `ValueError` for invalid URLs.

- `fetch_page(session, url) -> PageResponse` — GET the view page. Returns parsed HTML with detected gate type and metadata (CSRF token, page count, document title).

- `detect_gate(html) -> Gate` — inspects response HTML and returns the active gate. `Gate` is a union type:
  - `Gate.NONE` — authenticated, ready to download
  - `Gate.EMAIL` — email form present
  - `Gate.PASSCODE` — passcode field present (alongside email)
  - `Gate.NDA(text: str)` — NDA content with agreement text
  - `Gate.VERIFICATION(email: str)` — verification code input
  - `Gate.REJECTED(message: str)` — not in allowed viewers list

- `submit_email(session, url, csrf_token, email, passcode=None) -> GateResult` — POST email/passcode form. Returns new gate state (may chain to another gate).

- `submit_verification(session, url, code) -> GateResult` — POST verification code.

- `accept_nda(session, url) -> GateResult` — POST NDA acceptance.

- `fetch_page_data(session, url, page_num) -> PageData` — GET `/page_data/{n}`. Returns `PageData(image_url=..., page_num=...)` or raises on non-200.

- `download_image(session, image_url) -> bytes` — fetch PNG bytes from CloudFront URL.

**Types:**

```python
@dataclass
class DocSendURL:
    original: str
    normalized: str  # https://docsend.com/view/{id}
    doc_id: str

@dataclass
class PageResponse:
    gate: Gate
    csrf_token: str
    title: str | None
    page_count: int | None  # None if not yet authenticated

@dataclass  
class PageData:
    image_url: str
    page_num: int

# GateResult is either Authenticated or NeedsInput
GateResult = Authenticated | NeedsInput

@dataclass
class Authenticated:
    csrf_token: str
    page_count: int  # Always known once authenticated (parsed from page HTML)

@dataclass
class NeedsInput:
    gate: Gate
```

### Layer 2: `pdf_builder.py` — Image processing and PDF assembly

- `process_image(png_bytes: bytes) -> Image` — load PNG, composite RGBA onto white RGB background.
- `build_pdf(images: list[Image], output_path: str) -> None` — assemble multi-page PDF using Pillow's `save(... save_all=True, append_images=...)`.

### Layer 3: `cli.py` — Orchestration and CLI interface

Drives the client through the gate state machine, handles two-phase resume, serializes/deserializes session state.

**CLI interface:**

```
docsend-to-pdf <url> [options]

Required:
  <url>                      DocSend URL (or omit if using --state-file to resume)

Authentication:
  --email <email>            Email for gate
  --passcode <code>          Passcode if link is passcode-protected
  --verification-code <c>    Email verification code (for Verified Visitors)
  --accept-nda               Accept NDA/agreement gate

Session (two-phase resume):
  --session <blob>           Resume with base64 session blob (from previous --json output)
  --state-file <path>        Persist session to file instead of blob.
                             Phase 1: writes state file on exit 2.
                             Phase 2: reads state file on resume (URL not needed).

Output:
  -o, --output <path>        Output PDF path (default: <doc-title>.pdf or docsend-<id>.pdf)
  --json                     Structured JSON output to stdout
  --quiet                    Suppress progress output

Info:
  --version                  Show version and exit
  --help                     Show help and exit
```

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success — PDF written |
| 1 | Error — network failure, auth rejected, invalid URL |
| 2 | Needs input — gate requires user-provided value |

**JSON output contract:**

Every invocation with `--json` produces exactly one JSON object on stdout:

```json
{"status": "complete", "pages": 12, "output": "deck.pdf", "title": "Series A Deck"}
```

```json
{"status": "needs_email", "session": "<b64>"}
```

```json
{"status": "needs_passcode", "session": "<b64>"}
```

```json
{"status": "needs_verification", "email": "me@co.com", "session": "<b64>"}
```

```json
{"status": "needs_nda", "nda_text": "By viewing this document you agree to...", "session": "<b64>"}
```

```json
{"status": "error", "message": "Link not found or expired"}
```

When `--state-file` is used, the `session` field is replaced with `"state_file": "/path/to/state.json"`.

**Session state blob:**

Base64-encoded JSON containing:

```json
{
  "url": "https://docsend.com/view/abc",
  "cookies": {"_docsend_session": "..."},
  "csrf_token": "...",
  "gates_cleared": ["email"],
  "pending_gate": "verification",
  "email": "me@co.com"
}
```

### Gate state machine

```
START
  |
  v
FETCH_PAGE --> detect gate
  |
  |-- no gate --> DOWNLOAD_PAGES --> BUILD_PDF --> DONE (exit 0)
  |
  |-- email/passcode gate
  |     |-- have --email (and --passcode if needed)? --> SUBMIT --> re-detect
  |     |-- missing? --> OUTPUT needs_email/needs_passcode (exit 2)
  |
  |-- nda gate
  |     |-- --accept-nda provided? --> ACCEPT --> re-detect
  |     |-- missing? --> OUTPUT needs_nda + nda_text (exit 2)
  |
  |-- verification gate
  |     |-- --verification-code provided? --> SUBMIT --> re-detect
  |     |-- missing? --> OUTPUT needs_verification (exit 2)
  |
  |-- rejected (not in allowed viewers) --> OUTPUT error (exit 1)
```

After clearing any gate, re-detect — there may be another gate behind it. Maximum 4 gate transitions before either authenticated or error (prevents infinite loops).

### Page download

Once authenticated:
1. Determine page count: parse from `.page-label` text (e.g., "12 of 12") in the authenticated page HTML. If not found, fall back to iterating `page_data/{n}` until non-200.
2. Fetch `page_data/{n}` for each page to get image URLs.
3. Download images in parallel (`ThreadPoolExecutor`, 4 workers).
4. Build PDF.

## Skill Layer

### Skill category

**Workflow Automation** — multi-step process (gate negotiation → download → assembly) with consistent methodology.

### Trigger description

```
Converts DocSend shared links to downloadable PDF files. Use when the user
shares a docsend.com or docsend.dropbox.com URL, asks to "download this
deck", "save this DocSend as PDF", "convert this DocSend link", or wants
to extract a document from DocSend. Also triggers on bare DocSend URLs
pasted without explicit instructions. Handles all access gates including
email, passcode, NDA acceptance, and email verification — can optionally
check user's connected email for verification codes with permission.
Does NOT handle Papermark, Google Docs, Pitch.com, or other document
sharing platforms.
```

### Skill flow

```
USER provides DocSend URL
  |
  v
CHECK CLI installed (python -m docsend_to_pdf --version)
  |-- not installed --> pip install from plugin's cli/ directory
  |
  v
INVOKE CLI (phase 1) via Bash with --json
  |
  v
Parse JSON output
  |
  |-- status: complete --> report success, mention output path
  |
  |-- status: needs_email --> ask user for email, re-invoke
  |
  |-- status: needs_passcode --> ask user for passcode, re-invoke
  |
  |-- status: needs_nda --> show NDA text, ask user to confirm, re-invoke with --accept-nda
  |
  |-- status: needs_verification
  |     |
  |     v
  |   Check if any email tool is available (Gmail MCP, Outlook MCP, etc.)
  |     |
  |     |-- email access available:
  |     |     Ask user: "DocSend sent a verification code to X.
  |     |               I can either:
  |     |               (A) You paste the code here
  |     |               (B) I check your email for the code (requires your approval)"
  |     |     |-- user pastes code --> re-invoke CLI with --verification-code
  |     |     |-- user approves (B) --> search email for DocSend verification,
  |     |                               extract code, re-invoke CLI
  |     |
  |     |-- no email access:
  |           Ask user to paste the code --> re-invoke CLI
  |
  |-- status: error --> report error to user
```

The skill treats email as a **capability it may or may not have** — not a specific integration. It checks for available email tools at runtime and adapts the UX accordingly.

### SKILL.md body content

The SKILL.md body must contain (this is what the LLM reads when the skill triggers):

1. **Prerequisites check** — exact Bash command to verify CLI is installed, and install command if missing. Must handle the case where `pip` targets a managed environment by falling back to `pipx` or `pip install --user`.

2. **Invocation template** — exact Bash command pattern:
   ```
   python -m docsend_to_pdf "<url>" --email "<email>" --json -o "<output>.pdf"
   ```

3. **JSON response handling** — for each `status` value, what the LLM should do next. This is a decision table, not prose:
   - `complete` → report output path and page count to user
   - `needs_email` → ask user for email, re-invoke with `--email` and `--session`
   - `needs_passcode` → ask user for passcode, re-invoke with `--passcode` and `--session`
   - `needs_nda` → show `nda_text` to user, ask for confirmation, re-invoke with `--accept-nda` and `--session`
   - `needs_verification` → offer email lookup or manual paste (see verification flow below)
   - `error` → report `message` to user

4. **Verification flow** — instructions for detecting available email tools and offering the user a choice. The skill should check its available tools list for any email-related MCP (search for tools containing "mail", "email", "inbox" in their names). If found, offer option B. If not, only offer option A.

5. **Error recovery** — if the CLI exits with code 1 and no JSON output, report the stderr to the user. Common causes: network timeout, invalid URL, Python dependency missing.

### references/cli-usage.md content

Full JSON contract documentation: every possible status value, all CLI flags, session blob format, state file format, and example invocations for each gate scenario. This file exists so the LLM can consult it for edge cases without bloating the SKILL.md.

### Skill file structure

```
docsend-to-pdf/
  skills/
    docsend-to-pdf/
      SKILL.md            # Trigger description + orchestration instructions
      references/
        cli-usage.md      # Full JSON contract and CLI reference
```

## Project Structure

```
docsend-to-pdf-skill/
|-- .claude-plugin/
|   |-- plugin.json                # Claude Code plugin manifest
|-- .cursor-plugin/
|   |-- plugin.json                # Cursor plugin manifest
|-- .agents/
|   |-- skills/
|       |-- docsend-to-pdf/        # Cross-platform portable copy
|           |-- SKILL.md           # Stripped of ${CLAUDE_PLUGIN_ROOT} paths
|           |-- references/
|               |-- cli-usage.md
|-- docsend-to-pdf/                # Plugin root (canonical copy)
|   |-- skills/
|       |-- docsend-to-pdf/
|           |-- SKILL.md
|           |-- references/
|               |-- cli-usage.md
|-- cli/                           # Python CLI tool
|   |-- docsend_to_pdf/
|   |   |-- __init__.py
|   |   |-- __main__.py            # Entry point (python -m docsend_to_pdf)
|   |   |-- cli.py                 # Click CLI, orchestration, session serialization
|   |   |-- client.py              # HTTP interaction with DocSend
|   |   |-- pdf_builder.py         # Image processing + PDF assembly
|   |-- pyproject.toml
|-- marketplace.json               # Claude marketplace distribution
|-- README.md
|-- CHANGELOG.md
|-- LICENSE                        # MIT
|-- .github/
    |-- workflows/
        |-- release.yml            # Tag-based release workflow
```

### Plugin manifests

**`.claude-plugin/plugin.json`:**

```json
{
  "name": "docsend-to-pdf",
  "version": "0.1.0",
  "description": "Convert DocSend links to PDF files",
  "skills": ["./docsend-to-pdf/skills"]
}
```

**`.cursor-plugin/plugin.json`:**

```json
{
  "name": "docsend-to-pdf",
  "version": "0.1.0",
  "description": "Convert DocSend links to PDF files",
  "skills": "./docsend-to-pdf/skills"
}
```

**`marketplace.json`:**

```json
{
  "name": "docsend-to-pdf-marketplace",
  "display_name": "DocSend to PDF",
  "description": "Convert DocSend shared links to downloadable PDF files with full gate handling",
  "version": "0.1.0",
  "author": "<author>",
  "license": "MIT",
  "plugins": [
    {
      "name": "docsend-to-pdf",
      "path": "./docsend-to-pdf"
    }
  ]
}
```

### `.agents/skills/` portable copy

The `.agents/skills/docsend-to-pdf/` directory is a **stripped copy** of the canonical skill:
- `${CLAUDE_PLUGIN_ROOT}` path references are replaced with relative paths or generic instructions
- `references/cli-usage.md` is included
- This copy works with any Agent Skills-compatible client (Codex CLI, `npx skills add`, etc.)

### Version management

Version appears in four places. All must stay in sync:
1. `cli/pyproject.toml` → `[project].version`
2. `.claude-plugin/plugin.json` → `version`
3. `.cursor-plugin/plugin.json` → `version`
4. `marketplace.json` → `version`

The GitHub Actions release workflow bumps all four from the git tag (e.g., tag `v0.2.0` sets version `0.2.0` everywhere).

### GitHub Actions release workflow

`release.yml` triggers on tag push (`v*`):
1. Validate tag format
2. Update version strings in all four locations from the tag
3. Build the CLI package (`python -m build cli/`)
4. Create a GitHub Release with:
   - The built CLI wheel as a release asset
   - A zip of the skill directory as a release asset
   - Auto-generated changelog from commits since last tag
5. (Optional) Publish to PyPI if configured

### README structure

The README must include:
- Title and badges (Agent Skills compatible, Claude Code plugin, Cursor plugin, MIT license)
- One-paragraph description
- **Installation** sections for each platform:
  - Claude Code: `claude plugin add <owner>/docsend-to-pdf-skill`
  - Cursor: install from `.cursor-plugin/`
  - Agent Skills / Codex CLI: `npx skills add <owner>/docsend-to-pdf-skill`
  - Standalone CLI: `pipx install ./cli` or `pip install ./cli`
- **Usage** — examples for CLI and skill trigger phrases
- **How it works** — brief explanation of the gate state machine
- **License** — MIT

### Key decisions

- **CLI lives in `cli/`**, installed via `pip install ./cli` or `pipx`. The skill invokes it via `python -m docsend_to_pdf` in Bash.
- **Skill is minimal** — SKILL.md contains trigger description and orchestration logic. No Python code in the skill itself.
- **`references/cli-usage.md`** documents the JSON contract so the LLM knows how to parse CLI output and construct resume commands.
- **Cross-platform `.agents/skills/`** copy strips plugin-root paths — portable across Claude Code, Cursor, Codex CLI.
- **Dual plugin manifests** — `.claude-plugin/` and `.cursor-plugin/` for both platforms.

### Dependencies

```toml
[project]
name = "docsend-to-pdf"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28",
    "Pillow>=9.0",
    "click>=8.0",
]

[project.scripts]
docsend-to-pdf = "docsend_to_pdf.cli:main"
```

### Auto-install from skill

The SKILL.md instructs the LLM to:
1. Check if CLI is installed: `python -m docsend_to_pdf --version`
2. If not, attempt install in order:
   - `pipx install <plugin-root>/cli/` (preferred — isolated environment)
   - `pip install --user <plugin-root>/cli/` (fallback)
   - `pip install <plugin-root>/cli/` (last resort)
   Report failure clearly if all attempts fail (e.g., managed Python environment without pipx).
3. Proceed with conversion

## Testing Strategy

### CLI unit tests

- `test_client.py` — URL parsing, gate detection from sample HTML, form submission mocking
- `test_pdf_builder.py` — RGBA→RGB compositing, multi-page PDF assembly
- `test_cli.py` — session serialization/deserialization, JSON output format, exit codes

### Integration tests

- Record DocSend responses (HTML + page_data JSON) as fixtures
- Replay against the client to test the full gate state machine
- Test chained gates (email → NDA → verification)

### Skill testing

- Use skill-creator-plus eval framework
- Test prompts: "download this docsend deck: https://docsend.com/view/xxx", "save this as PDF", "convert this DocSend link"
- Verify trigger accuracy and correct CLI invocation
