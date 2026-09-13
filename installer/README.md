# ShiftBrief 0.1.0 installer candidate

This is an isolated per-user Windows x64 installer definition. It has not yet been built from the final patched source package, installed, or published. The parent task supplies the final portable ZIP, SHA256, and source commit; `build_installer.py` refuses mismatches and existing output directories.

The existing signed Inno Setup compiler is `C:/Users/robmc/AppData/Local/Programs/Inno Setup 6/ISCC.exe`. Compile using its supplied `/D` arguments through the build helper. No tooling download is needed.

The installed app lives under `%LOCALAPPDATA%/Programs/ShiftBrief`. Business data lives under `%LOCALAPPDATA%/ShiftBrief/data`, outside the installer file list. There is no custom uninstall deletion. Start-menu entries open, close, and uninstall the program. The Desktop shortcut is optional and unchecked. Installation does not automatically start a model, download assets, or load the fictional demo.

The installed wrapper is the only lifecycle change: an exact-instance token and loopback shutdown endpoint close its own server gracefully. It keeps an OS mutex and file lock until exit. Inno's [AppMutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm) checks the same mutex for both setup and uninstall. No process search, forced process termination, credential installation, or migration of the owner's live app occurs.

Final testing must use a new owned temporary install directory and `/NOICONS`. Before invoking setup, check that this AppId has no existing HKCU/HKLM uninstall entry in either registry view. Test the exact installed launcher with a process-local temporary LOCALAPPDATA so no real business directory is touched. Verify blank start, second launch reuse, rejected foreign shutdown, graceful close, then uninstall that exact target. Add a sentinel in the temporary data folder and verify its bytes remain afterward. Do not remove unrelated keys or directories.

Anticipated final asset (not yet uploaded): `https://github.com/rmcmurrer81/shiftbrief/releases/download/v0.1.0/ShiftBrief-Setup-0.1.0.exe`. Website publication must wait for a tested uploaded asset and verified checksum.
