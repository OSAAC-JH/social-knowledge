"""Offline tests use generated image bytes and mocked OCR, never real post claims."""
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_instagram as capture
from instagram_extractors import ExtractionError, classify, diagnostic, extract, parse_gallery

URL = "https://www.instagram.com/p/TESTfixture/"


def png(color="red"):
    output = BytesIO()
    Image.new("RGB", (16, 16), color).save(output, "PNG")
    return output.getvalue()


def media(position, color="red"):
    return {"position": position, "url": color, "is_video": False}


class CaptureTests(unittest.TestCase):
    def run_capture(self, items=None, count=2, reader=None, recognizer=None, **kwargs):
        post = {"media": items if items is not None else [media(2, "blue"), media(1)],
                "expected_count": count, "count_basis": "fixture"}
        return capture.capture(URL, provider=lambda code: post, reader=reader or png,
                               recognizer=recognizer or (lambda data, lang: "MOCK OCR"), **kwargs)

    def test_canonical_url(self):
        self.assertEqual(capture.canonical_url(URL + "?img_index=2")[1], URL)

    def test_reject_invalid_urls(self):
        for url in ("http://www.instagram.com/p/x/", "https://instagram.com.evil/p/x/",
                    "https://user@instagram.com/p/x/", "https://instagram.com:444/p/x/",
                    "https://instagram.com/explore/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture.canonical_url(url)

    def test_order_hash_and_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_capture(asset_dir=directory)
            self.assertEqual([c["position"] for c in result["cards"]], [1, 2])
            self.assertFalse(result["issues"])
            for card in result["cards"]:
                self.assertEqual(capture.sha256(Path(card["asset"]).read_bytes()).hexdigest(), card["sha256"])
            self.assertEqual(result["review_status"], "pending")

    def test_missing_card(self):
        result = self.run_capture(items=[media(1), media(3)], count=3)
        self.assertIn("integrity:missing_or_unexpected_cards", result["issues"])

    def test_unknown_count(self):
        result = self.run_capture(count=None)
        self.assertIn("integrity:unknown_card_count", result["issues"])

    def test_duplicate_positions_reject_before_download(self):
        reader = Mock()
        result = self.run_capture(items=[media(1), media(1)], reader=reader)
        self.assertIn("integrity:invalid_or_duplicate_positions", result["issues"])
        reader.assert_not_called()

    def test_duplicate_bytes(self):
        result = self.run_capture(items=[media(1), media(2)])
        self.assertIn("integrity:duplicate_image_bytes:2", result["issues"])

    def test_corrupt_image_never_ocr(self):
        recognizer = Mock()
        result = self.run_capture(reader=lambda _: b"<html>login</html>", recognizer=recognizer)
        recognizer.assert_not_called()
        self.assertEqual(result["cards"][0]["validation_status"], "failed")
        self.assertIsNone(result["cards"][0]["text"])

    def test_truncated_image(self):
        with self.assertRaises(Exception):
            capture.validate_image(png()[:40])

    def test_download_failure_not_ocr_failure(self):
        result = self.run_capture(reader=Mock(side_effect=TimeoutError("timed out")))
        self.assertEqual(result["cards"][0]["download_status"], "failed")
        self.assertTrue(any(d["stage"] == "download" for d in result["diagnostics"]))
        self.assertFalse(any(d["stage"] == "ocr" for d in result["diagnostics"]))

    def test_blank_and_failed_ocr_differ(self):
        blank = self.run_capture(recognizer=lambda *_: "")
        failed = self.run_capture(recognizer=Mock(side_effect=RuntimeError("missing kor")))
        self.assertEqual(blank["cards"][0]["ocr_status"], "blank")
        self.assertEqual(failed["cards"][0]["ocr_status"], "failed")
        self.assertIn("인식된 텍스트 없음", capture.markdown(blank, "2026-10-21"))
        self.assertIn("OCR 실패", capture.markdown(failed, "2026-10-21"))

    def test_extraction_error_does_not_invent_content(self):
        result = capture.capture(URL, provider=Mock(side_effect=ExtractionError("network", "provider_failed")))
        self.assertEqual(result["cards"], [])
        self.assertIsNone(result["caption"])

    def test_video_remains_incomplete(self):
        result = self.run_capture(items=[dict(media(1), is_video=True)], count=1)
        self.assertIn("capture:video_transcription_pending:1", result["issues"])

    def test_existing_sources_note_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            note = root / "sources" / "instagram" / "renamed.md"
            note.parent.mkdir(parents=True)
            note.write_text(f"source_url: {URL}\n## My Notes\nkeep me", encoding="utf-8")
            self.assertEqual(capture.existing_notes(root, "TESTfixture"), [note])
            self.assertIn("keep me", note.read_text(encoding="utf-8"))

    def test_local_images_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.png"
            path.write_bytes(png())
            result = capture.capture(URL, images=[path], recognizer=lambda *_: "MOCK OCR")
            self.assertEqual(result["count_basis"], "user_supplied_unverified")
            self.assertEqual(result["capture_status"], "incomplete")

    def test_cdn_allowlist_before_request(self):
        for url in ("https://evil.com/a", "https://x.cdninstagram.com.evil/a",
                    "https://user@x.cdninstagram.com/a", "http://x.fbcdn.net/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                capture.image_bytes(url)

    def test_nonimage_http_response(self):
        response = Mock(status_code=200, headers={"Content-Type": "text/html"})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch("requests.get", return_value=response) as get, self.assertRaises(ValueError):
            capture.image_bytes("https://x.cdninstagram.com/a")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])


class ExtractorTests(unittest.TestCase):
    def fixture(self, position=1):
        return {"post_shortcode": "TESTfixture", "num": position, "count": 1,
                "media_id": "synthetic-id", "description": "fixture caption", "username": "fixture"}

    def test_gallery_contract(self):
        data = self.fixture()
        result = parse_gallery([[2, "", data], [3, "https://x.cdninstagram.com/a", data]], "TESTfixture")
        self.assertEqual(result["expected_count"], 1)
        self.assertEqual(result["media"][0]["position"], 1)

    def test_gallery_embedded_login_error_exit_zero(self):
        output = [[-1, {"error": "AbortExtraction", "message": "HTTP redirect to login page (https://secret)"}]]
        process = subprocess.CompletedProcess([], 0, json.dumps(output), "")
        with patch("instagram_extractors.subprocess.run", return_value=process), self.assertRaises(ExtractionError) as raised:
            extract("TESTfixture")
        self.assertEqual(raised.exception.category, "authentication_or_access")
        self.assertEqual(raised.exception.diagnostic, "login_redirect")
        self.assertNotIn("secret", str(raised.exception))

    def test_wrong_identity_rejected(self):
        with self.assertRaises(ValueError):
            parse_gallery([[3, "url", self.fixture()]], "another-post")

    def test_empty_gallery_rejected(self):
        with self.assertRaises(ValueError):
            parse_gallery([], "TESTfixture")

    def test_process_deadline_on_both_backends(self):
        for backend in ("gallery-dl", "instaloader"):
            with self.subTest(backend=backend), patch("instagram_extractors.subprocess.run", side_effect=subprocess.TimeoutExpired([], 1)), self.assertRaises(ExtractionError) as raised:
                extract("TESTfixture", backend, timeout=1)
            self.assertEqual(raised.exception.category, "timeout")

    def test_invalid_json_is_parsing_failure(self):
        process = subprocess.CompletedProcess([], 0, "<html>", "")
        with patch("instagram_extractors.subprocess.run", return_value=process), self.assertRaises(ExtractionError) as raised:
            extract("TESTfixture")
        self.assertEqual(raised.exception.category, "parsing")

    def test_failure_categories_and_redaction(self):
        for message, category in (("HTTP 429", "rate_limit"), ("HTTP 403", "authentication_or_access"),
                                  ("ConnectionError", "network"), ("404 Not Found", "unavailable")):
            self.assertEqual(classify(message), category)
        self.assertEqual(diagnostic("HTTP 403 https://signed?token=secret"), "http_403")


@unittest.skipUnless(os.environ.get("SK_RUN_INSTAGRAM_INTEGRATION") == "1", "opt-in real network/OCR integration")
class LiveIntegrationTests(unittest.TestCase):
    def check_backend(self, backend):
        with tempfile.TemporaryDirectory() as directory:
            result = capture.capture("https://www.instagram.com/p/Del83xLEzc9/",
                                     provider=lambda code: extract(code, backend),
                                     backend=backend, asset_dir=directory)
            blocked = {"authentication_or_access", "network", "rate_limit", "timeout", "unavailable"}
            if result["diagnostics"] and result["diagnostics"][0]["stage"] == "extraction" and result["diagnostics"][0]["category"] in blocked:
                self.skipTest(json.dumps(result["diagnostics"][0]))
            self.assertTrue(result["cards"], result["issues"])
            self.assertEqual(len(result["cards"]), result["expected_count"])
            self.assertEqual([c["position"] for c in result["cards"]], list(range(1, len(result["cards"]) + 1)))
            for card in result["cards"]:
                self.assertEqual(card["validation_status"], "ok")
                self.assertEqual(capture.sha256(Path(card["asset"]).read_bytes()).hexdigest(), card["sha256"])
                self.assertIn(card["ocr_status"], ("ok", "blank"))
            # A passing integration run establishes execution, never OCR accuracy or review.
            self.assertEqual(result["review_status"], "pending")

    def test_gallery_live(self):
        self.check_backend("gallery-dl")

    def test_instaloader_live(self):
        self.check_backend("instaloader")


if __name__ == "__main__":
    unittest.main()
