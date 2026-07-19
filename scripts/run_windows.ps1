<#
Career Radar 的 Windows 任务计划入口。
脚本使用项目自己的虚拟环境，并把配置路径固定为项目根目录下的 config.yaml，
因此任务计划程序即使从 C:\Windows\System32 启动也不会找错文件。
#>

param(
    [string]$ConfigPath = ""
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
& $PythonExe -m career_radar run --config $ConfigPath
exit $LASTEXITCODE

