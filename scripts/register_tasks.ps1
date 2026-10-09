# register_tasks.ps1 - 注册 Windows 计划任务
# 因为路径含空格，脚本先取 Python 的 8.3 短路径再交给 schtasks

$ErrorActionPreference = "Stop"

# --- 配置 ---
$TaskNameCoordinator = "NewsAggCoordinator"
$TaskNameSupervisor = "NewsAggSupervisor"
$PythonArgsCoordinator = "-m newsagg coordinator"
$PythonArgsSupervisor = "-m newsagg supervisor"

# --- 获取 Python 短路径 ---
function Get-PythonShortPath {
    $pythonPath = (Get-Command python).Source
    $pythonDir = Split-Path $parent $pythonPath
    $fs = [System.IO.File]::OpenRead($pythonPath)
    $shell = New-Object -ComObject Scripting.FileSystemObject
    $shortPath = $shell.GetFile($pythonPath).ShortPath
    $fs.Close()
    return $shortPath
}

# --- 获取项目根目录 ---
$ProjectRoot = Split-Path -parent $PSScriptRoot

# --- 注册协调器任务（每小时） ---
function Register-CoordinatorTask {
    $pythonShort = Get-PythonShortPath
    $action = New-ScheduledTaskAction -Execute $pythonShort `
        -Argument $PythonArgsCoordinator `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Hours 1) `
        -RepetitionDuration ([System.TimeSpan]::MaxValue)

    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    Register-ScheduledTask -TaskName $TaskNameCoordinator `
        -Action $action -Trigger $trigger -Settings $settings `
        -RunLevel Highest -Force | Out-Null

    Write-Host "[OK] $TaskNameCoordinator 已注册（每小时执行）"
}

# --- 注册监督器任务（登录时） ---
function Register-SupervisorTask {
    $pythonShort = Get-PythonShortPath
    $action = New-ScheduledTaskAction -Execute $pythonShort `
        -Argument $PythonArgsSupervisor `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -AtLogOn

    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0)

    Register-ScheduledTask -TaskName $TaskNameSupervisor `
        -Action $action -Trigger $trigger -Settings $settings `
        -RunLevel Highest -Force | Out-Null

    Write-Host "[OK] $TaskNameSupervisor 已注册（登录时执行）"
}

# --- 主逻辑 ---
try {
    Register-CoordinatorTask
    Register-SupervisorTask
    Write-Host ""
    Write-Host "注册完成。如需手动启动监督器："
    Write-Host "  python -m newsagg supervisor"
} catch {
    Write-Host "[ERROR] 注册失败：$_" -ForegroundColor Red
    Write-Host "请手动注册或以管理员身份运行："
    Write-Host "  schtasks /Create /TN `"$TaskNameCoordinator`" /TR `"$pythonShort $PythonArgsCoordinator`" /SC HOURLY /RL HIGHEST /F"
    Write-Host "  schtasks /Create /TN `"$TaskNameSupervisor`" /TR `"$pythonShort $PythonArgsSupervisor`" /SC ONLOGON /RL HIGHEST /F"
    exit 1
}
