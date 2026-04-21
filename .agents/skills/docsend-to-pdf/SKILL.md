---
name: docsend-to-pdf
description: >-
  Download a DocSend document (docsend.com/view/... or
  docsend.dropbox.com/view/...) as a PDF. Use when the user pastes a DocSend
  link and wants it saved, downloaded, archived, exported, or converted to a
  PDF. Slides are per-request signed images behind email/passcode/NDA/email-
  verification gates — curl/wget/HTML scraping won't work, so this skill
  drives a headless browser and handles the gates. Not for Papermark, Google
  Docs, Notion, Pitch.com, pptx, or existing PDFs.
metadata:
  version: "0.1.2"
---

# DocSend to PDF

Convert DocSend shared links to downloadable PDF files.

## Prerequisites

Check if the CLI is installed:

```bash
python -m docsend_to_pdf --version
```

If not installed, install from the cli/ directory in this repository (clone first if needed: `git clone https://github.com/yaniv-golan/docsend-to-pdf-skill && pipx install ./docsend-to-pdf-skill/cli/`). Try in order:

1. `pipx install <path-to-repo>/cli/`
2. `pip install --user <path-to-repo>/cli/`
3. `pip install <path-to-repo>/cli/`

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
| `complete` | Report success: "Downloaded <pages>-page deck to <output>". Mention the title if present. |
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
