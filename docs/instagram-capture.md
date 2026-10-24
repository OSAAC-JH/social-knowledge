# Instagram capture MVP - gallery-dl image/carousel path

## Scope and status (2026-10-24)

The capture pipeline uses gallery-dl to fetch Instagram post image files and metadata,
then verifies ordered card positions, hashes local image bytes and attempts Korean/English
Tesseract OCR. It generates a **pending-review** Markdown note. This extractor upgrade
has **only passed offline mocked tests**; real Instagram downloads and Korean OCR quality
have not been validated in the execution environment.

This is not the same thing as successfully capturing
https://www.instagram.com/p/Del83xLEzc9/ . That post remains in
`inbox/2026-10-21_instagram_Del83xLEzc9.md` pending real media evidence.

## Why gallery-dl rather than yt-dlp for images?

- **gallery-dl** implements Instagram media, caption/author metadata, carousels and ordered
  media indices (`num`). It is the default path for photos and image cards.
- **yt-dlp** focuses on video and audio. Image-only Instagram carousels are out of its
  official scope, per its upstream issue #17077 (June 2026).
- For the present MVP, `gallery-dl` downloads **image previews of video cards** and sets
  `video_transcription_pending`. Full Reels/video processing with yt-dlp,
  frame sampling and audio transcription is a separate future stage.
- Both tools may fail without authentication; the pipeline must report access errors
  instead of fabricating captions, media or OCR. No third-party downloader sites are
  called and no credentials are silently requested.

## Setup

Python 3.10+:

    python -m pip install -r scripts/requirements-instagram.txt

Install Tesseract separately with Korean and English language packs
(Ubuntu: `tesseract-ocr`, `tesseract-ocr-kor`, `tesseract-ocr-eng`).
A network-enabled environment may be required to access permitted public content.

## Usage

    python scripts/capture_instagram.py "https://www.instagram.com/p/Del83xLEzc9/" --repo .

If a note already exists, the command exits early without downloading it. To re-extract
without overwriting the existing note:

    python scripts/capture_instagram.py "https://www.instagram.com/p/Del83xLEzc9/" --repo . --refresh

If the original Instagram post cannot be accessed, an operator can supply real
downloaded image files in the correct card order. Such manually supplied images
are **not automatically treated as proven Instagram source assets**:

    python scripts/capture_instagram.py "https://www.instagram.com/p/ABC123/" --images card01.jpg card02.jpg

The `--images` mode does not automatically prove total card count, caption or authorship.

## Flow and integrity guarantees

1. Normalize post/reel URL (strip query parameters, reject unrelated hosts/paths).
2. Check existing `inbox/` and `sources/instagram/` shortcode-named notes **before**
   making network requests; never silently replace existing `My Notes`.
3. Run `gallery-dl` as a bounded subprocess with an isolated configuration,
   short retry budget, a per-image size limit, no interactive prompts and a temporary
   download directory.
4. For each matching sidecar metadata file, map `num`, `media_id`, post shortcode,
   expected card count, username, date and original caption into a structured record.
5. Classify extractor errors (`rate_limited`, `authentication_or_access_denied`,
   `network_error`, `extractor_or_parsing_error`) without persisting raw stderr.
6. Compare expected and collected positions; distinguish `missing_card` from
   `empty_ocr`, `media_unavailable`, `ocr_failed` and missing caption metadata.
7. Compute SHA-256 over downloaded bytes and attempt OCR; preserve the OCR result
   separately from caption and source metadata. Keep incomplete results in `inbox`.
8. Review captured images and claims before any promotion to `sources/instagram/`.

Missing media, zero OCR text and failed OCR are separate conditions.
A successful OCR subprocess is **not** proof that its text matches the image.
Image files are currently temporary and **not** durably uploaded to Google Drive.
The `source_assets` metadata list must remain empty until durable upload is implemented.
Instagram CDN URLs must not be treated as durable source asset links.

The output records the identified media index and SHA-256 but does not embed the image
bytes. Sidecar count/metadata behavior and partial media/video posts still require live
integration tests. A metadata sidecar without the corresponding image file is an error.

## Verification

Offline tests (fixtures are synthetic, not a transcription of the real Instagram URL):

    python -m unittest discover -s tests -v

As of 2026-10-24: six offline unit tests passed against the refactored capture script.
No real post media was downloaded or OCR-validated. The execution environment lacked
`gallery_dl` and `yt_dlp` and could not clone GitHub by direct network connection.
Run an authenticated *only if explicitly authorized* real-world test under a separate
operator-controlled environment, keeping browser cookies and session secrets out of Git.

Exit statuses:
- `0`: local OCR draft without reported capture errors, still subject to review.
- `2`: capture incomplete or failed, pending review.
- `3`: an existing shortcode-named note was retained (no write).
- Invalid URL: argument error, no note written.

## Remaining work

- Install gallery-dl in an environment allowed to access Instagram and execute the
  test URL; collect sanitized diagnostics distinguishing rate limiting, login,
  parsing and media-download failures.
- Validate gallery-dl's metadata sidecars, card count and filenames on real
  mixed-media Instagram carousels.
- Visually verify Korean/English OCR per actual image, not synthetic fixtures.
- Implement secure temporary-to-Google-Drive binary retention with provenance and
  reliable deduplication. Keep assets and credentials out of Git.
- Add optional yt-dlp Reels/video stage with timestamped frames, audio transcription
  and fallback reporting. Do not confuse a video thumbnail with full transcription.

References:
- https://github.com/mikf/gallery-dl
- https://github.com/yt-dlp/yt-dlp
- https://github.com/yt-dlp/yt-dlp/issues/17077
- https://github.com/madmaze/pytesseract

## Real URL attempt - 2026-10-24

URL: https://www.instagram.com/p/De4D0QcD6nY/

The test command was invoked on a local runtime. Direct Instagram DNS lookup failed
(`curl: (6) Could not resolve host: www.instagram.com`). The runtime also had no
installed `gallery_dl` module; the capture command exited 2 with 0 cards,
`gallery_dl_exit:1:unknown_error`, and `no_media_extracted`. There was no
image file, so no real post OCR, transcription review or caption could be
performed. This is **not** a verified capture and must not be promoted.

The capture script now supports `--asset-dir DIR` to preserve downloaded image
bytes and a per-card `card-XX.ocr.txt` next to them, with SHA-256 recorded in
the report. `--report FILE` saves machine-readable capture outcomes. Images
are validated by Pillow before processing. `verification_status: not_reviewed`
is the only automatic result; human comparison is necessary to mark verified.

Verified offline: `python -m unittest discover -s tests -v` passed 7 tests,
including a synthetic *valid image* end-to-end byte persistence and OCR-text
persistence test. None of these synthetic fixtures represents the target post.

Example command after installing dependencies and gaining legitimate network
access:

    python scripts/capture_instagram.py \
      https://www.instagram.com/p/De4D0QcD6nY/ \
      --repo . --asset-dir ../instagram-assets/De4D0QcD6nY \
      --report ../instagram-assets/De4D0QcD6nY/capture-report.json

The `--asset-dir` path must remain outside version control. Google Drive
upload remains a separate unfinished integration.
