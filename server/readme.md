venv\Scripts\activate

terminal
python -m PyInstaller --onefile --name kapcher --icon=icon.ico --add-data "templates;templates" --add-data "static;static" app.py

without terminal
python -m PyInstaller --onefile --windowed --name kapcherServer --icon=icon.ico --add-data "templates;templates" --add-data "static;static" app.py


iss file for exe password protected
; ================================
;  KAPCHER SERVER INSTALLER
; ================================

[Setup]
AppId=KapcherServer
AppName=Kapcher Server
AppVersion=1.0
AppPublisher=Kapcher
DefaultDirName={pf}\KapcherServer
DefaultGroupName=Kapcher
OutputBaseFilename=KapcherServerSetup
Compression=lzma
SolidCompression=yes
Password=12345
SetupIconFile=icon.ico
PrivilegesRequired=admin
WizardStyle=modern

; ================================
; FILES TO INSTALL
; ================================

[Files]
Source: "dist\kapcher.exe"; DestDir: "{app}"; Flags: ignoreversion

; ================================
; SHORTCUTS
; ================================

[Icons]
Name: "{group}\Kapcher Server"; Filename: "{app}\kapcher.exe"
Name: "{commondesktop}\Kapcher Server"; Filename: "{app}\kapcher.exe"

; ================================
; AUTO START ON WINDOWS BOOT
; ================================

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
ValueType: string; ValueName: "KapcherServer"; \
ValueData: """{app}\kapcher.exe"""; Flags: uninsdeletevalue

; ================================
; RUN AFTER INSTALL
; ================================

[Run]
Filename: "{app}\kapcher.exe"; \
Description: "Launch Kapcher Server"; \
Flags: nowait postinstall skipifsilent

