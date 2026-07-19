<# Career Radar 本地 Web 管理端启动入口。仅监听 127.0.0.1。 #>

param(
    [string]$ConfigPath = "",
    [int]$Port = 8000
)

$ProjectDir = Split-Path -Parent $PSScriptRoot
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ProjectDir "config.yaml"
}
$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Error "找不到虚拟环境：$PythonExe。请先按 README 完成安装。"
    exit 2
}

Set-Location -LiteralPath $ProjectDir
& $PythonExe -m career_radar serve --config $ConfigPath --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
