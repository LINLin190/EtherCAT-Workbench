#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "EtherCAT Workbench"
#define MyAppExeName "EtherCATWorkbench.exe"
#define NpcapDownloadUrl "https://npcap.com/dist/npcap-1.88.exe"

[Setup]
AppId={{D37C82B2-81A3-43C0-B346-D2DEAE56AA28}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=LINLin190
AppPublisherURL=https://github.com/LINLin190/EtherCAT-Workbench
AppSupportURL=https://github.com/LINLin190/EtherCAT-Workbench/issues
LicenseFile=..\LICENSE.md
DefaultDirName={autopf}\EtherCAT Workbench
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=EtherCATWorkbench-{#MyAppVersion}-Setup-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\EtherCATWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function NpcapVersionAtLeast188(): Boolean;
var
  Version, Rest: String;
  DotPosition, Major, Minor, Patch: Integer;
begin
  Result := False;
  if not GetVersionNumbersString(ExpandConstant('{sys}\Npcap\Packet.dll'), Version) then
    exit;
  DotPosition := Pos('.', Version);
  if DotPosition = 0 then
    exit;
  Major := StrToIntDef(Copy(Version, 1, DotPosition - 1), 0);
  Rest := Copy(Version, DotPosition + 1, Length(Version));
  DotPosition := Pos('.', Rest);
  if DotPosition > 0 then
  begin
    Minor := StrToIntDef(Copy(Rest, 1, DotPosition - 1), 0);
    Rest := Copy(Rest, DotPosition + 1, Length(Rest));
    DotPosition := Pos('.', Rest);
    if DotPosition > 0 then
      Rest := Copy(Rest, 1, DotPosition - 1);
    Patch := StrToIntDef(Rest, 0);
  end
  else
  begin
    Minor := StrToIntDef(Rest, 0);
    Patch := 0;
  end;
  { Packet.dll uses fixed versions like 5.1.79.117 while its product version is 1.79. }
  Result :=
    (Major > 5) or
    ((Major = 5) and ((Minor > 1) or ((Minor = 1) and (Patch >= 88)))) or
    ((Major > 1) and (Major < 5)) or
    ((Major = 1) and (Minor >= 88));
end;

function NpcapReady(): Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{sys}\Npcap\Packet.dll')) and
    FileExists(ExpandConstant('{sys}\Npcap\wpcap.dll')) and
    FileExists(ExpandConstant('{sys}\wpcap.dll')) and
    NpcapVersionAtLeast188();
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ErrorCode: Integer;
begin
  if (CurStep = ssPostInstall) and (not WizardSilent()) and (not NpcapReady()) then
  begin
    if MsgBox(
      'Real EtherCAT 模式需要 Npcap 1.88 或更高版本，并启用 WinPcap API-compatible Mode。' + #13#10 + #13#10 +
      '当前未检测到满足要求的 Npcap。应用仍可安全使用 Demo/Mock 模式。' + #13#10 + #13#10 +
      '是否从 Npcap 官方网站下载 1.88 安装程序？',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', '{#NpcapDownloadUrl}', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
    end;
  end;
end;
