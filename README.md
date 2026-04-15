# DocSend to PDF

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/docsend-to-pdf-skill/static/install-claude-desktop.html)

[![PyPI version](https://img.shields.io/pypi/v/docsend-to-pdf.svg)](https://pypi.org/project/docsend-to-pdf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Agent Skills Compatible](https://img.shields.io/badge/Agent_Skills-compatible-4A90D9)](https://agentskills.io)
[![Claude Code Plugin](https://img.shields.io/badge/Claude_Code-plugin-F97316)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/plugins)
[![Cursor Plugin](https://img.shields.io/badge/Cursor-plugin-00D886)](https://cursor.com/docs/plugins)

Convert any DocSend shared link into a downloadable PDF — handling all access gates automatically.

Uses the open [Agent Skills](https://agentskills.io) standard. Works with Claude Desktop, Claude Code, Cursor, Codex CLI, Manus, and other compatible agents.

## What It Does

- Accepts any DocSend URL (`docsend.com/view/`, `/v/` short links, custom subdomains)
- Handles all access gates: email, passcode, NDA acceptance, email verification
- Downloads page images via DocSend's internal API and composites them into a multi-page PDF
- Two-phase resumable design for programmatic use (session blob or state file)
- Detects and rejects non-document links (Spaces/folders, video documents)

## Installation

### Claude Desktop

[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://yaniv-golan.github.io/docsend-to-pdf-skill/static/install-claude-desktop.html)

*— or install manually —*

1. Click **Customize** in the sidebar
2. Click **Browse Plugins**
3. Go to the **Personal** tab and click **+**
4. Choose **Add marketplace**
5. Type `yaniv-golan/docsend-to-pdf-skill` and click **Sync**

### Claude Code (CLI)

```bash
claude plugin marketplace add https://github.com/yaniv-golan/docsend-to-pdf-skill
claude plugin install docsend-to-pdf@docsend-to-pdf-marketplace
```

Or from within a Claude Code session:

```
/plugin marketplace add yaniv-golan/docsend-to-pdf-skill
/plugin install docsend-to-pdf@docsend-to-pdf-marketplace
```

### Any Agent (npx)

Works with Claude Code, Cursor, Copilot, Windsurf, and [40+ other agents](https://github.com/vercel-labs/skills):

```bash
npx skills add yaniv-golan/docsend-to-pdf-skill
```

### Cursor

1. Open **Cursor Settings**
2. Paste `https://github.com/yaniv-golan/docsend-to-pdf-skill` into the **Search or Paste Link** box

### Claude.ai (Web)

1. Download [`docsend-to-pdf.zip`](https://github.com/yaniv-golan/docsend-to-pdf-skill/releases/latest/download/docsend-to-pdf-skill.zip)
2. Click **Customize** in the sidebar → **Skills** → **+** → **Upload a skill**

### Manus

1. Download [`docsend-to-pdf.zip`](https://github.com/yaniv-golan/docsend-to-pdf-skill/releases/latest/download/docsend-to-pdf-skill.zip)
2. Go to **Settings** → **Skills** → **+ Add** → **Upload**
3. Upload the zip

### Codex CLI

```
$skill-installer https://github.com/yaniv-golan/docsend-to-pdf-skill
```

Or install manually:

1. Download [`docsend-to-pdf.zip`](https://github.com/yaniv-golan/docsend-to-pdf-skill/releases/latest/download/docsend-to-pdf-skill.zip)
2. Extract the `docsend-to-pdf/` folder to `~/.codex/skills/`

### Other Tools (Windsurf, etc.)

Download [`docsend-to-pdf.zip`](https://github.com/yaniv-golan/docsend-to-pdf-skill/releases/latest/download/docsend-to-pdf-skill.zip) and extract the `docsend-to-pdf/` folder to:

- **Project-level**: `.agents/skills/` in your project root
- **User-level**: `~/.agents/skills/`

### Standalone CLI (no agent)

```bash
pipx install docsend-to-pdf
```

or

```bash
pip install docsend-to-pdf
```

## Prerequisites

The skill installs the CLI on first run, but your machine needs:

- Python 3.9+
- pip or pipx

## Usage

The skill auto-activates when you share a DocSend link. Examples:

```
Here's the investor deck: https://docsend.com/view/abc123 — can you save it as a PDF?
```

```
Download https://docsend.com/v/2w8kc/mononio-ai-investor-deck as PDF
```

```
https://docsend.com/view/xyz789 → PDF please
```

The skill will handle email gates, passcodes, NDA acceptance, and verification codes interactively.

### Standalone CLI

```bash
# Basic download (no gate)
docsend-to-pdf https://docsend.com/view/abc123 -o deck.pdf

# With email gate
docsend-to-pdf https://docsend.com/view/abc123 --email you@example.com -o deck.pdf

# JSON output for scripting
docsend-to-pdf https://docsend.com/view/abc123 --email you@example.com --json -o deck.pdf
```

## Access Gates

| Gate | Handled | CLI Flag |
|---|---|---|
| Email | Yes | `--email` |
| Passcode | Yes | `--passcode` |
| NDA | Yes | `--accept-nda` |
| Email Verification | Yes | `--verification-code` |
| Allowed Viewers | Detected | Reports rejection clearly |

## GitHub Pages

To enable the "Install in Claude Desktop" button, go to repo Settings → Pages → Source: GitHub Actions.

## License

MIT
