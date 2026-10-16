import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

import app
import case_features
import image_analysis as images
import workspace_store as store


@unittest.skip("Image feature deferred at user request; routes are disabled.")
class ImageAnalysisTests(unittest.TestCase):
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
        self.case = app.create_case("Image analysis validation")
        image = Image.new("RGB", (200, 150), "white")
        draw = ImageDraw.Draw(image)
        for x in range(30, 100, 5):
            draw.line((x, 20, x, 100), fill="black", width=2)
        buffer = BytesIO()
        image.save(buffer, "PNG")
        self.image_bytes = buffer.getvalue()
        self.box = {"x": 30, "y": 20, "width": 70, "height": 80}

    def create(self):
        with patch.object(images, "detect", return_value=[self.box]):
            return images.analyze(self.image_bytes)

    def test_actual_detector_localizes_sample_face(self):
        sample = Image.open(Path(__file__).parent / "fixtures/astronaut.png").convert("RGB")
        boxes = images.detect(sample)
        self.assertTrue(any(150 <= b["x"] <= 220 and 35 <= b["y"] <= 100 for b in boxes), boxes)
        for b in boxes:
            self.assertGreater(b["width"], 0)
            self.assertLessEqual(b["x"] + b["width"], sample.width)
            self.assertLessEqual(b["y"] + b["height"], sample.height)

    def test_variants_crops_and_persistence(self):
        result = self.create()
        folder = images.IMAGE_DIR / result["id"]
        self.assertEqual(store.get(result["id"])["faces"], [self.box])
        with Image.open(folder / "face-1.png") as crop:
            self.assertEqual(crop.size, (70, 80))
        with (
            Image.open(folder / "original.png") as original,
            Image.open(folder / "blurred.png") as blurred,
        ):
            self.assertIsNotNone(ImageChops.difference(original, blurred).getbbox())
        self.assertEqual(self.client.get("/images/" + result["id"]).status_code, 200)
        self.assertEqual(self.client.get("/history/" + result["id"]).status_code, 302)
        response = self.client.get("/images/" + result["id"] + "/files/annotated.png")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        response.close()
        self.assertEqual(
            self.client.get("/images/" + result["id"] + "/files/face-2.png").status_code, 404
        )
        self.assertEqual(
            self.client.get("/images/" + result["id"] + "/files/other.png").status_code, 404
        )

    def test_upload_validation(self):
        for data in (b"not an image", b"<script>bad</script>"):
            response = self.client.post(
                "/images",
                data={"image": (BytesIO(data), "image.png")},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/images").status_code, 400)
        with self.assertRaises(ValueError):
            images.analyze(b"x" * 10_000_001)

    def test_upload_success_and_zero_faces(self):
        with patch.object(images, "detect", return_value=[]):
            response = self.client.post(
                "/images",
                data={"image": (BytesIO(self.image_bytes), "test.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.headers["Location"])
        self.assertIn(b"No faces were detected", page.data)
        self.assertIn(b"does not establish", page.data)

    def test_detect_box_scaling(self):
        class Detector:
            def empty(self):
                return False

            def detectMultiScale(self, *args, **kwargs):
                return [(10, 20, 30, 40)]

        with patch.object(images.cv2, "CascadeClassifier", return_value=Detector()):
            boxes = images.detect(Image.new("RGB", (3200, 1600)))
        self.assertEqual(boxes, [dict(x=20, y=40, width=60, height=80)])

    def test_case_capture_preserves_selected_variant(self):
        result = self.create()
        response = self.client.post(
            "/images/" + result["id"] + "/case",
            data=dict(case_id=self.case["id"], variant="blurred", caption="Redacted test image"),
        )
        self.assertEqual(response.status_code, 200, response.data)
        case = app.load_case(self.case["id"])
        section = case["searches"][0]["results"][0]
        self.assertEqual(len(section["findings"]), 2)
        evidence = section["findings"][0]["evidence"][0]
        saved = case_features.EVIDENCE_DIR / self.case["id"] / (evidence["id"] + ".png")
        self.assertEqual(
            saved.read_bytes(), (images.IMAGE_DIR / result["id"] / "blurred.png").read_bytes()
        )
        self.assertEqual(section["findings"][1].get("evidence", []), [])
        # Reject accidentally saving unblurred crops alongside a blurred report image.
        invalid = self.client.post(
            "/images/" + result["id"] + "/case",
            data=dict(case_id=self.case["id"], variant="blurred", include_crops="on"),
        )
        self.assertEqual(invalid.status_code, 400)
        response = self.client.post(
            "/images/" + result["id"] + "/case",
            data=dict(case_id=self.case["id"], variant="annotated", include_crops="on"),
        )
        self.assertEqual(response.status_code, 200)
        case = app.load_case(self.case["id"])
        self.assertEqual(len(case["searches"][-1]["results"][0]["findings"][1]["evidence"]), 1)
        pdf = self.client.get("/cases/" + self.case["id"] + "/report.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b"%PDF"))

    def test_upload_capacity(self):
        with patch.object(images.DETECTION_LOCK, "acquire", return_value=False):
            response = self.client.post(
                "/images",
                data={"image": (BytesIO(self.image_bytes), "test.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 429)

    def test_orientation_and_metadata_are_normalized(self):
        image = Image.new("RGB", (200, 150), "white")
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "Do not retain this metadata"
        buffer = BytesIO()
        image.save(buffer, "JPEG", exif=exif)
        with patch.object(images, "detect", return_value=[]):
            result = images.analyze(buffer.getvalue())
        self.assertEqual((result["width"], result["height"]), (150, 200))
        with Image.open(images.IMAGE_DIR / result["id"] / "original.png") as saved:
            self.assertEqual(dict(saved.getexif()), {})
