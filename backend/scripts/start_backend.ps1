# 习惯管家后端启动脚本
# ------------------------------------------------------------
# 解决的问题:uvicorn --reload 在 Windows 上会留下持着端口的僵尸进程。
# 父进程绑 socket -> 子进程继承 -> 父进程退出后 socket 仍被占用,
# 而 netstat 显示的 owning PID 已经失效,表现为「PID 杀不掉、端口又不通」。
#
# 用法:
#   .\scripts\start_backend.ps1                # 默认 8000
#   .\scripts\start_backend.ps1 -Port 8001
#   .\scripts\start_backend.ps1 -NoReload      # 不挂 --reload
#   .\scripts\start_backend.ps1 -CheckOnly     # 只体检端口,不启动
#   .\scripts\start_backend.ps1 -HostAddr 127.0.0.1   # 只允许本机访问
#
# 默认监听 0.0.0.0:真机调试时手机要通过局域网 IP 连过来。
param(
    [int]$Port = 8000,
    [string]$HostAddr = '0.0.0.0',
    [switch]$NoReload,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Continue'
$BackendDir = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $BackendDir '.venv\Scripts\python.exe'

Write-Host ''
Write-Host '==================================================' -ForegroundColor Cyan
Write-Host (' 后端启动  port=' + $Port) -ForegroundColor Cyan
Write-Host '==================================================' -ForegroundColor Cyan

if (-not (Test-Path $Py)) {
    Write-Host ('找不到 venv python: ' + $Py) -ForegroundColor Red
    Write-Host '请先: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt' -ForegroundColor Red
    exit 1
}
Write-Host (' 解释器: ' + $Py)
Write-Host (' 版本  : ' + (& $Py -V 2>&1))

# ---- 1. 端口体检 ----
Write-Host ''
Write-Host '[1] 端口体检'
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -eq 0) {
    Write-Host ('  端口 ' + $Port + ' : 空闲') -ForegroundColor Green
} else {
    Write-Host ('  端口 ' + $Port + ' : ' + $listeners.Count + ' 个监听者') -ForegroundColor Yellow
    foreach ($l in $listeners) {
        $procName = '<已退出/查不到>'
        try { $procName = (Get-Process -Id $l.OwningProcess -ErrorAction Stop).ProcessName } catch { }
        Write-Host ('    PID=' + $l.OwningProcess + '  进程=' + $procName)
    }
}

if ($CheckOnly) {
    Write-Host ''
    Write-Host '(-CheckOnly) 仅体检,不启动。' -ForegroundColor DarkGray
    exit 0
}

# ---- 2. 清理僵尸 ----
Write-Host ''
Write-Host '[2] 清理占用者'
foreach ($l in $listeners) {
    $tp = $l.OwningProcess
    taskkill /F /T /PID $tp 2>&1 | Out-Null
    Write-Host ('    taskkill PID=' + $tp)
}
$stray = @(Get-Process python, pythonw -ErrorAction SilentlyContinue)
foreach ($sp in $stray) {
    try {
        Stop-Process -Id $sp.Id -Force -ErrorAction Stop
        Write-Host ('    已清遗留 python PID=' + $sp.Id)
    } catch {
        Write-Host ('    清不掉 python PID=' + $sp.Id + '(可能需要管理员)') -ForegroundColor DarkYellow
    }
}
Start-Sleep -Seconds 1
$still = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($still.Count -gt 0) {
    Write-Host ''
    Write-Host ('端口 ' + $Port + ' 仍被占用,启动会失败。') -ForegroundColor Red
    Write-Host '  用管理员 PowerShell 查真实进程:' -ForegroundColor Red
    Write-Host ('      netstat -anob | Select-String *:' + $Port) -ForegroundColor Red
    Write-Host '      taskkill /F /T /PID <真实PID>' -ForegroundColor Red
    Write-Host ('  或者直接换端口:  .\scripts\start_backend.ps1 -Port 8001') -ForegroundColor Yellow
    exit 1
}
Write-Host '    端口已释放' -ForegroundColor Green

# ---- 3. 启动 ----
Write-Host ''
Write-Host '[3] 启动 uvicorn'
$uvArgs = @('-m', 'uvicorn', 'main:app', '--host', $HostAddr, '--port', ('' + $Port))
if (-not $NoReload) { $uvArgs += '--reload' }
$env:PYTHONIOENCODING = 'utf-8'
$logFile = Join-Path $BackendDir ('uvicorn.' + $Port + '.log')
$proc = Start-Process -FilePath $Py -ArgumentList $uvArgs -WorkingDirectory $BackendDir -RedirectStandardOutput $logFile -RedirectStandardError ($logFile + '.err') -PassThru -WindowStyle Hidden
Write-Host ('    PID=' + $proc.Id)
Write-Host ('    日志=' + $logFile)

# ---- 4. 等健康检查 ----
Write-Host ''
Write-Host '[4] 等待 /health ...'
$ready = $false
for ($i = 0; $i -lt 80; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri ('http://127.0.0.1:' + $Port + '/health') -TimeoutSec 2 -UseBasicParsing
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 700
}

if ($ready) {
    Write-Host ''
    Write-Host '==================================================' -ForegroundColor Green
    Write-Host ' 后端已就绪' -ForegroundColor Green
    Write-Host ('   监听     : ' + $HostAddr + ':' + $Port)
    Write-Host ('   本机接口 : http://127.0.0.1:' + $Port + '/api')
    Write-Host ('   文档     : http://127.0.0.1:' + $Port + '/docs')
    Write-Host ('   健康详情 : http://127.0.0.1:' + $Port + '/health/full')
    Write-Host ('   进程 PID : ' + $proc.Id)
    Write-Host ('   停止     : Stop-Process -Id ' + $proc.Id + ' -Force')

    if ($HostAddr -eq '0.0.0.0') {
        $lanIp = $null
        try {
            $lanIp = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
                Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
                Select-Object -First 1 -ExpandProperty IPAddressToString
        } catch { }

        Write-Host ''
        if ($lanIp) {
            Write-Host ' 真机调试(手机与电脑必须在同一 Wi-Fi):' -ForegroundColor Yellow
            Write-Host ('   手机浏览器先自测: http://' + $lanIp + ':' + $Port + '/health') -ForegroundColor Yellow
            Write-Host ('   小程序 Console 里执行:') -ForegroundColor Yellow
            Write-Host ("     wx.setStorageSync('api_base', 'http://" + $lanIp + ":" + $Port + "/api')") -ForegroundColor Yellow
            Write-Host ('     getApp().applyApiBase()') -ForegroundColor Yellow
            Write-Host '   连不上 = 防火墙没放行。以管理员运行:' -ForegroundColor DarkYellow
            Write-Host ('     netsh advfirewall firewall add rule name="habit-api-' + $Port + '" dir=in action=allow protocol=TCP localport=' + $Port) -ForegroundColor DarkYellow
        } else {
            Write-Host ' (没取到局域网 IP,真机调试请手动用 ipconfig 查)' -ForegroundColor DarkYellow
        }
    }
    Write-Host '==================================================' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host '启动失败,日志尾部:' -ForegroundColor Red
    if (Test-Path $logFile) { Get-Content $logFile -Tail 25 }
    if (Test-Path ($logFile + '.err')) { Get-Content ($logFile + '.err') -Tail 25 }
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch { }
    exit 1
}
