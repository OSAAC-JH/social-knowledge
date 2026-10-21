"""Anonymous, bounded metadata adapters. No configuration, cookies or login import."""
import json
from pathlib import Path
import re
import subprocess
import sys


class ExtractionError(RuntimeError):
    def __init__(self, category, diagnostic):
        self.category = category
        self.diagnostic = diagnostic
        super().__init__(f"{category}:{diagnostic}")


def classify(text):
    text = text.lower()
    if "429" in text or "too many requests" in text:
        return "rate_limit"
    if any(word in text for word in ("login", "401", "403", "challenge", "checkpoint")):
        return "authentication_or_access"
    if any(word in text for word in ("connection", "resolve", "network", "proxy", "ssl", "timed out")):
        return "network"
    if "404" in text or "notfound" in text or "not found" in text:
        return "unavailable"
    return "extraction"


def diagnostic(text):
    # Never persist raw stderr: it can contain signed URLs, headers or cookies.
    if "redirect to login" in text.lower():
        return "login_redirect"
    codes = sorted(set(re.findall(r"\b(?:400|401|403|404|429|500|502|503)\b", text)))
    return "http_" + "_".join(codes) if codes else "provider_failed"


def parse_gallery(messages, code):
    if not isinstance(messages, list):
        raise ValueError("Expected a gallery-dl message list")
    media = []
    metadata = None
    for message in messages:
        # --dump-json embeds extraction errors and may still exit with status 0.
        if isinstance(message, list) and len(message) == 2 and message[0] == -1:
            error = message[1]
            if not isinstance(error, dict):
                raise ValueError("Invalid gallery-dl error")
            text = f"{error.get('error', '')} {error.get('message', '')}"
            raise ExtractionError(classify(text), diagnostic(text))
        if not isinstance(message, list) or len(message) != 3:
            raise ValueError("Invalid gallery-dl message")
        kind, url, data = message
        if not isinstance(data, dict) or not isinstance(url, str):
            raise ValueError("Invalid gallery-dl metadata")
        if kind not in (2, 3):
            raise ValueError("Unexpected gallery-dl message type")
        if data.get("post_shortcode") != code:
            raise ValueError("Unexpected post identity")
        metadata = metadata or data
        if kind == 3:
            media.append({"position": data["num"], "url": url,
                          "is_video": bool(data.get("video_url")),
                          "media_id": str(data["media_id"])})
    if not metadata or not media:
        raise ValueError("No post media in gallery-dl output")
    return {"caption": metadata.get("description"), "author": metadata.get("username"),
            "published": metadata.get("post_date"), "media": media,
            "expected_count": metadata.get("count"),
            "count_basis": "extractor_emitted_files"}


def extract(code, backend="gallery-dl", timeout=60):
    if backend == "gallery-dl":
        command = [sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
                   "--no-colors", "--no-postprocessors", "--dump-json", "--retries", "0",
                   "--http-timeout", "15", "--sleep-429", "0", "--cache-file", ":memory:",
                   "-o", "extractor.instagram.videos=false",
                   "-o", "extractor.instagram.previews=true",
                   f"https://www.instagram.com/p/{code}/"]
    elif backend == "instaloader":
        command = [sys.executable, str(Path(__file__).with_name("capture_instagram.py")),
                   "--extract-worker", code]
    else:
        raise ValueError("Unknown extractor")
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 encoding="utf-8", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError("timeout", "metadata_deadline") from exc
    if process.returncode:
        raise ExtractionError(classify(process.stderr), diagnostic(process.stderr))
    try:
        payload = json.loads(process.stdout)
        post = parse_gallery(payload, code) if backend == "gallery-dl" else payload
        if not isinstance(post, dict) or not isinstance(post.get("media"), list):
            raise ValueError("Invalid post payload")
    except (ValueError, TypeError, KeyError) as exc:
        raise ExtractionError("parsing", type(exc).__name__) from exc
    post["extractor_warnings"] = []
    if "missing media" in process.stderr.lower():
        post["extractor_warnings"].append("upstream_missing_media")
    return post
