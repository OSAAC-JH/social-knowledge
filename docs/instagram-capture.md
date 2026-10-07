# Instagram capture MVP

URL → Instaloader metadata and ordered media → image bytes in memory → Tesseract OCR → inbox Markdown → Work review → GitHub Source Note.

This implements an independent extractor, not FastVideoSave's undocumented backend. Public availability does not guarantee anonymous requests will work from a sandbox. HTTP 200 can contain a login page instead of usable media metadata. Login, rate limits and network restrictions remain possible. Failures are recorded without fabricating content or retrying indefinitely.

## Setup and run

Install Python 3.10+ dependencies with `python -m pip install -r scripts/requirements-instagram.txt`. Install the Tesseract executable and Korean/English language data separately (Ubuntu packages: `tesseract-ocr`, `tesseract-ocr-kor`, `tesseract-ocr-eng`). No GPU is required.

Run `python scripts/capture_instagram.py https://www.instagram.com/p/DeJswa7k5zE/ --repo .`.

Fallback: `python scripts/capture_instagram.py URL --repo . --images card01.png card02.png`. Images are processed in the explicit argument order. Use this if the source is blocked. No cookies or passwords are required or stored by this MVP.

Exit 0: OCR draft captured (still requires review). Exit 2: partial/failed capture saved. Exit 3: existing inbox note retained; new extraction is printed for explicit merging. Invalid URLs exit 2 before creating a note.

## Work execution and persistence

1. Fetch the script and requirements from GitHub into a runtime that supports Python execution and outbound Instagram/CDN connections. Repository storage alone does not create an executable tool or remove network restrictions.
2. Run capture. Inspect the issues and ordered cards. OCR output is a transcription candidate, not the original binary or a verified claim.
3. Preserve original images/PDFs separately in Drive and fill `source_assets` with durable references. This MVP processes image bytes in memory and does not upload assets to Drive. CDN URLs expire and must not be used as permanent asset references.
4. Generate Summary/Claims separately from Raw Content; map topics against `taxonomy/topics.yml` and `taxonomy/aliases.yml`.
5. If all expected media and raw content are accounted for, save a completed note in `sources/instagram/` and remove/migrate the inbox note with GitHub connector operations or a local Git commit. If incomplete, retain `status: inbox`. Respect existing user notes and review changes before replacing content.

The capture script writes a local draft only. It does not push Git commits, call a summarization API, assign taxonomy or automatically mark `processed`. Work performs those steps using the existing repository rules. Keep downloaded binaries and credentials out of Git.

## Reels

Video posts currently OCR only the thumbnail and report `video_transcription_pending`. Full reels require video download, sampled frames plus OCR, audio transcription and timestamp alignment. A thumbnail is never treated as the full video transcript.

## References

- https://instaloader.github.io/as-module.html
- https://instaloader.github.io/module/structures.html
- https://github.com/madmaze/pytesseract
- https://fastvideosave.net/photo/
