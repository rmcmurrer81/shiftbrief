from pathlib import Path
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import urllib.error
import urllib.request
import zipfile

import build_installer as builder
import installed_launch as launcher
import smoke_installer as smoke


def archive_bytes(extra=None, bad_source=False):
    files = {"server.py": b"# app fixture", "index.html": b"<html></html>", "LICENSE": b"MIT",
             "README.md": b"portable fixture", "runtime/python.exe": b"fixture",
             "runtime/pythonw.exe": b"fixture", "runtime/python314._pth": b"import site"}
    record = {"sha256": hashlib.sha256(files["server.py"]).hexdigest(), "bytes": len(files["server.py"])}
    files["SOURCE-MANIFEST.json"] = json.dumps({"schema": "shiftbrief.portable-source.v1", "commit": "a" * 40,
                                               "source_files": {"server.py": record}}).encode()
    if bad_source:
        files["server.py"] += b"altered"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in files.items():
            archive.writestr("ShiftBrief/" + name, data)
        if extra:
            archive.writestr(extra, b"untrusted")
    return output.getvalue()


class PackageTests(unittest.TestCase):
    def test_existing_registration_with_missing_values_is_not_absent(self):
        key = MagicMock()
        with patch.object(smoke.winreg, "OpenKey", side_effect=[key, FileNotFoundError(), FileNotFoundError(), FileNotFoundError()]), \
             patch.object(smoke.winreg, "QueryValueEx", side_effect=FileNotFoundError()):
            self.assertEqual(smoke.registrations(), [{"hive": "HKCU", "view": "32", "install_location": None, "uninstall": None}])

    def test_stage_binds_commit_and_preserves_app_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); raw = archive_bytes(); source = root / "app.zip"; source.write_bytes(raw)
            result = builder.build(source, builder.digest(raw), "a" * 40, root / "build")
            self.assertEqual(result["status"], "STAGED_NOT_COMPILED")
            self.assertEqual((root / "build/payload/server.py").read_bytes(), b"# app fixture")
            self.assertFalse((root / "build/payload/data").exists())
            self.assertIn("%LOCALAPPDATA%", (root / "build/payload/README.md").read_text())
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, "new directory"):
                builder.build(source, builder.digest(raw), "a" * 40, root / "build")

    def test_bad_source_wrong_commit_and_private_archive_rejected(self):
        for raw, commit in [(archive_bytes(bad_source=True), "a" * 40), (archive_bytes(), "b" * 40),
                            (archive_bytes("ShiftBrief/data/state.json"), "a" * 40),
                            (archive_bytes("ShiftBrief/../escape"), "a" * 40),
                            (archive_bytes("ShiftBrief/SERVER.PY"), "a" * 40)]:
            with self.subTest(commit=commit, sha=builder.digest(raw)):
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    with self.assertRaises(ValueError):
                        builder.validate_zip(archive, commit)

    def test_wrong_zip_hash_creates_no_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "app.zip"; source.write_bytes(archive_bytes())
            with self.assertRaisesRegex(ValueError, "hash changed"):
                builder.build(source, "0" * 64, "a" * 40, root / "out")
            self.assertFalse((root / "out").exists())


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        class Base(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, value):
                raw = json.dumps(value).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_GET(self): self.send_error(404)
            def do_POST(self): self.send_error(404)
        self.app = ThreadingHTTPServer(("127.0.0.1", 0), Base)
        self.token = "c" * 48
        self.app.RequestHandlerClass = launcher.installed_handler(Base, self.app, self.token)
        self.thread = threading.Thread(target=self.app.serve_forever, daemon=True); self.thread.start()
        self.address = f"http://127.0.0.1:{self.app.server_port}"
        self.temp = tempfile.TemporaryDirectory(); self.data = Path(self.temp.name)
        (self.data / "application-instance.json").write_text(json.dumps({"port": self.app.server_port, "instance": self.token}))

    def tearDown(self):
        self.app.shutdown(); self.app.server_close(); self.thread.join(3); self.temp.cleanup()

    def test_owned_identity_and_shutdown(self):
        self.assertEqual(launcher.existing_instance(self.data), (self.address, self.token))
        self.assertEqual(launcher.stop_existing(self.data), {"status": "stopping"})
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def test_wrong_token_origin_host_and_chunked_do_not_stop(self):
        variants = [({"instance": "d" * 48}, {}), ({"instance": self.token}, {"Origin": "https://example.org"}),
                    ({"instance": self.token}, {"Host": "example.org"}),
                    ({"instance": self.token}, {"Transfer-Encoding": "chunked"})]
        for body, headers in variants:
            request = urllib.request.Request(self.address + "/api/installed-stop", data=json.dumps(body).encode(),
                        headers={"Content-Type": "application/json", **headers}, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            self.assertTrue(self.thread.is_alive())

    def test_unrelated_instance_is_not_reused_or_stopped(self):
        (self.data / "application-instance.json").write_text(json.dumps({"port": self.app.server_port, "instance": "e" * 48}))
        self.assertEqual(launcher.stop_existing(self.data), {"status": "not_running"})
        self.assertTrue(self.thread.is_alive())

    def test_business_directory_is_separate_from_installation(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.data)}):
            self.assertEqual(launcher.data_directory(), self.data / "ShiftBrief/data")
        with patch.dict(os.environ, {"LOCALAPPDATA": "relative"}):
            with self.assertRaises(RuntimeError): launcher.data_directory()


if __name__ == "__main__":
    unittest.main(verbosity=2)
