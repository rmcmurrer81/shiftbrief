"""Stage an exact portable ZIP into a new build, then optionally compile Inno Setup."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import re
import shutil
import stat
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
APP_VERSION = "0.1.0"
ISCC = Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe"
EXCLUDED_WRAPPERS = {"portable_launch.py", "Start ShiftBrief.cmd", "Open ShiftBrief.vbs"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_zip(archive, expected_commit):
    records = {}
    total = 0
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if ("\\" in entry.filename or path.is_absolute() or ".." in path.parts or
                not path.parts or path.parts[0] != "ShiftBrief" or
                any(":" in part or part.endswith((".", " ")) for part in path.parts)):
            raise ValueError("Unsafe or unexpected archive path: " + entry.filename)
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError("Symbolic links are not valid payload files")
        if entry.is_dir():
            continue
        if len(path.parts) < 2:
            raise ValueError("Payload file lacks a relative path")
        relative = str(PurePosixPath(*path.parts[1:]))
        key = relative.casefold()
        if key in records:
            raise ValueError("Duplicate archive destination: " + relative)
        if path.parts[1].casefold() in {"data", ".git", ".env", "models", "voices", "references"}:
            raise ValueError("Private or mutable root is forbidden: " + relative)
        total += entry.file_size
        if entry.file_size > 64 * 1024 * 1024 or total > 512 * 1024 * 1024 or len(records) >= 12000:
            raise ValueError("Payload exceeds build limits")
        records[key] = (relative, entry)
    required = {"source-manifest.json", "server.py", "index.html", "license",
                "runtime/python.exe", "runtime/pythonw.exe", "runtime/python314._pth"}
    if not required.issubset(records):
        raise ValueError("Incomplete portable application")
    manifest = json.loads(archive.read(records["source-manifest.json"][1]))
    if manifest.get("schema") != "shiftbrief.portable-source.v1" or manifest.get("commit") != expected_commit:
        raise ValueError("Source manifest is not bound to the requested commit")
    files = manifest.get("source_files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Empty application source manifest")
    for relative, record in files.items():
        found = records.get(relative.casefold())
        if found is None or found[0] != relative:
            raise ValueError("Source manifest file missing: " + relative)
        raw = archive.read(found[1])
        if digest(raw) != record.get("sha256") or len(raw) != record.get("bytes"):
            raise ValueError("Source manifest hash mismatch: " + relative)
    return records, manifest


def build(zip_path, expected_sha, expected_commit, output, compile_setup=False):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Exact lowercase ZIP SHA256 and source commit are required")
    raw = zip_path.read_bytes()
    if digest(raw) != expected_sha:
        raise ValueError("Portable ZIP hash changed")
    if output.exists():
        raise ValueError("Build output must be a new directory")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        records, manifest = validate_zip(archive, expected_commit)
        payload = output / "payload"
        payload.mkdir(parents=True)
        preserved = {}
        for relative, entry in records.values():
            if relative in EXCLUDED_WRAPPERS:
                continue
            target = payload.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(entry)
            target.write_bytes(data)
            preserved[relative] = digest(data)
    for name in ("installed_launch.py", "INSTALLED-README.txt"):
        shutil.copyfile(HERE / name, payload / name)
    # README for this distribution describes the installed data location.
    shutil.copyfile(payload / "README.md", payload / "PORTABLE-README-SOURCE.md")
    (payload / "README.md").write_text((HERE / "INSTALLED-README.txt").read_text(encoding="utf-8"), encoding="utf-8")
    preserved.pop("README.md", None)
    installed_manifest = {"schema": "shiftbrief.installer-payload.v1", "version": APP_VERSION,
        "source_commit": expected_commit, "portable_zip_sha256": expected_sha,
        "application_sources": manifest["source_files"], "excluded_portable_wrappers": sorted(EXCLUDED_WRAPPERS),
        "preserved_files": preserved, "installed_launcher_sha256": digest((payload / "installed_launch.py").read_bytes()),
        "business_data": "%LOCALAPPDATA%/ShiftBrief/data", "models_included": False}
    (payload / "INSTALLER-MANIFEST.json").write_text(json.dumps(installed_manifest, indent=2), encoding="utf-8")
    report = {"status": "STAGED_NOT_COMPILED", "version": APP_VERSION, "source_commit": expected_commit,
        "portable_zip": {"path": str(zip_path), "sha256": expected_sha}, "payload": str(payload),
        "source_pins": {p.name: digest(p.read_bytes()) for p in [HERE / "build_installer.py", HERE / "ShiftBrief.iss", HERE / "installed_launch.py", HERE / "INSTALLED-README.txt"]},
        "payload_files": {str(p.relative_to(payload)).replace("\\", "/"): digest(p.read_bytes()) for p in payload.rglob("*") if p.is_file()},
        "install_executed": False, "published": False}
    if compile_setup:
        if not ISCC.is_file():
            raise FileNotFoundError("The existing Inno Setup compiler was not found")
        command = [str(ISCC), "/Qp", "/DPayloadDir=" + str(payload.resolve()),
                   "/DBuildOutputDir=" + str((output / "installer").resolve()), str(HERE / "ShiftBrief.iss")]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (output / "compiler.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Inno compilation failed; see compiler.log")
        installer = output / "installer" / f"ShiftBrief-Setup-{APP_VERSION}.exe"
        report.update(status="COMPILED_NOT_INSTALLED_OR_PUBLISHED", installer={"path": str(installer),
            "sha256": digest(installer.read_bytes()), "bytes": installer.stat().st_size}, compiler_sha256=digest(ISCC.read_bytes()))
    (output / "BUILD-RESULT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable-zip", type=Path, required=True)
    parser.add_argument("--zip-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.portable_zip.resolve(), args.zip_sha256, args.source_commit, args.output.resolve(), args.compile), indent=2))
