# Codex instructions - Social Knowledge

## Project
Markdown-first personal knowledge repository. The canonical repository is `OSAAC-JH/social-knowledge`. GitHub stores Markdown, metadata, taxonomy, templates and scripts; Google Drive is intended for durable binary source assets; Obsidian is an optional local interface.

Read and follow these files before changing the capture pipeline:
1. `PROJECT.md`
2. `WORK_INSTRUCTIONS.md`
3. `taxonomy/schema.yml`, `taxonomy/topics.yml`, `taxonomy/aliases.yml`
4. `templates/source-note.md`
5. `scripts/capture_instagram.py`, `scripts/requirements-instagram.txt`
6. `docs/instagram-capture.md`

## Non-negotiable data-integrity rules
- Preserve original source content separately from AI summaries, key claims and interpretation.
- Never invent missing caption, card images, dates, OCR results or author information.
- A test image or synthetic OCR sample MUST NOT be represented as content from an Instagram post.
- Source notes use YAML frontmatter. Keep existing metadata rules and the filename pattern `YYYY-MM-DD_source_short-title.md`.
- Use existing canonical taxonomy topics and aliases before proposing new ones.
- `inbox` means incomplete or pending review. Never mark `processed` unless source capture and processing were actually completed and verified.
- Preserve any existing user notes (`My Notes`) and guard against duplication across both `inbox/` and `sources/`.
- Do not commit secrets, session cookies, authentication tokens, or raw binary downloads into Git. Requiring user credentials is not a permissible silent workaround.
- Work with legally accessible content and respect site restrictions. Do not rely on undocumented third-party downloader APIs as stable integrations.

## Immediate development task: Instagram carousel capture reliability
Test URL: `https://www.instagram.com/p/Del83xLEzc9/`.
Current tracking note: `inbox/2026-10-21_instagram_Del83xLEzc9.md`.
The post's real images, full caption, card count and OCR have NOT yet been verified. The note was corrected to remove an unrelated synthetic OCR claim. Do not assert that the post was captured.

1. Inspect the current Instaloader-based capture pipeline and reproduce failures with bounded requests and diagnostic logs in an environment that genuinely has external network access.
2. Evaluate the actively maintained open-source `gallery-dl` extractor as the primary candidate for image/carousel capture. Keep Instaloader as a possible fallback only if testing supports it; evaluate `yt-dlp` separately for future video/Reels needs. Downloader websites such as FastDL, IGExport, and SnapInsta are references for publicly advertised behavior, NOT verified reusable backend APIs.
3. Keep capture, integrity validation, OCR, curation and persistence as distinguishable steps. Preserve exact card order, count if discoverable, image provenance and SHA-256. Distinguish missing cards from blank OCR.
4. Validate Korean+English OCR against REAL captured card images. Use synthetic samples for isolated tests only and report them distinctly.
5. Add unit tests with fixtures/mocks and, where possible, a bounded real-world integration test. Separate network/authentication failures from parsing, download, media-validation and OCR failures.
6. Write a truthful test report stating environment, commands, tests passed/failed, what was actually downloaded, and outstanding limitations.
7. Only promote a verified post from `inbox/` to a `sources/instagram/` note after proper source preservation, analysis and review. Durable Drive asset upload is NOT yet implemented; do not claim it is.
8. Prefer a focused PR for the extractor upgrade rather than silently changing the main branch.

## Development phases
- Phase 1: One real Instagram carousel, URL -> ordered images -> Korean OCR -> source preservation -> reviewed Markdown -> GitHub, with honest partial-failure reporting.
- Phase 2: Reusable, testable workflow with duplicate prevention, idempotency and error recovery.
- Phase 3: Validate the workflow on 25-30 real content items across Instagram, Threads, LinkedIn, YouTube and websites/newsletters/blogs before broad automation.
- Phase 4: Schema validator, warning-first CI, Obsidian integration and eventual Insight Note candidates.

## Reporting
At the end of a task summarize changed files, test evidence, caveats, and PR/commit links. Distinguish implemented, tested, untested and blocked results.
