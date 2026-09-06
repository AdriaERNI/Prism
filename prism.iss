; Prism — Inno Setup installer script
; Minimal installer: installs prism.exe to Program Files, adds to PATH.
; No Start Menu, no desktop icons. The binary and installer have the Prism logo.

#ifndef AppVer
  #define AppVer "0.0.0"
#endif
#ifndef AppVerFile
  #define AppVerFile AppVer
#endif
; VersionInfoVersion must be numeric x.y.z.w — strip pre-release suffix
#ifndef AppVerNumeric
  #define AppVerNumeric "0.0.0.0"
#endif
; The onedir app root (PyInstaller outputs a folder named prism/).
; Relative to the directory containing this .iss. Overridden per build:
;   - Vagrant build-in-vm.ps1:  dist\prism  (iss is at repo root)
;   - CI build-release.yml:     prism        (iss is copied to dist/prism.iss)
#ifndef AppSource
  #define AppSource "dist\prism"
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
VersionInfoVersion={#AppVerNumeric}
VersionInfoProductName=Prism
VersionInfoProductVersion={#AppVerNumeric}
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
; PyInstaller --onedir output: a folder named prism/ containing prism.exe and _internal/.
; Install the entire folder so the companion DLLs and libs travel with the exe
; (avoids the cold-start extraction --onefile pays on every launch).
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; No [Icons] section — no Start Menu, no desktop shortcuts
; The exe is a CLI tool accessed via PATH, not a GUI app launched from a menu

[Code]
{ --------------------------------------------------------------------------- }
{ Microsoft Store return-code mapping (EXE exit codes, all values unique).    }
{                                                                             }
{   Scenario                       EXE code   Basis                            }
{   Installation successful            0      Inno documented (run to          }
{                                            completion)                       }
{   Installation already in progress   1      Inno documented (Setup fails to  }
{                                            initialize - second instance      }
{                                            blocked by the single-instance     }
{                                            mutex)                            }
{   Installation cancelled by user     2      Inno documented (user clicked    }
{                                            Cancel before install started)    }
{   Miscellaneous install failure      4      Inno documented (fatal error     }
{                                            during the actual installation)   }
{   Disk space is full                 7      Inno documented (cannot          }
{                                            continue: prepare-to-install      }
{                                            determined insufficient space)    }
{   Reboot required                    8      Inno documented (cannot          }
{                                            continue; system restart needed)   }
{   Application already exists       100      custom (returned by              }
{                                            GetCustomSetupExitCode below)     }
{   Network failure                 101      custom hook (reserved — set by   }
{                                            your own failure checks if used)  }
{   Package rejected                102      custom hook (reserved — set by   }
{                                            your own failure checks if used)  }
{                                                                             }
{   Reference: https://jrsoftware.org/ishelp/topic_setupexitcodes.htm         }
{                                                                             }
{ Inno returns 0/1/2/4/7/8 automatically on the corresponding conditions.     }
{ 100/101/102 are custom codes reported via GetCustomSetupExitCode, which    }
{ Inno calls only when Setup ran to completion and the exit code would       }
{ otherwise be 0. Windows exit codes are unsigned 32-bit values, so never   }
{ set a negative code here.                                                   }
{                                                                             }
{ Declaration order matters: Inno's Pascal Script is single-pass and has no  }
{ forward references, so every helper is defined before its first use.       }
{ --------------------------------------------------------------------------- }
var
  CustomErrorCode: Integer;        { 0 -> success; 101/102 reserved for hooks }
  WasPreviouslyInstalled: Boolean; { snapshot taken in InitializeSetup        }

{ Application already exists? A previous install record (the uninstall key   }
{ Inno wrote under "Uninstall\<AppId>", i.e. Prism_is1) is present.         }
function DetectApplicationExists(): Boolean;
var
  S: String;
begin
  Result := RegQueryStringValue(
    HKLM,
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Prism_is1',
    'DisplayName', S);
end;

function InitializeSetup(): Boolean;
begin
  { Take the "already installed?" snapshot BEFORE Setup writes anything,     }
  { because Inno creates the uninstall key during the installation itself.   }
  WasPreviouslyInstalled := DetectApplicationExists();
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

{ Report the scenario once Setup has run to completion. Inno calls this      }
{ only when the exit code would otherwise be 0, so returning a non-zero      }
{ value here is how the custom codes reach the Microsoft Store mapping.      }
function GetCustomSetupExitCode: Integer;
begin
  Result := CustomErrorCode;  { 0 -> Installation successful }
  if WasPreviouslyInstalled then
    Result := 100;            { Application already exists on the device }
end;
