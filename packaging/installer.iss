; Inno Setup script for Secure Notes.
; Build:  powershell -File packaging\build_installer.ps1   (runs PyInstaller first)
; Or:     ISCC.exe packaging\installer.iss                 (expects dist\NotesApp)

#define AppName "Secure Notes"
#define AppVersion "1.4.0"
#define AppPublisher "Niranjan Gadgil"
#define AppExeName "NotesApp.exe"
; Must match APP_USER_MODEL_ID in app/UI/brand.py so the taskbar groups/pins correctly.
#define AppUserModelID "SecureNotes.Desktop.App"

[Setup]
; Never change AppId: it identifies the product for upgrades and uninstall.
AppId={{7F3C2A91-5B6E-4D8A-9C1F-2E4B6A8D0C35}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); users may choose all-users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=SecureNotes-Setup-{#AppVersion}-x64
SetupIconFile=..\assets\notes.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\NotesApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Old files from a previous version are removed so stale modules never load.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall

; Encrypted vaults live in %LOCALAPPDATA%\Secure Notes and are deliberately NOT
; removed on uninstall, so reinstalling or upgrading never destroys user data.

