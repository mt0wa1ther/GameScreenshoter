; ============================================================
;  Game Screenshoter — установщик с EULA и выбором папки
; ============================================================

#define MyAppName      "Game Screenshoter"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "GameScreenshoter Team"
#define MyAppURL       "https://github.com/mt0wa1ther/GameScreenshoter"
#define MyAppExeName   "GameScreenshoter.exe"

[Setup]
AppId={{8E3C7F41-2A9D-4B5E-9C1F-7D0A3E6B8C24}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=GameScreenshoter_Setup_v{#MyAppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
LicenseFile=license.txt

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные значки:"; Flags: checkedonce
Name: "startupicon"; Description: "Запускать при входе в Windows"; GroupDescription: "Дополнительные значки:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico";      DestDir: "{app}\assets"; Flags: ignoreversion
Source: "license.txt";          DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";              Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}";      Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}";        Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\assets"

; ============================================================
;  Логика: 
;   • Первая установка → показываем ВСЕ страницы (в т.ч. выбор папки)
;   • Обновление → пропускаем папку, задачи, лицензию, финал
; ============================================================
[Code]
var
  IsUpdateInstall: Boolean;

function GetUninstallString(): String;
var
  Key, Value: String;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E3C7F41-2A9D-4B5E-9C1F-7D0A3E6B8C24}_is1';
  Value := '';
  if not RegQueryStringValue(HKLM, Key, 'UninstallString', Value) then
    RegQueryStringValue(HKCU, Key, 'UninstallString', Value);
  Result := Value;
end;

function InitializeSetup(): Boolean;
begin
  IsUpdateInstall := (GetUninstallString() <> '');
  Result := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // Пропускаем страницы ТОЛЬКО при обновлении
  if IsUpdateInstall then
  begin
    if (PageID = wpSelectDir) or      // выбор папки
       (PageID = wpSelectTasks) or    // галочки ярлыков
       (PageID = wpLicense) or        // лицензия (уже принята)
       (PageID = wpReady) or          // готов к установке
       (PageID = wpFinished) then     // финальный экран
      Result := True;
  end;
  // При первой установке ничего не пропускаем — все страницы показываются
end;

procedure InitializeWizard();
begin
  if IsUpdateInstall then
    WizardForm.Caption := '{#MyAppName} — Установка версии {#MyAppVersion}';
end;