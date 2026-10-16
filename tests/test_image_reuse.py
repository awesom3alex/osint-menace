import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
import case_features
import image_analysis as images
import image_reuse as reuse
import workspace_store as store


@unittest.skip("Image feature deferred at user request; routes are disabled.")
class ImageReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, key, value in [
            (images, "IMAGE_DIR", root / "images"),
            (store, "DB_PATH", root / "history.sqlite3"),
            (app, "CASES_DIR", root / "cases"),
            (case_features, "EVIDENCE_DIR", root / "evidence"),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = app.app.test_client()
        self.sample = Image.open(Path(__file__).parent / "fixtures/astronaut.png").convert("RGB")

    def save(self, image):
        buffer = BytesIO()
        image.save(buffer, "PNG")
        with patch.object(images, "detect", return_value=[]):
            return images.analyze(buffer.getvalue())

    def test_exact_resized_and_unrelated(self):
        query = self.save(self.sample)
        exact = self.save(self.sample)
        resized = self.save(self.sample.resize((256, 256), Image.Resampling.LANCZOS))
        unrelated = self.save(Image.new("RGB", (512, 512), "blue"))
        matches, scanned, total, missing = reuse.find_matches(query)
        by_id = {match["image_id"]: match for match in matches}
        self.assertEqual(by_id[exact["id"]]["match_type"], "Identical normalized pixels")
        self.assertEqual(by_id[resized["id"]]["match_type"], "Similar whole image")
        self.assertNotIn(unrelated["id"], by_id)
        self.assertNotIn(query["id"], by_id)
        self.assertEqual((scanned, total, missing), (3, 3, 0))

    def test_no_matches_and_missing_file(self):
        query = self.save(Image.new("RGB", (60, 60), "white"))
        other = self.save(Image.new("RGB", (60, 60), "black"))
        self.assertEqual(reuse.find_matches(query)[0], [])
        (images.IMAGE_DIR / other["id"] / "original.png").unlink()
        self.assertEqual(reuse.find_matches(query)[3], 1)
        response = self.client.post("/images/" + query["id"] + "/reuse")
        page = self.client.get(response.headers["Location"])
        self.assertIn(b"No local matches found", page.data)
        self.assertIn(b"public web", page.data)

    def test_source_url_validation(self):
        image = self.save(self.sample)
        url = "/images/" + image["id"] + "/source"
        for source in (
            "javascript:alert(1)",
            "file:///tmp/private",
            "https://user:password@example.com",
            "https://example.com/\nsecret",
        ):
            self.assertEqual(self.client.post(url, data={"source_url": source}).status_code, 400)
        self.assertEqual(
            self.client.post(
                url, data={"source_url": "https://example.com/image-source"}
            ).status_code,
            200,
        )
        self.assertEqual(store.get(image["id"])["source_url"], "https://example.com/image-source")

    def test_persistent_results_and_case_capture(self):
        query = self.save(self.sample)
        match = self.save(self.sample)
        self.client.post(
            "/images/" + match["id"] + "/source", data={"source_url": "https://example.com/source"}
        )
        result = self.client.post("/images/" + query["id"] + "/reuse", data={"threshold": "8"})
        self.assertEqual(result.status_code, 302)
        run_id = result.headers["Location"].split("/")[-1]
        self.assertEqual(self.client.get("/history/" + run_id).status_code, 302)
        page = self.client.get(result.headers["Location"])
        self.assertIn(b"Identical normalized pixels", page.data)
        self.assertIn(b"https://example.com/source", page.data)
        case = app.create_case("Reuse evidence validation")
        captured = self.client.post(
            "/image-reuse/" + run_id + "/case/" + match["id"], data={"case_id": case["id"]}
        )
        self.assertEqual(captured.status_code, 200)
        saved = app.load_case(case["id"])["searches"][0]["results"][0]
        self.assertEqual(len(saved["findings"][0]["evidence"]), 2)
        self.assertEqual(saved["links"][0]["value"], "https://example.com/source")
        self.assertEqual(self.client.get("/cases/" + case["id"] + "/report.pdf").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/image-reuse/" + run_id + "/case/" + query["id"], data={"case_id": case["id"]}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/images/" + query["id"] + "/reuse", data={"threshold": "99"}
            ).status_code,
            400,
        )
