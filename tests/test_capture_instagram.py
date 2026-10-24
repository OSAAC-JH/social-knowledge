"""Offline tests: synthetic media is never a claim about a real post."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "capture_instagram.py"
spec = importlib.util.spec_from_file_location("capture_instagram", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureTest(unittest.TestCase):
    def test_url_normalizes_and_preserves_media_type(self):
        self.assertEqual(module.canonical_url(
            "https://www.instagram.com/p/Del83xLEzc9/?img_index=2"),
            ("Del83xLEzc9", "https://www.instagram.com/p/Del83xLEzc9/"))
        self.assertEqual(module.canonical_url(
            "https://www.instagram.com/reels/ABc123/"),
            ("ABc123", "https://www.instagram.com/reel/ABc123/"))
        for url in ("http://www.instagram.com/p/Abc/",
                    "https://example.com/p/Abc/",
                    "https://www.instagram.com/p/Abc/../../etc/passwd"):
            with self.assertRaises(ValueError):
                module.canonical_url(url)

    def test_gallery_metadata_and_order(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            def runner(command, **kwargs):
                self.assertIn("--config-ignore", command)
                self.assertIn("extractor.instagram.videos=false", command)
                self.assertIn("extractor.instagram.previews=video", command)
                for pos in (2, 1):
                    prefix = base / f"{pos:03}_media{pos}.jpg"
                    prefix.write_bytes(b"image" + str(pos).encode())
                    Path(str(prefix) + ".json").write_text(json.dumps({
                        "num": pos, "count": 2, "post_shortcode": "ABC",
                        "description": "Synthetic sample - not from Instagram",
                        "post_date": "2026-10-21T00:00:00", "username": "tester",
                        "media_id": f"media{pos}", "video_url": None,
                    }), encoding="utf-8")
                return SimpleNamespace(returncode=0, stderr="")
            result = module.fetch_post("ABC", "https://www.instagram.com/p/ABC/",
                                       base, runner=runner)
            self.assertEqual([x["position"] for x in result["media"]], [1, 2])
            self.assertEqual(result["expected_cards"], 2)
            self.assertEqual(result["caption"], "Synthetic sample - not from Instagram")
            self.assertEqual(result["issues"], [])

    def test_auth_failure_is_classified_without_leaking_stderr(self):
        with tempfile.TemporaryDirectory() as temp:
            result = module.fetch_post("ABC", "https://www.instagram.com/p/ABC/",
                                       Path(temp), runner=lambda *a, **kw: SimpleNamespace(
                                           returncode=1, stderr="Login required: cookie 123456"))
            self.assertEqual(result["media"], [])
            self.assertIn("no_media_extracted", result["issues"])
            self.assertIn("gallery_dl_exit:1:authentication_or_access_denied", result["issues"])
            self.assertNotIn("123456", str(result))

    def test_missing_card_distinct_from_blank_ocr(self):
        with tempfile.TemporaryDirectory() as temp:
            def provider(code, url, directory):
                first, third = directory / "1.jpg", directory / "3.jpg"
                first.write_bytes(b"one")
                third.write_bytes(b"three")
                return {"media": [{"position": 1, "local": first, "is_video": False},
                                  {"position": 3, "local": third, "is_video": False}],
                        "expected_cards": 3, "caption": "", "issues": []}
            result = module.capture("https://www.instagram.com/p/ABC/", provider=provider,
                                    recognizer=lambda data, lang: "" if data == b"one" else "text")
            self.assertIn("missing_card:2", result["issues"])
            self.assertIn("empty_ocr:1", result["issues"])
            self.assertEqual([x["position"] for x in result["cards"]], [1, 3])
            self.assertEqual(result["cards"][0]["media_status"], "downloaded")
            self.assertEqual(result["cards"][0]["ocr_status"], "blank")

    def test_download_failure_not_reported_as_empty_text(self):
        def provider(code, url, directory):
            return {"media": [{"position": 1, "local": directory / "missing.jpg",
                               "is_video": False}], "expected_cards": 1, "issues": []}
        result = module.capture("https://www.instagram.com/p/ABC/", provider=provider)
        self.assertTrue(any(v.startswith("media_unavailable:1:") for v in result["issues"]))
        self.assertEqual(result["cards"][0]["ocr_status"], "not_run")
        self.assertIsNone(result["cards"][0]["sha256"])

    def test_failure_keeps_inbox_and_never_invents_content(self):
        def provider(code, url, directory):
            raise RuntimeError("Login required")
        result = module.capture("https://www.instagram.com/p/ABC/", provider=provider)
        self.assertIn("capture_failed:RuntimeError", result["issues"])
        self.assertEqual(result["cards"], [])
        note = module.markdown(result, "2026-10-24")
        self.assertIn('status: "inbox"', note)
        self.assertIn("미확보", note)
        self.assertNotIn("Synthetic sample - not from Instagram", note)


if __name__ == "__main__":
    unittest.main()
