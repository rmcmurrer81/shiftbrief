; Built only from the hash-verified staged portable package. No network downloads.
#ifndef PayloadDir
  #error PayloadDir must be supplied by build_installer.py
#endif
#ifndef BuildOutputDir
  #error BuildOutputDir must be supplied by build_installer.py
#endif
#define AppVersion "0.1.0"

[Setup]
AppId={{1A16CC9E-46AB-43B5-8E2D-E6294096E312}
AppName=ShiftBrief
AppVersion={#AppVersion}
AppPublisher=Kira Labs / Robert McMurrer
AppPublisherURL=https://kiralabs.org/projects.html#shiftbrief
AppSupportURL=https://github.com/rmcmurrer81/shiftbrief
AppUpdatesURL=https://github.com/rmcmurrer81/shiftbrief/releases
DefaultDirName={localappdata}\Programs\ShiftBrief
DefaultGroupName=ShiftBrief
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
LicenseFile={#PayloadDir}\LICENSE
InfoAfterFile={#PayloadDir}\INSTALLED-README.txt
OutputDir={#BuildOutputDir}
OutputBaseFilename=ShiftBrief-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=ShiftBrief
UninstallDisplayIcon={app}\runtime\pythonw.exe
AppMutex=Local\ShiftBrief-1A16CC9E-46AB-43B5-8E2D-E6294096E312
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ShiftBrief"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\installed_launch.py"""; WorkingDir: "{app}"
Name: "{group}\Close ShiftBrief"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\installed_launch.py"" --stop"; WorkingDir: "{app}"
Name: "{group}\Uninstall ShiftBrief"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ShiftBrief"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\installed_launch.py"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\installed_launch.py"""; Description: "Open ShiftBrief"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent unchecked

; No UninstallDelete section. Business data is outside {app} and must survive.
