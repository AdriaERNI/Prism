#ifndef AppVer
  #define AppVer "0.0.0"
#endif

[Setup]
AppName=Prism
AppVersion={#AppVer}
DefaultDirName={autopf}\prism
DefaultGroupName=Prism
OutputDir=C:\vagrant\dist
OutputBaseFilename=prism-{#AppVer}-setup
Compression=lzma
SolidCompression=yes
ChangesEnvironment=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#AppVer}
VersionInfoProductName=Prism
VersionInfoProductVersion={#AppVer}

[Files]
Source: "C:\vagrant\dist\prism-{#AppVer}.exe"; DestDir: "{app}"; DestName: "prism.exe"; Flags: ignoreversion

[Icons]
Name: "{group}\Prism"; Filename: "{app}\prism.exe"
Name: "{group}\Uninstall Prism"; Filename: "{uninstallexe}"

[Code]
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