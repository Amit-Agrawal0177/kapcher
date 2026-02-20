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
Source: "dist\kapcher_client.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Kapcher Client"; Filename: "{app}\kapcher_client.exe"
Name: "{userdesktop}\Kapcher Client"; Filename: "{app}\kapcher_client.exe"

; Auto start on Windows login
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
ValueType: string; ValueName: "KapcherClient"; \
ValueData: """{app}\kapcher_client.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\kapcher_client.exe"; \
Description: "Launch Kapcher Client"; \
Flags: nowait postinstall skipifsilent
