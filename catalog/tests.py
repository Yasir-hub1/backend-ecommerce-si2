from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from catalog.services.ar_assets import estimate_anchors, process_garment_image, validate_ar_upload
from core.ar import default_anchor_config, validate_anchor_config


def _png_bytes(*, width=640, height=720, opaque=False) -> bytes:
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    for x in range(80, width - 80):
        for y in range(40, height - 40):
            img.putpixel((x, y), (20, 20, 20, 255 if not opaque else 255))
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class AnchorConfigTests(SimpleTestCase):
    def test_default_is_valid_v1(self):
        config = validate_anchor_config(default_anchor_config())
        self.assertEqual(config['version'], 1)
        self.assertEqual(config['body_part'], 'TORSO')
        self.assertIn('M', config['size_scale'])

    def test_rejects_out_of_range_points(self):
        raw = default_anchor_config()
        raw['anchor_left'] = {'x': 1.5, 'y': 0.1}
        with self.assertRaises(ValueError):
            validate_anchor_config(raw)

    def test_rejects_unknown_body_part(self):
        raw = default_anchor_config()
        raw['body_part'] = 'ARM'
        with self.assertRaises(ValueError):
            validate_anchor_config(raw)


class EstimateAnchorsTests(SimpleTestCase):
    def test_finds_shoulders_inside_silhouette(self):
        img = Image.open(BytesIO(_png_bytes())).convert('RGBA')
        config = estimate_anchors(img)
        self.assertTrue(config['auto_calibrated'])
        self.assertLess(config['anchor_left']['x'], config['anchor_right']['x'])
        self.assertGreater(config['anchor_left']['y'], 0)


class ValidateUploadTests(SimpleTestCase):
    @override_settings(AR_AUTO_CUTOUT=False, AR_ASSET_UPLOAD_MAX_MB=8)
    def test_rejects_tiny_image(self):
        data = _png_bytes(width=64, height=64)
        upload = SimpleUploadedFile('tiny.png', data, content_type='image/png')
        with self.assertRaises(ValidationError):
            validate_ar_upload(upload)


class ProcessGarmentTests(TestCase):
    @override_settings(AR_AUTO_CUTOUT=False, AR_ASSET_MAX_WIDTH=512)
    def test_process_without_rembg(self):
        png, anchor = process_garment_image(_png_bytes(width=800, height=900))
        self.assertGreater(len(png), 0)
        self.assertEqual(anchor['version'], 1)

    @override_settings(AR_AUTO_CUTOUT=True)
    @patch('catalog.services.ar_assets._remove_background', side_effect=RuntimeError('no rembg'))
    def test_cutout_failure_falls_back(self, _mock):
        png, anchor = process_garment_image(_png_bytes())
        self.assertGreater(len(png), 0)
        self.assertEqual(anchor['body_part'], 'TORSO')
