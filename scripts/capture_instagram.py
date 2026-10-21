#!/usr/bin/env python3
"""Capture an Instagram post into an OCR draft; never invent missing content."""
import argparse
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import logging
import tempfile
import time
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from instagram_extractors import ExtractionError, classify, extract

LOG = logging.getLogger("instagram_capture")


def canonical_url(value):
    parsed = urlsplit(value)
    match = re.fullmatch(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname not in {"instagram.com", "www.instagram.com"} or not match or parsed.port not in {None, 443} or parsed.username:
        raise ValueError("Expected an HTTPS Instagram post or reel URL")
    code = match.group(1)
    return code, f"https://www.instagram.com/p/{code}/"


def fetch_post(code):
    import instaloader
    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1,
                                    request_timeout=15)
    post = instaloader.Post.from_shortcode(loader.context, code)
    if post.typename == "GraphSidecar":
        media = [{"position": i, "url": n.display_url, "is_video": n.is_video,
                  "media_id": None}
                 for i, n in enumerate(post.get_sidecar_nodes(), 1)]
    else:
        media = [{"position": 1, "url": post.url, "is_video": post.is_video,
                  "media_id": str(post.mediaid)}]
    return {"caption": post.caption, "author": post.owner_username,
            "published": post.date_utc.date().isoformat(), "media": media,
            "expected_count": post.mediacount, "count_basis": "post_metadata"}


def bounded_post(code):
    return extract(code, "instaloader")


def image_bytes(url):
    # Instagram supplies these URLs, but limit requests to its media CDN.
    import requests
    host = urlsplit(url).hostname or ""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.port not in (None, 443) or not (host.endswith(".cdninstagram.com") or host.endswith(".fbcdn.net")):
        raise ValueError("Unexpected media CDN")
    with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("Unexpected HTTP status")
        if not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Media response is not an image")
        data = bytearray()
        started = time.monotonic()
        for chunk in response.iter_content(65536):
            if time.monotonic() - started > 60:
                raise TimeoutError("Image stream deadline exceeded")
            data.extend(chunk)
            if len(data) > 25 * 1024 * 1024:
                raise ValueError("Image exceeds 25 MiB")
        return bytes(data)


def validate_image(data):
    from PIL import Image
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            return {"width": image.width, "height": image.height, "format": image.format}


def ocr(data, language, psm=3):
    from PIL import Image, ImageOps
    import pytesseract
    available = set(pytesseract.get_languages(config=""))
    if not set(language.split("+")).issubset(available):
        raise RuntimeError("Required Tesseract language data is missing")
    with Image.open(BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return pytesseract.image_to_string(image, lang=language, config=f"--psm {psm}", timeout=45)


def capture(url, language="kor+eng", images=(), provider=bounded_post, reader=image_bytes, recognizer=ocr,
            asset_dir=None, backend="instaloader"):
    code, source_url = canonical_url(url)
    result = {"shortcode": code, "source_url": source_url, "caption": None,
              "extractor": "local" if images else backend, "expected_count": None,
              "count_basis": None, "capture_status": "incomplete", "review_status": "pending",
              "source_completeness": "not_independently_verified",
              "author": None, "published": None, "cards": [], "issues": [], "diagnostics": []}

    def issue(stage, category, position=None, detail=None):
        record = {"stage": stage, "category": category, "position": position, "detail": detail}
        result["diagnostics"].append(record)
        result["issues"].append(":".join(str(v) for v in (stage, category, position, detail) if v is not None))
        LOG.warning("stage=%s category=%s position=%s detail=%s", stage, category, position, detail)

    if images:
        media = [{"position": i, "local": str(path), "is_video": False}
                 for i, path in enumerate(images, 1)]
        result["count_basis"] = "user_supplied_unverified"
        issue("integrity", "source_completeness_unverified")
    else:
        try:
            post = provider(code)
            media = post["media"]
            for key in ("caption", "author", "published"):
                result[key] = post.get(key)
            result["expected_count"] = post.get("expected_count")
            result["count_basis"] = post.get("count_basis")
            for warning in post.get("extractor_warnings", []):
                issue("extraction", warning)
        except Exception as exc:
            issue("extraction", exc.category if isinstance(exc, ExtractionError) else classify(str(exc)),
                  detail=exc.diagnostic if isinstance(exc, ExtractionError) else type(exc).__name__)
            return result

    positions = [item.get("position") for item in media]
    expected = result["expected_count"]
    if not media or any(type(p) is not int or p < 1 for p in positions) or len(set(positions)) != len(positions):
        issue("integrity", "invalid_or_duplicate_positions")
        return result
    if expected is None:
        issue("integrity", "unknown_card_count")
    elif type(expected) is not int or expected < 1 or expected > 100:
        issue("integrity", "invalid_card_count")
        return result
    if len(media) > 100 or max(positions) > 100:
        issue("integrity", "media_limit")
        return result
    if expected is not None and set(positions) != set(range(1, expected + 1)):
        issue("integrity", "missing_or_unexpected_cards")
    elif sorted(positions) != list(range(1, len(media) + 1)):
        issue("integrity", "position_gap")
    seen_hashes = set()
    for item in sorted(media, key=lambda item: item["position"]):
        position = item["position"]
        card = {"position": position, "kind": "video_thumbnail" if item["is_video"] else "image",
                "provenance": {"source_url": source_url, "media_id": item.get("media_id"),
                               "origin": item.get("local") or item.get("url", "").split("?", 1)[0]},
                "text": None, "sha256": None, "download_status": "pending",
                "validation_status": "pending", "ocr_status": "not_run", "asset": None}
        result["cards"].append(card)
        if item["is_video"]:
            issue("capture", "video_transcription_pending", position)
        try:
            if "local" in item:
                path = Path(item["local"])
                if path.stat().st_size > 25 * 1024 * 1024:
                    raise ValueError("Image exceeds 25 MiB")
                data = path.read_bytes()
            else:
                data = reader(item["url"])
            card["download_status"] = "ok"
        except Exception as exc:
            card["download_status"] = "failed"
            issue("download", classify(str(exc)), position, type(exc).__name__)
            continue
        try:
            card.update(validate_image(data))
            card["validation_status"] = "ok"
            card["sha256"] = sha256(data).hexdigest()
            if card["sha256"] in seen_hashes:
                issue("integrity", "duplicate_image_bytes", position)
            seen_hashes.add(card["sha256"])
        except Exception as exc:
            card["validation_status"] = "failed"
            issue("media_validation", "invalid_image", position, type(exc).__name__)
            continue
        if asset_dir is not None:
            try:
                directory = Path(asset_dir)
                directory.mkdir(parents=True, exist_ok=True)
                extension = card["format"].lower()
                target = directory / f"card-{position:03d}-{card['sha256']}.{extension}"
                # Exclusive writes prevent silently replacing preserved evidence.
                with target.open("xb") as output:
                    output.write(data)
                card["asset"] = str(target.resolve())
            except Exception as exc:
                issue("persistence", "asset_write_failed", position, type(exc).__name__)
        else:
            issue("persistence", "original_not_preserved", position)
        try:
            card["text"] = recognizer(data, language)
            card["ocr_status"] = "ok" if card["text"].strip() else "blank"
            if not card["text"].strip():
                issue("ocr", "blank_text", position)
        except Exception as exc:
            card["ocr_status"] = "failed"
            category = "missing_language_data" if str(exc) == "Required Tesseract language data is missing" else "recognition_failed"
            issue("ocr", category, position, type(exc).__name__)
    if not result["issues"]:
        result["capture_status"] = "draft_captured_review_required"
    return result


def markdown(result, date):
    # JSON scalars are YAML-compatible, including multiline strings and colons.
    metadata = {"title": f"Instagram {result['shortcode']}", "source_type": "instagram",
                "source_url": result["source_url"], "captured": date, "topics": [],
                "content_type": [], "status": "inbox", "language": None,
                "source_assets": []}
    for key in ("author", "published"):
        if result.get(key):
            metadata[key] = result[key]
    front = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    sections = "\n".join(f"## {heading}\n\n검토 후 작성.\n" for heading in
                         ["Summary", "Key Points", "Key Claims", "Framework / Concepts", "Practical Implications", "Related Topics"])
    caption = result.get("caption")
    raw = "### Caption\n\n" + ("미확보" if caption is None else caption or "캡션 텍스트 없음 (추출기 응답).") + "\n\n"
    for card in result["cards"]:
        status = card["ocr_status"]
        text = card["text"] if status == "ok" else {
            "blank": "OCR 실행 완료: 인식된 텍스트 없음. 육안 검토 필요.",
            "failed": "OCR 실패: 텍스트 미확보.",
            "not_run": "OCR 미실행: 이미지 확보/검증 상태 확인 필요."}[status]
        raw += f"### Card {card['position']} ({card['kind']}, OCR: {status})\n\n{text}\n\n"
    issues = "\n".join(f"- {issue}" for issue in result["issues"]) or "- OCR 초안 확보; 육안 검토 필요."
    return f"---\n{front}\n---\n\n# {metadata['title']}\n\n{sections}\n## My Notes\n\n## Source\n\n- URL: {result['source_url']}\n\n## Capture Status\n\n{issues}\n\n## Raw Content\n\nOCR은 원본 이미지 자체가 아니며 오류가 있을 수 있습니다. 원본 자산 저장은 별도로 수행해야 합니다.\n\n{raw}"


def existing_notes(repo, code):
    source_url = f"https://www.instagram.com/p/{code}/"
    return [path for root in (repo / "inbox", repo / "sources") for path in root.rglob("*.md")
            if re.search(rf"_instagram_{re.escape(code)}(?:\.|_)", path.name)
            or source_url in path.read_text(encoding="utf-8")]


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--extract-worker":
        try:
            code, _ = canonical_url(f"https://www.instagram.com/p/{sys.argv[2]}/")
            print(json.dumps(fetch_post(code), ensure_ascii=True))
            return 0
        except Exception as exc:
            # Parent captures stderr and persists only the category + exception class/status.
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--lang", default="kor+eng")
    parser.add_argument("--images", type=Path, nargs="*", default=[])
    parser.add_argument("--extractor", choices=("gallery-dl", "instaloader"), default="instaloader")
    parser.add_argument("--psm", type=int, choices=(3, 6, 11), default=3, help="Tesseract segmentation mode")
    parser.add_argument("--probe", action="store_true", help="Save evidence only; do not create a note")
    parser.add_argument("--asset-dir", type=Path, default=Path(__file__).resolve().parents[1] / ".capture")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        code, _ = canonical_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    directory = args.asset_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{code}-{args.extractor}-", dir=directory))
    result = capture(args.url, args.lang, args.images,
                     provider=lambda code: extract(code, args.extractor),
                     asset_dir=run_dir, backend=args.extractor,
                     recognizer=lambda data, lang: ocr(data, lang, args.psm))
    result["ocr_config"] = {"language": args.lang, "psm": args.psm}
    (run_dir / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    print(f"Evidence: {run_dir}", file=sys.stderr)
    if args.probe:
        return 2 if result["issues"] else 0
    inbox = args.repo / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    # Reuse the original capture date to avoid duplicate captures of the same post.
    matches = existing_notes(args.repo, result["shortcode"])
    if matches:
        print("Existing capture retained; review/merge extraction explicitly.", file=sys.stderr)
        return 3
    date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    path = inbox / f"{date}_instagram_{result['shortcode']}.md"
    with path.open("x", encoding="utf-8") as output:
        output.write(markdown(result, date))
    print(path)
    return 2 if result["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
