$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$staging = Join-Path $root "work\local-agent-package"
$payload = Join-Path $staging "ai_web_project"
$downloadDir = Join-Path $root "frontend\downloads"
$zipPath = Join-Path $downloadDir "LocalAgent.zip"
$sourcePython = (Get-Content (Join-Path $root "backend\.venv\pyvenv.cfg") |
    Where-Object { $_ -like "base-prefix = *" } |
    Select-Object -First 1) -replace "^base-prefix = ", ""
$sourceSitePackages = Join-Path $root "backend\.venv\Lib\site-packages"

if (-not (Test-Path $sourcePython)) {
    throw "Bundled Python source not found: $sourcePython"
}
if (-not (Test-Path $sourceSitePackages)) {
    throw "Virtualenv site-packages not found: $sourceSitePackages"
}

if (Test-Path $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $payload | Out-Null
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null

Copy-Item -LiteralPath (Join-Path $root "backend") -Destination (Join-Path $payload "backend") -Recurse
Copy-Item -LiteralPath (Join-Path $root "chatgpt-login-only-extension") -Destination (Join-Path $payload "chatgpt-login-only-extension") -Recurse
Copy-Item -LiteralPath (Join-Path $root "frontend") -Destination (Join-Path $payload "frontend") -Recurse

$payloadDownloads = Join-Path $payload "frontend\downloads"
if (Test-Path $payloadDownloads) {
    Remove-Item -LiteralPath $payloadDownloads -Recurse -Force
}

$runtime = Join-Path $payload "runtime"
Copy-Item -LiteralPath $sourcePython -Destination $runtime -Recurse
$runtimeSitePackages = Join-Path $runtime "Lib\site-packages"
if (Test-Path $runtimeSitePackages) {
    Remove-Item -LiteralPath $runtimeSitePackages -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeSitePackages | Out-Null
Copy-Item -Path (Join-Path $sourceSitePackages "*") -Destination (Join-Path $runtime "Lib\site-packages") -Recurse

foreach ($name in @("uploads", "work", "datasets", "models")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $payload $name) | Out-Null
}

Copy-Item -LiteralPath (Join-Path $root "local-agent-package\install-local-agent.ps1") -Destination $staging
Copy-Item -LiteralPath (Join-Path $root "local-agent-package\start-local-agent.ps1") -Destination $staging

foreach ($path in @(
    (Join-Path $payload "backend\.venv"),
    (Join-Path $payload "backend\__pycache__"),
    (Join-Path $payload "runtime\Lib\site-packages\pip")
)) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

Get-ChildItem (Join-Path $payload "runtime\Lib\site-packages") -Directory -Filter "pip-*.dist-info" |
    Remove-Item -Recurse -Force

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

Write-Host "Built $zipPath"
