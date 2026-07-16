; Prism — Inno Setup installer script
; Minimal installer: installs prism.exe to Program Files, adds to PATH.
; No Start Menu, no desktop icons. The binary and installer have the Prism logo.

#ifndef AppVer
  #define AppVer "0.0.0"
#endif
#ifndef AppVerFile
  #define AppVerFile AppVer
#endif

[Setup]
AppName=Prism
AppVersion={#AppVer}
AppPublisher=Adria Sanchez
AppPublisherURL=https://github.com/AdriaERNI/Prism
AppSupportURL=https://github.com/AdriaERNI/Prism/issues
AppContact=https://github.com/AdriaERNI/Prism

; Install to Program Files
DefaultDirName={autopf}\Prism
DisableProgramGroupPage=yes
; No Start Menu group at all
DefaultGroupName=

; Output
OutputDir=.
OutputBaseFilename=prism-{#AppVerFile}-setup

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Privileges
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Version info (shows in file properties)
VersionInfoVersion={#AppVer}
VersionInfoProductName=Prism
VersionInfoProductVersion={#AppVer}
VersionInfoCompany=Adria Sanchez
VersionInfoDescription=Prism — InterSystems IRIS CLI and MCP Server
VersionInfoCopyright=Copyright (C) 2026 Adria Sanchez

; Custom icons for the installer and uninstaller
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\prism.exe

; Wizard images (logo in sidebar + header)
WizardImageFile=docs\assets\wizard-sidebar.bmp
WizardSmallImageFile=docs\assets\wizard-header.bmp

; Minimize wizard pages — Prism is a CLI tool, not a GUI app
DisableWelcomePage=yes
DisableReadyPage=no
DisableFinishedPage=no
ShowLanguageDialog=no
LanguageDetectionMethod=none

; Environment
ChangesEnvironment=yes

; Uninstall
UninstallDisplayName=Prism
CreateUninstallRegKey=yes

[Files]
Source: "prism-{#AppVerFile}.exe"; DestDir: "{app}"; DestName: "prism.exe"; Flags: ignoreversion

; No [Icons] section — no Start Menu, no desktop shortcuts
; The exe is a CLI tool accessed via PATH, not a GUI app launched from a menu

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function NeedRestart(): Boolean;
begin
  // Request restart so PATH changes propagate to new terminal sessions
  Result := False;
end;

procedure EnvAddPath(Path: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Paths) then
    Paths := '';
  if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') > 0 then
    exit;
  if Paths <> '' then
    Paths := Paths + ';';
  Paths := Paths + Path;
  RegWriteStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Paths);
end;

procedure EnvRemovePath(Path: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Paths) then
    exit;
  P := Pos(';' + Uppercase(Path), ';' + Uppercase(Paths));
  if P = 0 then exit;
  Delete(Paths, P - 1, Length(Path) + 1);
  RegWriteStringValue(HKLM, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
