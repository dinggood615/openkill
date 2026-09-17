#!/usr/bin/env python3
"""Ensure Core transport failures have an explicit, narrow classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/test-core.py"
spec = importlib.util.spec_from_file_location("openkill_test_core_contract", SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoreDownloadContractTests(unittest.TestCase):
    def test_transport_error_is_explicit_environment_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("fixture transport failure"),
        ):
            with self.assertRaises(module.CoreReleaseUnavailable) as raised:
                module.download_core("v1.19.30", Path(temp) / "mihomo")
        self.assertIn("release API transport", str(raised.exception))

    def test_http_or_validation_error_is_not_environment_skip(self) -> None:
        error = urllib.error.HTTPError("https://example.invalid", 404, "missing", {}, None)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            module.urllib.request,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaises(RuntimeError) as raised:
                module.download_core("v1.19.30", Path(temp) / "mihomo")
        self.assertIn("HTTP 404", str(raised.exception))

    def test_asset_transport_failure_keeps_explicit_environment_class(self) -> None:
        release = {
            "assets": [{
                "name": "mihomo-linux-amd64-compatible-test.gz",
                "digest": "sha256:" + ("0" * 64),
                "browser_download_url": "https://example.invalid/core.gz",
            }],
            "tag_name": "v1.19.30",
        }

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                import json
                return json.dumps(self.payload).encode("utf-8")

        def urlopen(request, timeout=0):
            if isinstance(request, urllib.request.Request):
                return Response(release)
            raise urllib.error.URLError("fixture asset transport failure")

        with tempfile.TemporaryDirectory() as temp, mock.patch.object(module.urllib.request, "urlopen", side_effect=urlopen):
            with self.assertRaises(module.CoreReleaseUnavailable) as raised:
                module.download_core("v1.19.30", Path(temp) / "mihomo")
        self.assertIn("release asset transport", str(raised.exception))

    def test_checksum_mismatch_is_a_required_failure(self) -> None:
        release = {
            "assets": [{
                "name": "mihomo-linux-amd64-compatible-test.gz",
                "digest": "sha256:" + ("0" * 64),
                "browser_download_url": "https://example.invalid/core.gz",
            }],
            "tag_name": "v1.19.30",
        }

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                import json
                if isinstance(self.payload, dict):
                    return json.dumps(self.payload).encode("utf-8")
                return self.payload

        def urlopen(request, timeout=0):
            if isinstance(request, urllib.request.Request):
                return Response(release)
            return Response(b"not-a-gzip")

        with tempfile.TemporaryDirectory() as temp, mock.patch.object(module.urllib.request, "urlopen", side_effect=urlopen):
            with self.assertRaises(RuntimeError) as raised:
                module.download_core("v1.19.30", Path(temp) / "mihomo")
        self.assertIn("checksum mismatch", str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
