import unittest

import app
from readable_results import readable_text, structured_value


class ReadableResultsTests(unittest.TestCase):
    def test_json_strings_and_native_values(self):
        for value in ({"valid": True}, '[{"valid":true}]', '{"valid":true}', '{"a":1}\n{"a":2}'):
            self.assertTrue(structured_value(value)["structured"])
        self.assertFalse(structured_value("Ordinary tool output")["structured"])
        self.assertFalse(structured_value("{unfinished")["structured"])

    def test_renderer_escapes_untrusted_data(self):
        with app.app.app_context():
            template = app.app.jinja_env.from_string(
                "{% from 'readable_value.html' import readable %}{{ readable(value) }}"
            )
            html = template.render(
                value={
                    "valid": True,
                    "profile": "<script>alert(1)</script>",
                    "nested": {"line_type": "FIXED_OR_MOBILE"},
                    "items": [],
                }
            )
        self.assertIn("Valid number", html)
        self.assertIn("Yes", html)
        self.assertIn("Fixed or mobile", html)
        self.assertIn("View raw JSON", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("No results returned.", html)

    def test_markdown_is_readable(self):
        self.assertEqual(
            readable_text('{"valid":true,"line_type":"FIXED_OR_MOBILE"}'),
            "Valid number: Yes\nLine type: Fixed or mobile",
        )
