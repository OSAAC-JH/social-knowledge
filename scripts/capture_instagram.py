#!/usr/bin/env python3
"""Capture Instagram image cards as an unreviewed OCR draft, without invention."""
import argparse
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
MAX_IMAGE_BYTES = 25 * 1024 * 1024


def canonical_url(value):
    parsed = urlsplit(value)
    match = re.fullmatch(r"/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/?", parsed.path)
    if (parsed.scheme != "https" or parsed.hostname not in {"instagram.com", "www.instagram.com"}
            or not match or parsed.port not in {None, 443} or parsed.username):
        raise ValueError("Expected an HTTPS Instagram post or reel URL")
    kind, code = match.groups()
    kind = "reel" if kind == "reels" else kind
    return code, f"https://www.instagram.com/{kind}/{code}/"


def fetch_post(code, source_url, directory, runner=subprocess.run):
    """Use gallery-dl's maintained Instagram extractor; download one image per card.

    Video posts yield their preview image only. No credentials or downloader
    configuration are loaded implicitly. Sidecars associate order and metadata.
    """
    command = [sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
               "--quiet", "--retries", "1", "--http-timeout", "20",
               "--filesize-max", "25m", "--directory", str(directory),
               "--filename", "{num:03}_{media_id}.{extension}",
               "--write-metadata", "--option", "extractor.instagram.videos=false",
               "--option", "extractor.instagram.previews=video",
               source_url]
    completed = runner(command, capture_output=True, text=True, timeout=300)
    media = []
    issues = []
    metadata = []
    for sidecar in sorted(directory.glob("*.json")):
        target = sidecar.with_suffix("")
        if target.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        try:
            info = json.loads(sidecar.read_text(encoding="utf-8"))
            position = info["num"]
            if (not isinstance(position, int) or isinstance(position, bool)
                    or not 1 <= position <= 30 or info.get("post_shortcode") != code):
                raise ValueError("Invalid image position or mismatched shortcode")
        except (ValueError, KeyError, TypeError, OSError) as exc:
            issues.append(f"invalid_metadata:{sidecar.name}:{type(exc).__name__}")
            continue
        metadata.append(info)
        media.append({"position": position, "local": target,
                      "is_video": bool(info.get("video_url")),
                      "media_id": str(info.get("media_id", ""))})
    if completed.returncode:
        issues.append(f"gallery_dl_exit:{completed.returncode}")
    if not media:
        raise RuntimeError("No verified Instagram media metadata/files were extracted")
    if len({item["position"] for item in media}) != len(media):
        issues.append("duplicate_media_positions")
        # Do not silently invent or overwrite the ambiguous ordering.
        media = list({item["position"]: item for item in media}.values())
    first = metadata[0]
    counts = {entry.get("count") for entry in metadata if type(entry.get("count")) is int}
    expected = next(iter(counts)) if len(counts) == 1 else None
    if expected is None or not 1 <= expected <= 30:
        issues.append("expected_card_count_unverified")
        expected = None
    caption = first.get("description")
    if not isinstance(caption, str):
        caption = None
        issues.append("caption_unverified")
    date = str(first.get("post_date") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        date = None
    media.sort(key=lambda item: item["position"])
    return {"caption": caption, "author": first.get("username"),
            "published": date, "media": media, "expected_cards": expected,
            "issues": issues}


def ocr(data, language):
    from PIL import Image, ImageOps
    import pytesseract
    available = set(pytesseract.get_languages(config=""))
    if not set(language.split("+")).issubset(available):
        raise RuntimeError("Required Tesseract language data is missing")
    with Image.open(BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return pytesseract.image_to_string(image, lang=language, timeout=45)


def capture(url, language="kor+eng", images=(), provider=fetch_post, recognizer=ocr):
    code, source_url = canonical_url(url)
    result = {"shortcode": code, "source_url": source_url, "caption": None,
              "author": None, "published": None, "expected_cards": None,
              "cards": [], "issues": []}
    with TemporaryDirectory(prefix="instagram-capture-") as temporary:
        if images:
            media = [{"position": i, "local": Path(path), "is_video": False,
                      "media_id": None} for i, path in enumerate(images, 1)]
            result["expected_cards"] = len(media)
            result["issues"].append("manual_assets_source_unverified")
        else:
            try:
                post = provider(code, source_url, Path(temporary))
                media = post["media"]
                for key in ("caption", "author", "published", "expected_cards"):
                    result[key] = post.get(key)
                result["issues"].extend(post.get("issues", []))
            except Exception as exc:
                result["issues"].append(f"capture_failed:{type(exc).__name__}")
                return result
        seen = set()
        for item in sorted(media, key=lambda item: item["position"]):
            position = item["position"]
            if position in seen:
                result["issues"].append(f"duplicate_card:{position}")
                continue
            seen.add(position)
            card = {"position": position,
                    "kind": "video_thumbnail" if item["is_video"] else "image",
                    "media_id": item.get("media_id"), "sha256": None,
                    "text": "", "media_status": "missing", "ocr_status": "not_run"}
            if item["is_video"]:
                result["issues"].append(f"video_transcription_pending:{position}")
            try:
                path = Path(item["local"])
                if path.stat().st_size > MAX_IMAGE_BYTES or path.stat().st_size == 0:
                    raise ValueError("Image empty or exceeds 25 MiB")
                data = path.read_bytes()
                card["sha256"] = sha256(data).hexdigest()
                card["media_status"] = "downloaded"
            except (OSError, ValueError) as exc:
                result["issues"].append(f"media_unavailable:{position}:{type(exc).__name__}")
                result["cards"].append(card)
                continue
            try:
                card["text"] = recognizer(data, language)
                card["ocr_status"] = "text" if card["text"].strip() else "blank"
                if card["ocr_status"] == "blank":
                    result["issues"].append(f"empty_ocr:{position}")
            except Exception as exc:
                card["ocr_status"] = "failed"
                result["issues"].append(f"ocr_failed:{position}:{type(exc).__name__}")
            result["cards"].append(card)
        expected = result["expected_cards"]
        if expected is None:
            result["issues"].append("card_count_unverified")
        else:
            for position in sorted(set(range(1, expected + 1)) - seen):
                result["issues"].append(f"missing_card:{position}")
            if len(seen) != expected:
                result["issues"].append(f"incomplete_media:{len(seen)}/{expected}")
        if not result["cards"]:
            result["issues"].append("no_cards_collected")
    return result


def markdown(result, date):
    metadata = {"title": f"Instagram {result['shortcode']}", "source_type": "instagram",
                "source_url": result["source_url"], "captured": date,
                "topics": [], "content_type": [], "status": "inbox",
                "language": None, "source_assets": []}
    for key in ("author", "published"):
        if result.get(key):
            metadata[key] = result[key]
    front = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    sections = "\n".join(f"## {heading}\n\n검토 후 작성.\n" for heading in
                         ["Summary", "Key Points", "Key Claims", "Framework / Concepts",
                          "Practical Implications", "Related Topics"])
    caption = result.get("caption")
    raw = "### Caption\n\n" + (caption if caption is not None else "미확보") + "\n\n"
    for card in result["cards"]:
        raw += (f"### Card {card['position']} ({card['kind']}, OCR)\n\n"
                f"- Media ID: {card['media_id'] or '미확보'}\n"
                f"- SHA-256: {card['sha256'] or '미확보'}\n"
                f"- Media: {card['media_status']}; OCR: {card['ocr_status']}\n\n"
                + (card["text"] or "확인된 OCR 텍스트 없음") + "\n\n")
    issues = "\n".join(f"- {issue}" for issue in result["issues"]) or "- OCR 초안 확보; 육안 검토 필요."
    count = result["expected_cards"] if result["expected_cards"] is not None else "미확인"
    return (f"---\n{front}\n---\n\n# {metadata['title']}\n\n{sections}"
            f"\n## My Notes\n\n## Source\n\n- URL: {result['source_url']}\n"
            f"\n## Capture Status\n\n- Expected cards: {count}\n- Collected cards: {len(result['cards'])}\n"
            f"{issues}\n\n## Raw Content\n\n"
            "OCR은 원본 이미지가 아니며 오류가 있을 수 있습니다. 원본 자산의 Drive 저장은 미구현입니다.\n\n"
            f"{raw}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--lang", default="kor+eng")
    parser.add_argument("--images", type=Path, nargs="*", default=[])
    parser.add_argument("--refresh", action="store_true",
                        help="Re-extract for inspection even if an inbox/source note exists")
    args = parser.parse_args()
    try:
        code, _ = canonical_url(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    inbox = args.repo / "inbox"
    source_dir = args.repo / "sources" / "instagram"
    matches = sorted(inbox.glob(f"*_instagram_{code}.md")) + sorted(
        source_dir.glob(f"*_instagram_{code}.md"))
    if matches and not args.refresh:
        print(f"Existing note retained: {matches[0]}. Use --refresh for inspection.",
              file=sys.stderr)
        return 3
    result = capture(args.url, args.lang, args.images)
    if matches:
        print("Existing note retained; review/merge extraction explicitly.", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3
    inbox.mkdir(parents=True, exist_ok=True)
    date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    path = inbox / f"{date}_instagram_{code}.md"
    with path.open("x", encoding="utf-8") as output:
        output.write(markdown(result, date))
    print(path)
    return 2 if result["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
