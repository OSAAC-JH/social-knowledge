# Instagram capture pipeline

URL → selected extractor → ordered media → bounded download → image validation → local source preservation → Korean/English OCR → inbox draft → human review.

Instaloader remains the default after the [real comparison](instagram-capture-test-report-2026-10-21.md): it downloaded all 7 target images while anonymous gallery-dl redirected to login. gallery-dl is an implemented alternative, not a proven replacement. Backends are explicit; no silent fallback or authentication. Video/Reels work with yt-dlp is deferred; thumbnails always retain `video_transcription_pending`.

## Setup and run

Use Python 3.10+, a virtual environment, and `python -m pip install -r scripts/requirements-instagram.txt`. Install Tesseract separately with `kor` and `eng`; verify using `tesseract --list-langs`. Ubuntu packages: `tesseract-ocr`, `tesseract-ocr-kor`, `tesseract-ocr-eng`. Windows installs the declared tzdata dependency for Asia/Seoul dates.

```sh
python scripts/capture_instagram.py https://www.instagram.com/p/Del83xLEzc9/ --extractor instaloader --probe
python scripts/capture_instagram.py https://www.instagram.com/p/Del83xLEzc9/ --extractor gallery-dl --probe
```

`--probe` saves evidence without creating notes. Omit it to create an inbox draft. Existing notes in both `inbox/` and `sources/` are detected by shortcode filename or canonical source URL, including renamed notes. They are retained without merging or overwriting My Notes. Notes are never automatically promoted or marked processed.

Each run creates `.capture/<shortcode>-<backend>-<random>/` with exact original bytes and `manifest.json`. `.capture/` is ignored by Git. `--asset-dir PATH` selects another location; keep it outside Git or explicitly ignored. Keep manifests with their images. Local originals are not Drive uploads; `source_assets` remains empty until durable storage is performed separately.

Local input: `python scripts/capture_instagram.py URL --images card01.png card02.png --probe --psm 6`. Argument order is retained, but source completeness is unverified. Supplying two images does not establish the post's card count. gallery-dl ignores user configuration, uses an in-memory cache and never executes configured postprocessors. No browser-cookie/session import is implemented.

## Integrity and diagnostics

- Metadata runs in subprocesses with a 60-second deadline on Windows and Unix; library requests have 15-second timeouts and bounded retries. Timeout terminates the child, including rate-controller waits.
- Downloads allow only HTTPS Instagram/Facebook media CDN subdomains, reject redirects, require HTTP 200 and image MIME, and enforce a 25 MiB limit. Connect/read timeouts are 10/30 seconds; a stream elapsed-time check runs at 60 seconds. A slow read can extend that check by the read timeout. This is a per-image bound, not a whole-carousel deadline; at most 100 positions are accepted.
- Pillow verifies and fully decodes images before OCR. Decompression bomb warnings become errors. The manifest retains source URL, media ID when available, query-free CDN origin, position, dimensions, format, SHA-256 and local asset path. Signed CDN queries and raw provider stderr are not persisted.
- Numeric positions are sorted without renumbering gaps. Count mismatches, duplicate positions/bytes, unknown count and missing media are issues. Failed cards remain present with OCR `not_run`.
- Instaloader count comes from post metadata. gallery-dl count is its emitted-file count and may already exclude unavailable media; its `Missing media` warning is retained. Neither proves independent source completeness. `source_completeness` remains unverified and `review_status` pending.
- Structured diagnostics distinguish extraction/parsing, authentication/access, network, rate limit, timeout, download, validation, integrity, persistence and OCR. gallery-dl can exit 0 with an embedded JSON error; that is a failure.
- OCR states `ok`, `blank`, `failed`, `not_run` differ. `ok` means nonempty output, not accurate transcription. `--psm 3` is default; 6 and 11 are available. Missing language data is distinct from recognition failure. Missing content is never filled with generated prose.

Exit codes: 0 = evidence/draft captured, still requiring review; 2 = partial/failed capture or invalid URL; 3 = existing note retained. The execution host may display nonzero CLI codes as 1; these are the Python return values.

## Tests and curation

```sh
python -m unittest discover -s tests -v
# POSIX opt-in:
SK_RUN_INSTAGRAM_INTEGRATION=1 python -m unittest discover -s tests -v
```

PowerShell: set `$env:SK_RUN_INSTAGRAM_INTEGRATION='1'` before unittest. Live tests contact Instagram/CDNs and run Tesseract. External access blocks are **skipped**, not passed; parsing/validation failures fail. Temporary live downloads are removed; use `--probe` for retained evidence. Offline tests generate synthetic bytes and mock OCR, establishing no facts about a real post. Live tests check execution, not OCR accuracy; visual findings are reported separately.

Review every OCR card against its original, preserve corrections separately from raw OCR, upload assets to durable storage, then populate `source_assets`. Apply canonical taxonomy before explicitly moving inbox work to `sources/instagram/`. Drive upload, automatic curation, OCR confidence/character-error benchmarking and video transcription remain unimplemented.

## Primary references

- [gallery-dl Instagram extractor](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/extractor/instagram.py)
- [gallery-dl JSON job contract](https://github.com/mikf/gallery-dl/blob/master/gallery_dl/job.py)
- [gallery-dl configuration](https://github.com/mikf/gallery-dl/blob/master/docs/configuration.rst)
- [Instaloader structures](https://instaloader.github.io/module/structures.html)
- [pytesseract](https://github.com/madmaze/pytesseract)
