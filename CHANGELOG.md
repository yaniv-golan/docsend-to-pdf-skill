# Changelog

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
