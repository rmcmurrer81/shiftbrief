# ShiftBrief 0.1.0 Windows installer

Version 0.1.0 is released. [Download the installer](https://github.com/rmcmurrer81/shiftbrief/releases/download/v0.1.0/ShiftBrief-Setup-0.1.0.exe), or open the [release page](https://github.com/rmcmurrer81/shiftbrief/releases/tag/v0.1.0) for the portable ZIP and `SHA256SUMS.txt`. The released application source is commit `77b4c6275f48346bfd88fc842765cbb20e1669ad`; later documentation updates do not change that tested tag or its assets.

## Install and use

Run `ShiftBrief-Setup-0.1.0.exe` on Windows 10 or newer, using an x64-compatible system. This per-user installer includes Python and the application dependencies; no separate Python setup is required. Open **ShiftBrief** from the Start menu. A **Create a desktop shortcut** option is unchecked by default.

The app opens a local browser interface and starts with a blank business. **Load demo** explicitly adds the fictional Maple Street example. **Records · offline** requires no account, API key or model download. Optional AI needs a separately configured provider and model; model weights, personal voice files and saved business data are not bundled.

The program lives under `%LOCALAPPDATA%\Programs\ShiftBrief`. Business data lives under `%LOCALAPPDATA%\ShiftBrief\data`. Use **Save business copy** or **Back up all businesses** to make portable backups. Closing the browser does not stop the local server: choose **Start → ShiftBrief → Close ShiftBrief** before upgrading or uninstalling. Uninstall through Windows Settings or the Start-menu entry. Uninstall removes the program and retains the separate business-data folder.

## Release verification

The published installer is **39,768,239 bytes**, with SHA-256:

```text
51d85d37688ed3cfbdf15452731edc2ddecd11a3fcd012d40504ca0663631e6c
```

The release asset was downloaded without authentication and matched those bytes and checksum. An isolated installed-app smoke test passed: setup, exact installed payload hashes, blank first run, second-launch reuse, rejection of a foreign shutdown token, graceful close, uninstall, and preservation of a sentinel in the separate data folder. No model or external service was invoked.

That smoke test used silent setup with `/NOICONS`, a temporary install target and temporary data location. It did **not** visually check the installer wizard or create/click the optional desktop shortcut. The shortcut behavior above is defined in `ShiftBrief.iss`; it is not claimed as a completed visual test.

## Build and maintain

`build_installer.py` stages an exact portable ZIP, checks its SHA-256 and source manifest against the supplied commit, and refuses an existing output directory. It compiles with an existing Inno Setup 6 compiler at `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`; the build does not download tools or runtime assets. Supply `--portable-zip`, `--zip-sha256`, `--source-commit`, `--output`, and `--compile`. Keep new build outputs separate from the released artifacts.

The installed launcher uses an exact-instance token and loopback shutdown endpoint to close its own server gracefully. An OS mutex and file lock remain held until exit; Inno Setup checks the same AppMutex during setup and uninstall. It does not search for or forcibly terminate other processes. Business data is outside the installer file list, with no custom uninstall deletion.

For future lifecycle checks, use a new temporary install directory and `/NOICONS`. Verify there is no existing registration for this AppId before setup, isolate `LOCALAPPDATA` for the launched test app, and uninstall only that owned target. Confirm its separate data sentinel survives. See `smoke_installer.py` and `test_installer.py` for the bounded verification workflow.
