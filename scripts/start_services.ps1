# 启动本机开发依赖（MySQL + Redis）。
# 用法（PowerShell，非管理员即可）：
#   pwsh scripts/start_services.ps1
#   pwsh scripts/start_services.ps1 -Stop
#
# 说明：
#   - MySQL 数据目录放在无空格路径 D:\newsagg_mysql_data（规避 PowerShell `\n` 转义坑）。
#   - Redis 用项目内置 .redis5 原生 5.0.14 启动在 6380（6379 的 Memurai 不含 XADD）。
#     进程经 Python detached 拉起，脱离本会话生命周期。

$ErrorActionPreference = 'Stop'

$MYSQL_INI = 'D:/newsagg_mysql_data/my.ini'
$MYSQL_PORT = 3306
$REDIS_PORT = 6380
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$redisBin = Join-Path $root '.redis5\redis-server.exe'
$redisDir = Join-Path $root '.redis5'


function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port })
}


# 用 Python 拉起 detached 子进程，规避 PowerShell 转义/生命周期问题
$spawn = @"
import subprocess
def go(cmd, out):
    with open(out, 'a') as f:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f,
                         stderr=subprocess.STDOUT,
                         creationflags=0x00000008 | 0x00000200)
go(['C:/Program Files/MySQL/MySQL Server 8.4/bin/mysqld.exe', '--defaults-file=$MYSQL_INI'],
   r'D:/newsagg_mysql_data/spawn.out.log')
go(['$($redisBin -replace '\\','/')', '--port', '6380', '--bind', '127.0.0.1',
    '--dir', '$($redisDir -replace '\\','/')'],
   '$($redisDir -replace '\\','/')/spawn.out.log')
print('spawned')
"@

if ($Stop) {
    & $py -c "import subprocess; [subprocess.run(['taskkill','/F','/IM',n],capture_output=True) for n in ('mysqld.exe','redis-server.exe')]"
    Start-Sleep -Seconds 2
    Write-Host "MySQL 3306 : $(if (Test-Port $MYSQL_PORT) { 'UP' } else { 'DOWN' })"
    Write-Host "Redis 6380 : $(if (Test-Port $REDIS_PORT) { 'UP' } else { 'DOWN' })"
    exit 0
}

if (-not (Test-Port $MYSQL_PORT)) { & $py -c $spawn }
for ($i = 0; $i -lt 25 -and -not (Test-Port $MYSQL_PORT); $i++) { Start-Sleep -Seconds 1 }
for ($i = 0; $i -lt 15 -and -not (Test-Port $REDIS_PORT); $i++) { Start-Sleep -Seconds 1 }

Write-Host "MySQL 3306 : $(if (Test-Port $MYSQL_PORT) { 'UP' } else { 'DOWN' })"
Write-Host "Redis 6380 : $(if (Test-Port $REDIS_PORT) { 'UP' } else { 'DOWN' })"
if (-not ((Test-Port $MYSQL_PORT) -and (Test-Port $REDIS_PORT))) {
    Write-Host "有服务未就绪，请查看日志：D:\newsagg_mysql_data\*.err 与 $redisDir\*.log" -ForegroundColor Yellow
    exit 1
}
Write-Host "开发依赖就绪。"
