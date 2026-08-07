param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Status", "Install", "Remove")]
    [string]$Action,
    [string]$DailyTime = "08:00",
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
$TaskName = "Career Radar Daily Monitor"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$RunScript = Join-Path $PSScriptRoot "run_windows.ps1"
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ProjectDir "config.yaml"
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)

function Write-TaskStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        [ordered]@{
            installed = $false
            taskName = $TaskName
            state = "not_installed"
            nextRunAt = $null
            lastRunAt = $null
            lastResult = $null
        } | ConvertTo-Json -Compress
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    [ordered]@{
        installed = $true
        taskName = $TaskName
        state = [string]$task.State
        nextRunAt = if ($info.NextRunTime) { $info.NextRunTime.ToString("o") } else { $null }
        lastRunAt = if ($info.LastRunTime -and $info.LastRunTime.Year -gt 1900) { $info.LastRunTime.ToString("o") } else { $null }
        lastResult = $info.LastTaskResult
    } | ConvertTo-Json -Compress
}

if ($Action -eq "Status") {
    Write-TaskStatus
    exit 0
}

if ($Action -eq "Install") {
    if ($DailyTime -notmatch "^(?:[01]\d|2[0-3]):[0-5]\d$") {
        throw "Invalid daily run time"
    }
    if (-not (Test-Path -LiteralPath $RunScript)) {
        throw "Runner script not found"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Config file not found"
    }
    $taskAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -ConfigPath `"$ConfigPath`"" `
        -WorkingDirectory $ProjectDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $DailyTime
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 4)
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Description "Career Radar daily public recruitment monitor" `
        -Action $taskAction `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
    Write-TaskStatus
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-TaskStatus
