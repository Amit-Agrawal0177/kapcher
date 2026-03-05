[Setup]
AppId=KapcherClient
AppName=Kapcher Client
AppVersion=1.0
AppPublisher=Kapcher
DefaultDirName={localappdata}\KapcherClient
DefaultGroupName=Kapcher Client
OutputBaseFilename=KapcherClientSetup
Compression=lzma
SolidCompression=yes
Password=12345
SetupIconFile=icon.ico
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "dist\kapcherClient.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Kapcher Client"; Filename: "{app}\kapcherClient.exe"
Name: "{userdesktop}\Kapcher Client"; Filename: "{app}\kapcherClient.exe"

; Auto start on Windows login
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
ValueType: string; ValueName: "KapcherClient"; \
ValueData: """{app}\kapcherClient.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\kapcherClient.exe"; \
Description: "Launch Kapcher Client"; \
Flags: nowait postinstall skipifsilent
