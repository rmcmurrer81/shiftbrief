"""Installed ShiftBrief: bundled runtime, per-user records, graceful owned shutdown."""
from pathlib import Path
import argparse
import ctypes
from ctypes import wintypes
import json
import msvcrt
import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
MUTEX = r"Local\ShiftBrief-1A16CC9E-46AB-43B5-8E2D-E6294096E312"
_PROCESS_LOCKS = []
_MUTEX_HANDLES = []


def data_directory():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise RuntimeError("Windows LocalAppData is unavailable; no business folder was changed.")
    return Path(base) / "ShiftBrief" / "data"


def existing_instance(data):
    info = json.loads((data / "application-instance.json").read_text(encoding="utf-8"))
    port = info.get("port")
    token = info.get("instance")
    if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or len(token) != 48:
        raise ValueError("Invalid local instance metadata")
    address = f"http://127.0.0.1:{port}"
    with urllib.request.urlopen(address + "/api/installed-instance", timeout=1) as response:
        current = json.load(response)
    if current != {"app": "ShiftBrief", "instance": token}:
        raise ValueError("The saved port is not this ShiftBrief instance")
    return address, token


def stop_existing(data):
    try:
        address, token = existing_instance(data)
    except (OSError, ValueError, KeyError):
        return {"status": "not_running"}
    body = json.dumps({"instance": token}).encode("utf-8")
    request = urllib.request.Request(address + "/api/installed-stop", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=3) as response:
        result = json.load(response)
    if result != {"status": "stopping"}:
        raise RuntimeError("ShiftBrief did not acknowledge the close request")
    return result


def claim_mutex():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel.CreateMutexW(None, False, MUTEX)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    # Kept alive until OS process exit, as is the one-byte data lock.
    _MUTEX_HANDLES.append(handle)


def installed_handler(original, app, instance):
    class Handler(original):
        def do_GET(self):
            if self.path == "/api/installed-instance":
                self.reply({"app": "ShiftBrief", "instance": instance})
            else:
                super().do_GET()

        def do_POST(self):
            if self.path != "/api/installed-stop":
                return super().do_POST()
            expected = f"127.0.0.1:{app.server_port}"
            origin = self.headers.get("Origin")
            if (self.headers.get("Host") != expected or
                    origin not in (None, "http://" + expected) or
                    self.headers.get("Transfer-Encoding") is not None or
                    self.headers.get("Content-Type") != "application/json"):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 256:
                    raise ValueError("Invalid request length")
                self.connection.settimeout(2)
                value = json.loads(self.rfile.read(length))
                if value != {"instance": instance}:
                    raise ValueError("Wrong instance")
            except (ValueError, OSError):
                self.send_error(403)
                return
            self.reply({"status": "stopping"})
            threading.Thread(target=app.shutdown, daemon=True).start()
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop", action="store_true")
    options = parser.parse_args()
    data = data_directory()
    if options.stop:
        result = stop_existing(data)
        if sys.stdout:
            print(json.dumps(result), flush=True)
        return
    data.mkdir(parents=True, exist_ok=True)
    lock = (data / "application.lock").open("a+b")
    if lock.seek(0, 2) == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        for _ in range(30):
            try:
                address, _ = existing_instance(data)
                if not options.no_browser:
                    webbrowser.open(address)
                if sys.stdout:
                    print(json.dumps({"status": "reused", "url": address}), flush=True)
                return
            except (OSError, ValueError, KeyError):
                time.sleep(.2)
        raise RuntimeError("ShiftBrief is already starting. Wait a moment, then open it again.")
    _PROCESS_LOCKS.append(lock)
    claim_mutex()
    sys.path.insert(0, str(ROOT))
    import server
    app = server.make_server(data, 0)
    instance = secrets.token_hex(24)
    app.RequestHandlerClass = installed_handler(app.RequestHandlerClass, app, instance)
    info = {"port": app.server_port, "instance": instance}
    (data / "application-instance.json").write_text(json.dumps(info), encoding="utf-8")
    address = f"http://127.0.0.1:{app.server_port}"
    stop = threading.Event()

    def watch():
        while not stop.wait(15):
            app.app.store.refresh_watches()

    watcher = threading.Thread(target=watch, name="ShiftBrief document watch", daemon=True)
    watcher.start()
    if sys.stdout:
        print(json.dumps({"status": "started", "url": address, "data_directory": str(data)}), flush=True)
    if not options.no_browser:
        threading.Timer(.4, lambda: webbrowser.open(address)).start()
    try:
        app.serve_forever()
    finally:
        stop.set()
        app.server_close()
        watcher.join(2)
        try:
            if json.loads((data / "application-instance.json").read_text(encoding="utf-8")) == info:
                (data / "application-instance.json").unlink()
        except (OSError, ValueError):
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if sys.stderr:
            print("ShiftBrief could not start: " + str(error), file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None, str(error), "ShiftBrief could not start", 0x10)
        raise
