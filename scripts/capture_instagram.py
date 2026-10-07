#!/usr/bin/env python3
"""Capture an Instagram post into an OCR draft; never invent missing content."""
import argparse
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


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
        media = [{"url": n.display_url, "is_video": n.is_video}
                 for n in post.get_sidecar_nodes()]
    else:
        media = [{"url": post.url, "is_video": post.is_video}]
    return {"caption": post.caption or "", "author": post.owner_username,
            "published": post.date_utc.date().isoformat(), "media": media}


def image_bytes(url):
    # Instagram supplies these URLs, but limit requests to its media CDN.
    import requests
    host = urlsplit(url).hostname or ""
    if urlsplit(url).scheme != "https" or not (host.endswith(".cdninstagram.com") or host.endswith(".fbcdn.net")):
        raise ValueError("Unexpected media CDN")
    with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Media response is not an image")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 25 * 1024 * 1024:
                raise ValueError("Image exceeds 25 MiB")
        return bytes(data)


def ocr(data, language):
    from PIL import Image, ImageOps
    import pytesseract
    available = set(pytesseract.get_languages(config=""))
    if not set(language.split("+")).issubset(available):
        raise RuntimeError("Required Tesseract language data is missing")
    with Image.open(BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return pytesseract.image_to_string(image, lang=language, timeout=45)


def capture(url, language="kor+eng", images=(), provider=fetch_post, reader=image_bytes, recognizer=ocr):
    code, source_url = canonical_url(url)
    result = {"shortcode": code, "source_url": source_url, "caption": "",
              "author": None, "published": None, "cards": [], "issues": []}
    if images:
        media = [{"local": str(path), "is_video": False} for path in images]
    else:
        try:
            post = provider(code)
            media = post["media"]
            for key in ("caption", "author", "published"):
                result[key] = post.get(key)
        except Exception as exc:
            result["issues"].append(f"capture_failed:{type(exc).__name__}")
            return result
    for position, item in enumerate(media, 1):
        card = {"position": position, "kind": "video_thumbnail" if item["is_video"] else "image", "text": "", "sha256": None}
        if item["is_video"]:
            result["issues"].append(f"video_transcription_pending:{position}")
        try:
            data = Path(item["local"]).read_bytes() if "local" in item else reader(item["url"])
            card["sha256"] = sha256(data).hexdigest()
            card["text"] = recognizer(data, language)
            if not card["text"].strip():
                result["issues"].append(f"empty_ocr:{position}")
        except Exception as exc:
            result["issues"].append(f"ocr_or_download_failed:{position}:{type(exc).__name__}")
        result["cards"].append(card)
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
    raw = "### Caption\n\n" + (result.get("caption") or "미확보") + "\n\n"
    for card in result["cards"]:
        raw += f"### Card {card['position']} ({card['kind']}, OCR)\n\n" + (card["text"] or "추출 실패 또는 텍스트 없음") + "\n\n"
    issues = "\n".join(f"- {issue}" for issue in result["issues"]) or "- OCR 초안 확보; 육안 검토 필요."
    return f"---\n{front}\n---\n\n# {metadata['title']}\n\n{sections}\n## My Notes\n\n## Source\n\n- URL: {result['source_url']}\n\n## Capture Status\n\n{issues}\n\n## Raw Content\n\nOCR은 원본 이미지 자체가 아니며 오류가 있을 수 있습니다. 원본 자산 저장은 별도로 수행해야 합니다.\n\n{raw}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--lang", default="kor+eng")
    parser.add_argument("--images", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    try:
        result = capture(args.url, args.lang, args.images)
    except ValueError as exc:
        parser.error(str(exc))
    inbox = args.repo / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    # Reuse the original capture date to avoid duplicate captures of the same post.
    matches = list(inbox.glob(f"*_instagram_{result['shortcode']}.md"))
    if matches:
        print("Existing capture retained; review/merge extraction explicitly.", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3
    date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    path = inbox / f"{date}_instagram_{result['shortcode']}.md"
    with path.open("x", encoding="utf-8") as output:
        output.write(markdown(result, date))
    print(path)
    return 2 if result["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
