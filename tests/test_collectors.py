import contextlib
import json
import os
import socket
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from docx import Document

import cli_workspace
import collectors as c
import discovery
import menace


def response(data=None, status="found", code=200):
    return {"status": status, "http_status": code, "url": "https://example.com/source", "data": data,
            "body": json.dumps(data).encode(), "headers": {"content-type": "application/json"}}


def observation(section):
    return section["findings"][0]["value"]


class CollectorTests(unittest.TestCase):
    def test_github_schema_and_identity(self):
        with patch.object(c, "get_json", return_value=response({"login": "octocat", "name": "Example", "public_repos": 8})):
            result = c.collect("username", "octocat", c.Options(platforms=("github",)))[0]
        value = observation(result)
        self.assertEqual(value["status"], "found")
        self.assertFalse(value["data"]["identity_verified"])
        self.assertIn("retrieved_at", value)
        self.assertEqual(result["links"][0]["category"], "candidate_profile")
        with patch.object(c, "get_json", return_value=response({"message": "oops"})):
            result = c.profiles("octocat", c.Options(platforms=("github",)))[0]
        self.assertEqual(observation(result)["status"], "error")

    def test_bluesky_no_profile_and_rate_limit(self):
        with patch.object(c, "get_json", return_value=response({"error": "ProfileNotFound"}, "error", 400)):
            self.assertEqual(observation(c.profiles("missing", c.Options(platforms=("bluesky",)))[0])["status"], "not_found")
        with patch.object(c, "get_json", return_value=response(None, "rate_limited", 429)):
            self.assertEqual(observation(c.profiles("example", c.Options(platforms=("github",)))[0])["status"], "rate_limited")

    def test_phone_international_and_invalid(self):
        value = observation(c.collect("phone", "020 8366 1177", c.Options(region="GB"))[0])
        self.assertTrue(value["data"]["valid"])
        self.assertEqual(value["data"]["e164"], "+442083661177")
        self.assertEqual(observation(c.collect("phone", "nonsense")[0])["status"], "invalid")

    def test_bitcoin_zero_and_transaction_limit(self):
        summary = {"chain_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0, "tx_count": 0},
                   "mempool_stats": {"funded_txo_sum": 0, "spent_txo_sum": 0}}
        with patch.object(c, "get_json", side_effect=[response(summary), response([{"txid": "a"}, {"txid": "b"}])]):
            results = c.collect("wallet", "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", c.Options(limit=1))
        self.assertEqual(observation(results[0])["data"]["confirmed_satoshis"], 0)
        self.assertEqual(len(observation(results[1])["data"]), 1)

    def test_ethereum_precision_and_missing_balance(self):
        address = "0x" + "1" * 40
        with patch.object(c, "get_json", side_effect=[response({"coin_balance": "1000000000000000001"}), response({"items": []})]):
            results = c.collect("wallet", address)
        self.assertEqual(observation(results[0])["data"]["balance_eth"], "1.000000000000000001")
        with patch.object(c, "get_json", return_value=response({})):
            results = c.collect("wallet", address)
        self.assertEqual(observation(results[0])["status"], "error")
        self.assertNotIn("data", observation(results[0]))

    def test_page_extraction_hash_and_truncation(self):
        raw = response()
        raw["body"] = b"<title>Evidence</title><script>secret_script</script><p>" + b"hello " * 50 + b"</p>"
        raw["headers"] = {"content-type": "text/html"}
        with patch.object(c, "fetch", return_value=raw):
            value = observation(c.collect("url", "https://example.com", c.Options(text_limit=100))[0])
        self.assertEqual(value["data"]["title"], "Evidence")
        self.assertNotIn("secret_script", value["data"]["text"])
        self.assertEqual(len(value["data"]["body_sha256"]), 64)
        self.assertTrue(value["data"]["text_truncated"])

    def test_private_destinations_blocked_before_connect(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with patch.object(socket, "getaddrinfo", return_value=answer), patch.object(socket, "create_connection") as connect:
            result = c.fetch("http://example.com")
        self.assertEqual(result["status"], "error")
        connect.assert_not_called()

    def test_invalid_json_and_http_statuses(self):
        bad = response()
        bad["body"] = b"<html>challenge</html>"
        with patch.object(c, "fetch", return_value=bad):
            self.assertEqual(c.get_json("https://example.com", c.Options())["status"], "error")
        for code, expected in ((404, "not_found"), (403, "blocked"), (429, "rate_limited"), (500, "error")):
            connection = MagicMock()
            http_response = connection.getresponse.return_value
            http_response.status = code
            http_response.getheaders.return_value = []
            http_response.read.return_value = b""
            with patch.object(c, "public_address", return_value=(c.urllib.parse.urlsplit("http://example.com"), 80, "93.184.216.34")), patch.object(c.http.client, "HTTPConnection", return_value=connection), patch.object(socket, "create_connection"):
                self.assertEqual(c.fetch("http://example.com")["status"], expected)

    def test_records_credentials_jurisdiction_and_empty(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(c, "get_json") as get:
            results = c.collect("records", "Example", c.Options(records_sources=("sec", "courtlistener")))
        get.assert_not_called()
        self.assertTrue(all(observation(result)["status"] == "configuration_required" for result in results))
        with patch.object(c, "get_json", return_value=response({"search": []})):
            self.assertEqual(observation(c.collect("name", "No Match")[0])["status"], "no_matches")
        self.assertEqual(observation(c.collect("records", "Example", c.Options(records_sources=("sec",), jurisdiction="world"))[0])["status"], "invalid")

    def test_record_matching_and_token_not_in_evidence(self):
        with patch.dict(os.environ, {"SEC_USER_AGENT": "Test org test@example.com"}), patch.object(c, "get_json", return_value=response({"0": {"title": "EXAMPLE COMPANY", "ticker": "EXM", "cik_str": 123}})):
            result = c.records("EXM", c.Options(records_sources=("sec",)))[0]
        self.assertEqual(observation(result)["data"][0]["cik_str"], 123)
        with patch.dict(os.environ, {"COURTLISTENER_TOKEN": "test-secret"}), patch.object(c, "get_json", return_value=response({"results": [{"caseName": "Example v Sample", "court": "Test", "absolute_url": "/opinion/123"}]})):
            result = c.records("Example", c.Options(records_sources=("courtlistener",)))[0]
        self.assertEqual(observation(result)["data"][0]["caseName"], "Example v Sample")
        self.assertNotIn("test-secret", json.dumps(result))

    def test_page_exact_excerpt(self):
        raw = response()
        raw["body"] = b"<p>First observation. Second observation.</p>"
        raw["headers"] = {"content-type": "text/html"}
        with patch.object(c, "fetch", return_value=raw.copy()):
            value = observation(c.page("https://example.com", c.Options(excerpt="Second observation."))[0])
        self.assertEqual(value["data"]["text"], "Second observation.")
        with patch.object(c, "fetch", return_value=raw.copy()):
            value = observation(c.page("https://example.com", c.Options(excerpt="Not present"))[0])
        self.assertEqual(value["status"], "no_matches")
        self.assertNotIn("data", value)

    def test_redirect_validation_and_header_isolation(self):
        responses = []
        for code, headers in ((302, [("Location", "http://second.example/page")]), (200, [])):
            item = MagicMock(status=code)
            item.getheaders.return_value = headers
            item.read.return_value = b"{}"
            responses.append(item)
        connections = [MagicMock(), MagicMock()]
        for conn, item in zip(connections, responses):
            conn.getresponse.return_value = item
        def address(url):
            return c.urllib.parse.urlsplit(url), 80, "93.184.216.34"
        with patch.object(c, "public_address", side_effect=address) as addresses, patch.object(c.http.client, "HTTPConnection", side_effect=connections), patch.object(socket, "create_connection"):
            result = c.fetch("http://first.example/", headers={"Authorization": "Token test"})
        self.assertEqual(result["status"], "found")
        self.assertEqual(addresses.call_count, 2)
        self.assertIn("Authorization", connections[0].request.call_args.kwargs["headers"])
        self.assertNotIn("Authorization", connections[1].request.call_args.kwargs["headers"])

    def test_links_mode_no_collector_requests(self):
        with patch.object(discovery, "collect") as collect:
            results = discovery.run_search("username", "example", mode="links")
        collect.assert_not_called()
        self.assertEqual(results[0]["findings"], [])
        self.assertTrue(any(link["category"] == "search_link" for link in results[0]["links"]))

    def test_cli_options_and_json_failure_exit(self):
        output = StringIO()
        with patch.object(discovery, "collect", return_value=[c.invalid("Example", "Bad target")]), contextlib.redirect_stdout(output):
            code = menace.main(["search", "example", "--type", "username", "--platform", "github", "--limit", "2", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["results"][0]["findings"][0]["value"]["status"], "invalid")

    def test_repeat_capture_dedup_ignores_fetch_time(self):
        first = {"value": {"retrieved_at": "one", "source_url": "https://example.com", "data": {"title": "Same"}}}
        second = {"value": {**first["value"], "retrieved_at": "two"}}
        self.assertEqual(cli_workspace.fingerprint("findings", first), cli_workspace.fingerprint("findings", second))
        second["value"]["data"] = {"title": "Changed"}
        self.assertNotEqual(cli_workspace.fingerprint("findings", first), cli_workspace.fingerprint("findings", second))

    def test_page_selection_case_and_word_provenance(self):
        old_dir = menace.core.CASES_DIR
        try:
            with tempfile.TemporaryDirectory() as folder:
                menace.core.CASES_DIR = Path(folder) / "cases"
                case = menace.core.create_case("Collector integration")
                section = c.section("Example page", "Public HTTP page", {"status": "found", "url": "https://example.com"},
                                    {"title": "Example", "text": "Evidence text", "body_sha256": "abc"})
                with patch.object(discovery, "collect", return_value=[section]), contextlib.redirect_stdout(StringIO()), contextlib.redirect_stderr(StringIO()):
                    code = menace.main(["--data-dir", folder, "search", "https://example.com", "--type", "url", "--case", case["id"], "--finding", "1"])
                self.assertEqual(code, 0)
                case = menace.core.load_case(case["id"])
                self.assertEqual(len(case["searches"]), 1)
                from word_report import build_word_report
                word = Document(build_word_report(case))
                text = "\n".join(paragraph.text for paragraph in word.paragraphs)
                self.assertIn("https://example.com", text)
                self.assertIn("body_sha256", text)
                self.assertIn("Evidence text", text)
        finally:
            menace.core.CASES_DIR = old_dir


if __name__ == "__main__":
    unittest.main()
