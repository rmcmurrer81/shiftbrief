"""Owned-path installation/launch/uninstall proof; no existing app or real data mutation."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import winreg

HERE = Path(__file__).resolve().parent
KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{1A16CC9E-46AB-43B5-8E2D-E6294096E312}_is1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registrations():
    result = []
    for hive, name in [(winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")]:
        for view, label in [(winreg.KEY_WOW64_32KEY, "32"), (winreg.KEY_WOW64_64KEY, "64")]:
            try:
                key = winreg.OpenKey(hive, KEY, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            with key:
                entry = {"hive": name, "view": label}
                for field, value_name in [("install_location", "InstallLocation"), ("uninstall", "UninstallString")]:
                    try:
                        entry[field] = winreg.QueryValueEx(key, value_name)[0]
                    except FileNotFoundError:
                        entry[field] = None
                result.append(entry)
    return result


def get_json(url):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def run(build_report, smoke_root):
    smoke_root = smoke_root.resolve()
    if not smoke_root.is_relative_to(HERE) or smoke_root == HERE or smoke_root.exists():
        raise ValueError("Smoke root must be a new directory inside the installer candidate")
    before = registrations()
    if before:
        raise RuntimeError("A ShiftBrief AppId is already registered; no installer was executed")
    build = json.loads(build_report.read_text(encoding="utf-8"))
    installer = Path(build["installer"]["path"])
    if sha(installer) != build["installer"]["sha256"]:
        raise ValueError("Installer hash changed")
    smoke_root.mkdir()
    target = smoke_root / "installed-app"
    profile = smoke_root / "test-local-appdata"
    data = profile / "ShiftBrief/data"
    report = {"status": "RUNNING", "installer_sha256": sha(installer), "target": str(target),
              "data_directory": str(data), "preexisting_registrations": before,
              "model_calls": 0, "browser_opened": False, "remote_calls": 0}
    report_path = smoke_root / "SMOKE-RESULT.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    command = [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/NOICONS", "/TASKS=",
               "/DIR=" + str(target), "/LOG=" + str(smoke_root / "install.log")]
    setup = subprocess.run(command, timeout=90)
    report["setup_exit"] = setup.returncode
    if setup.returncode:
        save(); raise RuntimeError("Isolated setup failed")
    installed = registrations()
    if not installed or any(Path(item["install_location"]).resolve() != target for item in installed):
        save(); raise RuntimeError("Installer registration does not match the owned target")
    report["installed_registrations"] = installed
    for relative, expected in build["payload_files"].items():
        if sha(target / relative) != expected:
            save(); raise RuntimeError("Installed payload differs: " + relative)
    report["installed_payload_hashes_match"] = True
    env = os.environ.copy(); env["LOCALAPPDATA"] = str(profile); env["PYTHONDONTWRITEBYTECODE"] = "1"
    # This smoke checks offline records only, even if the parent process has optional provider settings.
    for key in list(env):
        if key.startswith("SHIFTBRIEF_"):
            del env[key]
    stdout = (smoke_root / "app.stdout.log").open("w", encoding="utf-8")
    stderr = (smoke_root / "app.stderr.log").open("w", encoding="utf-8")
    launch = [str(target / "runtime/python.exe"), "-B", str(target / "installed_launch.py"), "--no-browser"]
    process = subprocess.Popen(launch, env=env, cwd=target, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    report["owned_pid"] = process.pid
    address = None
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("Owned installed launcher exited before readiness")
            try:
                info = json.loads((data / "application-instance.json").read_text(encoding="utf-8"))
                candidate = f"http://127.0.0.1:{int(info['port'])}"
                if get_json(candidate + "/api/installed-instance") == {"app": "ShiftBrief", "instance": info["instance"]}:
                    address = candidate; break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.1)
        if not address:
            raise RuntimeError("Installed launcher readiness timed out")
        state = get_json(address + "/api/state")
        report["state_top_level_keys"] = sorted(state)
        view = state["state"]
        if (view["staffing"]["employees"] or view["documents"] or view["assistant"]["messages"] or
                view["workspace_setup"] != {"empty_business": True, "fictional_demo": False}):
            raise RuntimeError("Fresh installed business was not blank")
        report["first_run_blank"] = True
        repeat = subprocess.run(launch, env=env, cwd=target, capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        result = json.loads(repeat.stdout.strip().splitlines()[-1])
        if repeat.returncode or result != {"status": "reused", "url": address}:
            raise RuntimeError("Second launch did not reuse the exact installed instance")
        report["second_launch_reused"] = True
        wrong = urllib.request.Request(address + "/api/installed-stop", data=b'{"instance":"wrong"}',
                                       headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(wrong, timeout=3)
            raise RuntimeError("Foreign close unexpectedly succeeded")
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise
            error.close()
        if process.poll() is not None:
            raise RuntimeError("Foreign close stopped the app")
        report["foreign_close_rejected"] = True
        sentinel = data / "uninstall-preservation-proof.txt"
        sentinel.write_bytes(b"Owned fixture: preserve my business data.\r\n")
        sentinel_hash = sha(sentinel)
        close = subprocess.run([*launch[:-1], "--stop"], env=env, cwd=target, capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        if close.returncode or json.loads(close.stdout.strip()) != {"status": "stopping"}:
            raise RuntimeError("Owned close action failed")
        if process.wait(timeout=10) != 0:
            raise RuntimeError("Owned process did not close cleanly")
        report["graceful_close_passed"] = True
        report["data_hashes_before_uninstall"] = {str(p.relative_to(data)): sha(p) for p in data.rglob("*") if p.is_file()}
        uninstaller = target / "unins000.exe"
        expected_uninstall = str(uninstaller)
        if any(item["uninstall"].strip('"') != expected_uninstall for item in registrations()):
            raise RuntimeError("Uninstaller command changed or is outside the owned target")
        result = subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/LOG=" + str(smoke_root / "uninstall.log")], timeout=60)
        report["uninstall_exit"] = result.returncode
        # Inno's detached final cleanup can finish just after the parent returns.
        for _ in range(50):
            if not registrations() and not (target / "installed_launch.py").exists():
                break
            time.sleep(.1)
        if result.returncode or registrations() or (target / "installed_launch.py").exists():
            raise RuntimeError("Owned uninstall did not remove its program/registration")
        after = {str(p.relative_to(data)): sha(p) for p in data.rglob("*") if p.is_file()}
        if after != report["data_hashes_before_uninstall"] or sha(sentinel) != sentinel_hash:
            raise RuntimeError("Uninstall changed the preserved business fixture")
        report.update(status="PASS", uninstalled_owned_target=True, business_data_preserved=True,
                      final_registrations=registrations(), installer_unchanged=sha(installer) == build["installer"]["sha256"])
    except Exception as error:
        report.update(status="FAILED", error=str(error), owned_process_running=process.poll() is None)
        # Do not kill any process or run broad cleanup on failure; preserve exact diagnostics.
        raise
    finally:
        stdout.close(); stderr.close(); save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.build_report.resolve(), args.work_dir), indent=2))
