# Instagram verification — 2026-10-21 (Asia/Seoul)

Target: https://www.instagram.com/p/Del83xLEzc9/

## Environment and baseline

Windows, Python 3.11.15; gallery-dl 1.32.17; Instaloader 4.15.4; Pillow 12.3.0; pytesseract 0.3.13; requests 2.34.2; Tesseract 5.5.3.20260724 with `kor` and `eng`. Dependencies are in repository-local `.venv`.

Initial sandbox git clone could not connect to GitHub port 443. Approved external-network execution subsequently cloned GitHub, installed PyPI dependencies and reached Instagram/CDNs. The live results are actual external requests, not mocks or a network-isolated failure. No credentials, browser cookies or third-party downloader services were used.

The original pipeline used Instaloader only, joined OCR/download errors, held originals in memory, had no full image decode/count manifest, and only a Unix metadata alarm. Duplicate prevention searched only inbox shortcode filenames. The original tracking note recorded an unverified capture. This run adds evidence without promoting that note.

## Extractor comparison

Commands (Windows uses `.venv\Scripts\python`):

```sh
python scripts/capture_instagram.py https://www.instagram.com/p/Del83xLEzc9/ --extractor gallery-dl --probe
python scripts/capture_instagram.py https://www.instagram.com/p/Del83xLEzc9/ --extractor instaloader --probe
```

| Backend | Actual result | Images | Interpretation |
|---|---|---:|---|
| gallery-dl | Embedded AbortExtraction: HTTP redirect to login page | 0 | `authentication_or_access:login_redirect`; blocked |
| Instaloader | Caption, author/date metadata, 7 image entries; all downloaded/decoded | 7 | Real capture succeeded; OCR incomplete |

gallery-dl exited 0 despite its embedded error. The first adapter run misclassified this as parsing failure; it now recognizes embedded errors, covered by a regression test. An initial Instaloader adapter change accessed nonexistent `PostSidecarNode.mediaid`, failing before download. It now explicitly stores null ID for sidecars. Successful capture and subsequent tests used that correction, preserving sidecar order and CDN provenance.

Decision: retain Instaloader as default based on actual results; offer gallery-dl explicitly for further evaluation. Successful gallery-dl extraction remains unverified. No authentication workaround was attempted.

## Card order and integrity

Instaloader declared 7 media entries; positions 1–7 are contiguous. All 7 returned image MIME, decoded as JPEG and have distinct SHA-256 hashes. Exact bytes and original caption were preserved under ignored local `.capture/Del83xLEzc9-instaloader-80oqp17v/` with manifest.json. A local contact sheet `.capture/real-contact-sheet.jpg` was inspected: cover followed by visible page numbers 1, 2, 3, 4, 5, 6, agreeing with extraction order. No missing card was detected relative to metadata count. Independent browser/UI verification of platform count was not performed.

| Position | Dimensions | SHA-256 | Default OCR |
|---:|---|---|---|
| 1 | 2160×2700 | `69628daab0b8c4f4d04b9768107f77b591280b3d96bf3759cd58969114195aaf` | blank |
| 2 | 1206×1507 | `1592d40bb936f48d0b5fe7e2a5b9d401c9c2dc93a38aa94106f19a8d27429238` | nonempty, errors |
| 3 | 1206×1507 | `85a58683768879fd5995901a87b6e26bc7f20dfc6fa21d1ba2dc19d7dffa6953` | nonempty, errors |
| 4 | 1206×1507 | `885c0d05e30ef49795bc578f82a31ce28efac971f7c344f88ccda6aec4fd33e9` | nonempty, omissions |
| 5 | 1206×1507 | `22d3ad5c2f8f20d0e57d2d370729ebe8a8f0dd5c250b056e6a3dd9c14f230cf5` | nonempty, omissions |
| 6 | 1206×1507 | `859980a6594ede138508fe0d2e44e89206cffbed8b4a1b03021bcaaa267fbad7` | nonempty, omissions |
| 7 | 1206×1507 | `f85ee11424d981c68c1a6a2ed8f2ff104505366fcf874cf3313561b98dbe6e78` | nonempty, errors |

Original images are deliberately not committed. Hashes and reproducible commands are evidence, not durable binary hosting. Drive upload is not implemented or performed.

## Korean OCR visual comparison

Real `kor+eng`, PSM 3 ran on all 7 originals. Card 1 returned empty text despite its visible title: an OCR detection failure, not a missing or genuinely blank image. Cards 2–7 returned text, which was visually compared with all images:

- Card 2 confuses mixed Korean/English Open AI and the ownership heading; English quotations are partly preserved.
- Card 3 has character errors in the low-ego heading; body structure is mostly recognizable.
- Cards 4–6 contain highlighted passages that default segmentation partly omits/fragments despite legible originals.
- Card 7 introduces stray characters and drops part of the opening line.

A separate comparison ran `pytesseract.image_to_string(image, lang="kor+eng", config="--psm 6", timeout=45)` on the same preserved originals. Unchanged outputs are in `.capture/psm6-comparison.json`. PSM 6 recovered substantially more paragraph text on cards 4–7, including card 7's opening line. It still confused AI, Korean characters and arrows; cover text remained noisy. This is qualitative visual comparison, not a measured accuracy score or corrected transcript. `--psm 6` is exposed as an option; PSM 3 stays default pending broader evaluation. No synthetic OCR is represented as this post's content and no generated text fills gaps.

The post remains inbox/pending review. No verified full transcription, summary or curation is claimed.

## Automated test evidence

```sh
python -m unittest discover -s tests -v
# PowerShell opt-in:
$env:SK_RUN_INSTAGRAM_INTEGRATION='1'
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
git diff --check
```

Offline: **24 passed, 2 opt-in live tests skipped** (26 discovered). Mocked tests cover gallery JSON mapping, embedded exit-0 error, wrong identity, malformed/empty JSON, backend deadlines, URL/CDN validation, decoding/corruption, original-byte/hash preservation, numeric order, missing/duplicate positions, unknown count, duplicate images, local provenance limits, download/OCR/blank states, video incompleteness and renamed source-note detection.

Live opt-in: **25 passed, 1 skipped** (26 discovered). Instaloader integration passed count/order, original decoding, preserved-file hash equality and Korean/English OCR execution. gallery-dl was skipped specifically for `authentication_or_access:login_redirect`: blocked, not passed. Blank OCR is allowed by the execution test and still recorded as an issue; passing execution does not certify transcription accuracy. Compilation and whitespace checks passed.

## Remaining limitations

- gallery-dl successful extraction/download is fixture-tested only; live access is blocked at login. Its count is computed after extraction and cannot independently establish completeness.
- Anonymous access is unstable; one successful Instaloader post proves no broad reliability guarantee.
- Full OCR correctness remains unverified. Every card still needs reviewed transcription, especially cover/highlighted passages. PSM comparison output is separate from raw capture.
- No Drive assets, reviewed Source Note, Reels transcription or yt-dlp evaluation is claimed in this focused image-extractor change.
- Local notes are never overwritten/automatically promoted; My Notes remain intact.
