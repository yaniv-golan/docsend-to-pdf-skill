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
```

### Email gate — two phases

```bash
# Phase 1: discover gate
python -m docsend_to_pdf "https://docsend.com/view/abc123" --json

# Phase 2: provide email
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --session "eyJ1cmwiOi..." --json -o deck.pdf
```

### Email + verification — three phases

```bash
# Phase 1: provide email, hits verification
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --json

# Phase 2: provide verification code
python -m docsend_to_pdf --session "eyJ1cmwiOi..." --verification-code "123456" --json -o deck.pdf
```

### NDA gate

```bash
# Phase 1: hits NDA
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --json

# Phase 2: accept NDA
python -m docsend_to_pdf --session "eyJ1cmwiOi..." --accept-nda --json -o deck.pdf
```

### Using state file instead of blob

```bash
# Phase 1
python -m docsend_to_pdf "https://docsend.com/view/abc123" --email "me@co.com" --state-file /tmp/ds.json --json

# Phase 2 (URL not needed — stored in state file)
python -m docsend_to_pdf --state-file /tmp/ds.json --verification-code "123456" --json -o deck.pdf
```
