; Inno Setup script for RetroBake. packaging/build.py runs it as:
;   iscc /DAppVersion=<version> /DSourceDir=<PyInstaller folder> /DOutDir=<dist> retrobake.iss
; Installs for the current user only, so no administrator prompt.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0F3B1C-8D52-4C47-9A7E-52B4D7C1A0B9}
AppName=RetroBake
AppVersion={#AppVersion}
AppPublisher=Roger (voidwhereprohibited)
AppPublisherURL=https://github.com/voidwhereprohibited/retrobake
DefaultDirName={localappdata}\Programs\RetroBake
DefaultGroupName=RetroBake
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\..\LICENSE
OutputDir={#OutDir}
OutputBaseFilename=RetroBake-Setup-{#AppVersion}
SetupIconFile=..\retrobake.ico
UninstallDisplayIcon={app}\RetroBake.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Put a RetroBake icon on the desktop"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RetroBake"; Filename: "{app}\RetroBake.exe"
Name: "{group}\Uninstall RetroBake"; Filename: "{uninstallexe}"
Name: "{userdesktop}\RetroBake"; Filename: "{app}\RetroBake.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\RetroBake.exe"; Description: "Start RetroBake now"; Flags: nowait postinstall skipifsilent
