
#define MyAppName "Synapse"

#define VersionFile FileOpen("..\Application\version.txt")

#if VersionFile == 0
  #error "Could not open Application\version.txt"
#endif

#define MyAppVersion Trim(FileRead(VersionFile))

#expr FileClose(VersionFile)
#undef VersionFile

#define MyAppPublisher "Synapse"
#define MyAppExeName "Synapse.exe"

[Setup]
; NEVER change this GUID between releases.
AppId={{B8E4A2C1-73D9-4F65-9A21-C6E8D3B50742}

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\Synapse
DefaultGroupName=Synapse

UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes

Uninstallable=yes

PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

WizardStyle=modern
DisableProgramGroupPage=yes

OutputDir=installer-output
OutputBaseFilename=Synapse-Setup-{#MyAppVersion}

SetupIconFile=..\Application\assets\synapse_logo.ico
UninstallDisplayIcon={app}\Synapse.exe

Compression=lzma2
SolidCompression=yes

CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; \
    Description: "Create a desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; \
    Flags: unchecked

[Files]
Source: "dist\Synapse\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Synapse"; \
    Filename: "{app}\{#MyAppExeName}"

Name: "{autodesktop}\Synapse"; \
    Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch Synapse"; \
    Flags: postinstall nowait skipifsilent
