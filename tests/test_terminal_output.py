import contextlib
import json
import unittest
from io import StringIO
from unittest.mock import patch

import collectors
import menace
import osint_tool
import terminal_output as output


class OutputTests(unittest.TestCase):
    def capture(self, results, **kwargs):
        stream = StringIO()
        with contextlib.redirect_stdout(stream):
            output.print_results(results, **kwargs)
        return stream.getvalue()

    def test_phone_fields_not_json(self):
        result = collectors.phone("02083661177", collectors.Options(region="GB"))
        text = self.capture(result)
        self.assertIn("International format: +44 20 8366 1177", text)
        self.assertIn("Valid number: Yes", text)
        self.assertIn("Original carrier: Not available", text)
        self.assertIn("Number type: Fixed line", text)
        self.assertNotIn('"status":', text)
        self.assertNotIn("metadata_version", text)
        self.assertIn("Metadata version:", self.capture(result, details=True))

    def test_nested_records_and_narrow_width(self):
        result = collectors.section("Transactions", "Example provider", {"status": "found", "url": "https://example.com"},
                                    [{"hash": "a" * 64, "from": {"hash": "b" * 42}, "status": "ok"}])
        text = self.capture([result], width=40)
        self.assertIn("Record 1", text)
        self.assertTrue(all(len(line) <= 40 for line in text.splitlines()))
        self.assertNotIn("{'", text)

    def test_failure_status_and_zero_are_visible(self):
        section = collectors.section("Check", "Source", {"status": "rate_limited", "message": "HTTP 429"})
        text = self.capture([section])
        self.assertIn("Status: Rate limited", text)
        self.assertIn("Details: HTTP 429", text)
        section = collectors.section("Balance", "Source", {"status": "found"}, {"balance_eth": "0", "is_contract": False})
        text = self.capture([section])
        self.assertIn("Balance (ETH): 0", text)
        self.assertIn("Contract account: No", text)

    def test_json_unchanged_and_escape_safe(self):
        sections = [collectors.invalid("Example", "Bad target")]
        stream = StringIO()
        with patch.object(menace.discovery, "collect", return_value=sections), contextlib.redirect_stdout(stream):
            menace.main(["search", "test", "--type", "username", "--mode", "collect", "--json"])
        self.assertEqual(json.loads(stream.getvalue())["results"], sections)
        text = self.capture([{"name": "Unsafe\x1b[31mheading", "findings": [{"label": "Test", "value": "text\x1b[2J"}]}])
        self.assertNotIn("\x1b", text)

    def test_legacy_renderer_uses_same_format(self):
        section = osint_tool.Section("DNS example")
        section.add("DNS records", {"A": ["192.0.2.1"], "MX": []}, "Example")
        stream = StringIO()
        with contextlib.redirect_stdout(stream):
            osint_tool.render([section], False)
        self.assertNotIn("{'A'", stream.getvalue())
        self.assertIn("192.0.2.1", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
