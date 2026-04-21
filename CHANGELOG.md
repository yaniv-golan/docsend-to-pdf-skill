# Changelog

## [0.1.2] - 2026-04-21

### Fixed
- Repo layout now matches the Claude Code marketplace spec: `marketplace.json` moved to `.claude-plugin/marketplace.json`, and `plugin.json` moved into the plugin directory at `docsend-to-pdf/.claude-plugin/plugin.json`. 0.1.1 could not be installed via `claude plugin marketplace add` because Claude Code looks for `.claude-plugin/marketplace.json` at the repo root.
- `marketplace.json` rewritten to the current schema (`owner`, `metadata.pluginRoot`, `plugins[].source` instead of the legacy `plugins[].path`), matching the sibling papermark-to-pdf layout.
- `plugin.json` `skills` path corrected from `./docsend-to-pdf/skills` to `./skills` (relative to the plugin root, which is now `docsend-to-pdf/`).
- Release workflow paths updated to the new file locations.

## [0.1.1] - 2026-04-21

### Changed
- Skill description rewritten in the same style as sibling `papermark-to-pdf`: outcome-first opening, technical "why" that preempts curl/wget/scraping attempts, and a crisp exclusion list (Papermark, Google Docs, Notion, Pitch.com, pptx, existing PDFs). 593 → 485 chars (-18%).

## [0.1.0] - 2026-04-15

### Added
- Initial release
- Python CLI tool with all DocSend gate types (email, passcode, NDA, verification, allowed viewers)
- Two-phase resumable design (session blob and state file modes)
- Structured JSON output for programmatic use
- Claude Code skill with conversational gate handling
- Optional email integration for verification code retrieval
- Cross-platform packaging (Claude Code, Cursor, Agent Skills)
