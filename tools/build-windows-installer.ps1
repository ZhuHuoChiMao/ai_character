$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$downloadDir = Join-Path $root "frontend\downloads"
$zipPath = Join-Path $downloadDir "LocalAgent.zip"
$setupPath = Join-Path $downloadDir "LocalAgentSetup.exe"
$installerWork = Join-Path $root "work\local-agent-installer"
$sedPath = Join-Path $installerWork "LocalAgentSetup.sed"
$stubExe = Join-Path $installerWork "LocalAgentSetupStub.exe"
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not ($args -contains "-SkipPackage")) {
    & powershell.exe -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build-local-agent-package.ps1")
}

if (Test-Path $installerWork) {
    Remove-Item -LiteralPath $installerWork -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $installerWork | Out-Null

Copy-Item -LiteralPath $zipPath -Destination (Join-Path $installerWork "LocalAgent.zip") -Force
Copy-Item -LiteralPath (Join-Path $root "local-agent-package\bootstrap-install.ps1") -Destination (Join-Path $installerWork "bootstrap-install.ps1") -Force

if (Test-Path $setupPath) {
    Remove-Item -LiteralPath $setupPath -Force
}

if (Test-Path $csc) {
    & $csc /nologo /target:exe /platform:anycpu /out:$stubExe /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll (Join-Path $PSScriptRoot "LocalAgentSetupStub.cs")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to compile LocalAgentSetupStub.cs"
    }

    $marker = [System.Text.Encoding]::ASCII.GetBytes("LOCAL_AGENT_ZIP_PAYLOAD_V1`n")
    $setupStream = [System.IO.File]::Create($setupPath)
    try {
        $stubBytes = [System.IO.File]::ReadAllBytes($stubExe)
        $zipBytes = [System.IO.File]::ReadAllBytes($zipPath)
        $setupStream.Write($stubBytes, 0, $stubBytes.Length)
        $setupStream.Write($marker, 0, $marker.Length)
        $setupStream.Write($zipBytes, 0, $zipBytes.Length)
    }
    finally {
        $setupStream.Dispose()
    }

    Write-Host "Built $setupPath"
    exit 0
}

$sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=Local Agent installation finished.
TargetName=$setupPath
FriendlyName=Local Agent Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -File bootstrap-install.ps1
PostInstallCmd=<None>
FILE0=bootstrap-install.ps1
FILE1=LocalAgent.zip

[SourceFiles]
SourceFiles0=$installerWork\

[SourceFiles0]
%FILE0%=
%FILE1%=
"@

$sed | Set-Content -LiteralPath $sedPath -Encoding ASCII

& iexpress.exe /N /Q $sedPath

for ($attempt = 0; $attempt -lt 20 -and -not (Test-Path $setupPath); $attempt++) {
    Start-Sleep -Milliseconds 500
}

if (-not (Test-Path $setupPath)) {
    throw "IExpress did not create $setupPath"
}

Write-Host "Built $setupPath"
