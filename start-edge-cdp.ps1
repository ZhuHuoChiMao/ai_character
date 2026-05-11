$profile = Join-Path $PSScriptRoot "edge-cdp-profile"
$extension = Join-Path $PSScriptRoot "chatgpt-login-only-extension"
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"

if (-not (Test-Path $edge)) {
    $edge = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}

if (-not (Test-Path $edge)) {
    throw "未找到 Microsoft Edge: $edge"
}

Start-Process -FilePath $edge -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$profile",
    "--disable-extensions-except=$extension",
    "--load-extension=$extension",
    "https://chatgpt.com/"
)

Write-Host "Edge 已用远程调试端口 9222 启动。请在打开的窗口里登录 ChatGPT。"
