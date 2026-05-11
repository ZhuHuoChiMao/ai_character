$profile = Join-Path $PSScriptRoot "chrome-cdp-profile"
$extension = Join-Path $PSScriptRoot "chatgpt-login-only-extension"
$chrome = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"

if (-not (Test-Path $chrome)) {
    $chrome = "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
}

if (-not (Test-Path $chrome)) {
    throw "未找到 Google Chrome: $chrome"
}

Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$profile",
    "--disable-extensions-except=$extension",
    "--load-extension=$extension",
    "https://chatgpt.com/"
)

Write-Host "Chrome 已用远程调试端口 9222 启动。请在打开的窗口里登录 ChatGPT。"
