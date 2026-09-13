"""Preserve a verified portable runtime/wrappers; overlay a pinned clean public commit."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile

from build_installer import validate_zip

SKIP = {".gitignore", "START SHIFTBRIEF.cmd", "README.md", "BROWSER-BUILD.md", "BROWSER_API.md",
        "browser-dependencies.json", "build_browser.py"}
WRAPPERS = ("portable_launch.py", "Start ShiftBrief.cmd", "Open ShiftBrief.vbs")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def update(old_zip, old_sha, old_commit, repo, commit, output):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An exact source commit is required")
    if output.exists():
        raise ValueError("Portable output must be a new directory")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
        raise ValueError("Expected clean source checkout changed")
    raw = old_zip.read_bytes()
    if sha(raw) != old_sha:
        raise ValueError("Preserved portable ZIP changed")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        records, old_manifest = validate_zip(archive, old_commit)
        members = {relative: archive.read(entry) for relative, entry in records.values()}
    preserved = {name: sha(data) for name, data in members.items() if name.startswith("runtime/") or name in WRAPPERS}
    sources = {}
    for name in git("ls-tree", "-r", "--name-only", commit).decode().splitlines():
        if "/" in name or name in SKIP:
            continue
        if name.startswith(".") or any(word in name.casefold() for word in ("credential", "secret", "voice-pack")):
            raise ValueError("Unexpected private/configuration source: " + name)
        data = git("show", commit + ":" + name)
        if name in WRAPPERS:
            raise ValueError("Source commit collides with preserved portable wrapper")
        members[name] = data
        sources[name] = {"sha256": sha(data), "bytes": len(data)}
    for name in set(old_manifest["source_files"]) - set(sources):
        members.pop(name, None)
    members["SOURCE-README.md"] = git("show", commit + ":README.md")
    readme = members["README.md"].decode("utf-8")
    if old_commit not in readme:
        raise ValueError("Portable README no longer contains its old source binding")
    members["README.md"] = readme.replace(old_commit, commit).encode("utf-8")
    manifest = {"schema": "shiftbrief.portable-source.v1", "commit": commit, "source_files": sources,
                "source_readme_sha256": sha(members["SOURCE-README.md"]),
                "portable_wrappers": {name: {"path": name, "sha256": sha(members[name]), "bytes": len(members[name])} for name in WRAPPERS},
                "runtime_file_count": sum(name.startswith("runtime/") for name in preserved),
                "model_weights_included": False, "saved_state_included": False}
    members["SOURCE-MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    for name, expected in preserved.items():
        if sha(members[name]) != expected:
            raise ValueError("Preserved runtime or launcher changed")
    output.mkdir(parents=True)
    package = output / "ShiftBrief-Windows-Portable-0.1.0.zip"
    with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(members.items()):
            archive.writestr("ShiftBrief/" + name, data)
    with zipfile.ZipFile(package) as archive:
        validate_zip(archive, commit)
        for name, expected in preserved.items():
            if sha(archive.read("ShiftBrief/" + name)) != expected:
                raise ValueError("Written ZIP did not preserve runtime or launcher")
    if sha(old_zip.read_bytes()) != old_sha:
        raise ValueError("Predecessor archive changed during packaging")
    report = {"status": "PACKAGED_NOT_LAUNCHED_OR_PUBLISHED", "source_commit": commit,
              "predecessor": {"path": str(old_zip), "sha256": old_sha, "source_commit": old_commit},
              "zip": {"path": str(package), "sha256": sha(package.read_bytes()), "bytes": package.stat().st_size},
              "source_file_count": len(sources), "runtime_files_preserved": manifest["runtime_file_count"],
              "wrappers_preserved": list(WRAPPERS), "payload_files": {name: sha(data) for name, data in members.items()},
              "no_saved_data_or_models_added": True, "helper_sha256": sha(Path(__file__).read_bytes())}
    (output / "PORTABLE-BUILD-RESULT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {key: value for key, value in report.items() if key != "payload_files"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-zip", type=Path, required=True)
    parser.add_argument("--old-sha256", required=True)
    parser.add_argument("--old-commit", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(update(args.old_zip.resolve(), args.old_sha256, args.old_commit, args.repo.resolve(), args.commit,
                            args.output.resolve()), indent=2))
