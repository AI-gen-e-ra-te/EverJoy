# DigiPeople Core 启动脚本 (Windows PowerShell)
# 启动 Fay、后端服务和前端界面

param(
    [switch]$Help,
    [switch]$Fay,
    [switch]$Backend,
    [switch]$Monitor,
    [switch]$All
)

# 颜色定义
$ESC = [char]27
$RED = "$ESC[91m"
$GREEN = "$ESC[92m"
$YELLOW = "$ESC[93m"
$BLUE = "$ESC[94m"
$NC = "$ESC[0m"

# 日志函数
function Write-Info {
    param([string]$Message)
    Write-Host "${BLUE}[INFO]${NC} $Message"
}

function Write-Success {
    param([string]$Message)
    Write-Host "${GREEN}[SUCCESS]${NC} $Message"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "${YELLOW}[WARNING]${NC} $Message"
}

function Write-Error {
    param([string]$Message)
    Write-Host "${RED}[ERROR]${NC} $Message"
}

# 显示帮助
function Show-Help {
    Write-Host "DigiPeople Core 启动脚本 (Windows PowerShell)"
    Write-Host "用法: .\start_all.ps1 [选项]"
    Write-Host ""
    Write-Host "选项:"
    Write-Host "  -Help, -h      显示此帮助信息"
    Write-Host "  -Fay, -f       启动 Fay 服务"
    Write-Host "  -Backend, -b   启动后端服务"
    Write-Host "  -Monitor, -m   监控模式，保持运行并显示日志"
    Write-Host "  -All, -a       启动所有服务（默认）"
    Write-Host ""
}

# 如果请求帮助，显示帮助信息
if ($Help) {
    Show-Help
    exit 0
}

# 解析参数
$START_FAY = $true
$START_BACKEND = $true
$MONITOR_MODE = $false

if ($Fay) {
    $START_BACKEND = $false
}

if ($Backend) {
    $START_FAY = $false
}

if ($Monitor) {
    $MONITOR_MODE = $true
}

# 项目根目录
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
Write-Info "项目根目录: $PROJECT_ROOT"

# 检查环境
Write-Info "检查环境依赖..."

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 未安装，请先安装 Python 3.10+"
    exit 1
}

# 加载环境变量
$ENV_FILE = Join-Path $PROJECT_ROOT ".env"
if (Test-Path $ENV_FILE) {
    Write-Info "加载环境变量..."
    Get-Content $ENV_FILE | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
} else {
    Write-Warning ".env 文件不存在，使用默认配置"
}

# 进程 ID 文件
$FAY_PID_FILE = Join-Path $PROJECT_ROOT ".fay.pid"
$BACKEND_PID_FILE = Join-Path $PROJECT_ROOT ".backend.pid"

# 启动函数
function Start-FayService {
    Write-Info "启动 Fay 服务..."

    $FAY_DIR = Join-Path $PROJECT_ROOT "Fay"
    if (-not (Test-Path $FAY_DIR)) {
        Write-Error "Fay 目录不存在: $FAY_DIR"
        return $false
    }

    Set-Location $FAY_DIR

    # 检查 config_center 文件
    $CONFIG_FILE = Join-Path $FAY_DIR "config\config_center\d19f7b0a-2b8a-4503-8c0d-1a587b90eb69.json"
    if (-not (Test-Path $CONFIG_FILE)) {
        Write-Warning "未找到默认配置中心文件，使用默认启动参数"
    }

    # 启动 Fay
    $fayProcess = Start-Process python -ArgumentList "main.py start -config_center d19f7b0a-2b8a-4503-8c0d-1a587b90eb69" `
        -NoNewWindow -PassThru

    $fayProcess.Id | Out-File -FilePath $FAY_PID_FILE -Encoding ASCII
    Write-Success "Fay 服务已启动 (PID: $($fayProcess.Id))"

    # 等待 Fay 启动完成
    Write-Info "等待 Fay WebSocket 服务就绪..."
    Start-Sleep -Seconds 5

    # 检查端口
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $tcpClient.Connect("127.0.0.1", 10002)
        $tcpClient.Close()
        Write-Success "Fay WebSocket 服务已就绪 (端口: 10002)"
    } catch {
        Write-Warning "Fay WebSocket 服务可能未启动，请检查日志"
    }

    return $true
}

function Start-BackendService {
    Write-Info "启动后端服务..."

    $BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"
    if (-not (Test-Path $BACKEND_DIR)) {
        Write-Error "后端目录不存在: $BACKEND_DIR"
        return $false
    }

    Set-Location $BACKEND_DIR

    # 检查虚拟环境
    $VENV_DIR = Join-Path $BACKEND_DIR "venv"
    if (Test-Path $VENV_DIR) {
        Write-Info "激活 Python 虚拟环境..."
        $VENV_ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
        if (Test-Path $VENV_ACTIVATE) {
            . $VENV_ACTIVATE
        }
    }

    # 安装依赖
    $REQUIREMENTS_FILE = Join-Path $BACKEND_DIR "requirements.txt"
    if (Test-Path $REQUIREMENTS_FILE) {
        Write-Info "检查 Python 依赖..."
        pip install -r requirements.txt --quiet
    }

    # 创建必要目录
    $DIRS = @("uploads", "avatars", "audio", "videos", "logs")
    foreach ($dir in $DIRS) {
        $fullPath = Join-Path $PROJECT_ROOT "data\$dir"
        if (-not (Test-Path $fullPath)) {
            New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
        }
    }

    # 设置 Python 路径
    $env:PYTHONPATH = "$BACKEND_DIR;$env:PYTHONPATH"

    # 获取端口配置
    $PORT = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
    $HOST = if ($env:BACKEND_HOST) { $env:BACKEND_HOST } else { "0.0.0.0" }

    # 检查 uvicorn
    if (Get-Command uvicorn -ErrorAction SilentlyContinue) {
        Write-Info "使用 uvicorn 启动后端服务..."
        $backendProcess = Start-Process uvicorn -ArgumentList "app.main:app --host $HOST --port $PORT --reload" `
            -NoNewWindow -PassThru
    } else {
        Write-Info "使用 python 启动后端服务..."
        $backendProcess = Start-Process python -ArgumentList "-m app.main" `
            -NoNewWindow -PassThru
    }

    $backendProcess.Id | Out-File -FilePath $BACKEND_PID_FILE -Encoding ASCII
    Write-Success "后端服务已启动 (PID: $($backendProcess.Id))"

    # 等待后端启动完成
    Write-Info "等待后端服务就绪..."
    Start-Sleep -Seconds 3

    # 检查健康接口
    try {
        $healthResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$PORT/api/health/" -UseBasicParsing
        if ($healthResponse.Content -match "healthy") {
            Write-Success "后端服务已就绪 (端口: $PORT)"
        } else {
            Write-Warning "后端服务可能未完全启动，请检查日志"
        }
    } catch {
        Write-Warning "后端服务健康检查失败，请稍后重试"
    }

    return $true
}

# 清理函数
function Cleanup {
    Write-Info "清理进程..."

    # 停止 Fay 服务
    if (Test-Path $FAY_PID_FILE) {
        $fayPid = Get-Content $FAY_PID_FILE
        try {
            $fayProcess = Get-Process -Id $fayPid -ErrorAction SilentlyContinue
            if ($fayProcess) {
                Write-Info "停止 Fay 服务 (PID: $fayPid)..."
                Stop-Process -Id $fayPid -Force
            }
        } catch {
            # 进程可能已经结束
        }
        Remove-Item $FAY_PID_FILE -Force -ErrorAction SilentlyContinue
    }

    # 停止后端服务
    if (Test-Path $BACKEND_PID_FILE) {
        $backendPid = Get-Content $BACKEND_PID_FILE
        try {
            $backendProcess = Get-Process -Id $backendPid -ErrorAction SilentlyContinue
            if ($backendProcess) {
                Write-Info "停止后端服务 (PID: $backendPid)..."
                Stop-Process -Id $backendPid -Force
            }
        } catch {
            # 进程可能已经结束
        }
        Remove-Item $BACKEND_PID_FILE -Force -ErrorAction SilentlyContinue
    }
}

# 注册清理函数
trap {
    Cleanup
    break
}

# 主启动逻辑
if ($START_FAY) {
    Start-FayService
}

if ($START_BACKEND) {
    Start-BackendService
}

# 显示服务状态
Write-Host ""
Write-Success "========================================"
Write-Success "DigiPeople Core 启动完成！"
Write-Success "========================================"
Write-Host ""
Write-Host "服务状态:"
Write-Host "  Fay WebSocket:      ws://127.0.0.1:10002"
$PORT = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
Write-Host "  后端API:           http://127.0.0.1:$PORT"
Write-Host "  前端界面:          http://127.0.0.1:$PORT"
Write-Host ""
Write-Host "健康检查:"
Write-Host "  curl http://127.0.0.1:$PORT/api/health/"
Write-Host ""
Write-Host "监控日志:"
Write-Host "  Get-Content backend\logs\app.log -Tail 10 -Wait"
Write-Host ""

# 监控模式
if ($MONITOR_MODE) {
    Write-Info "进入监控模式，按 Ctrl+C 停止所有服务..."
    Write-Host ""

    # 显示进程信息
    if (Test-Path $FAY_PID_FILE) {
        $fayPid = Get-Content $FAY_PID_FILE
        Write-Host "Fay 服务 PID: $fayPid"
    }

    if (Test-Path $BACKEND_PID_FILE) {
        $backendPid = Get-Content $BACKEND_PID_FILE
        Write-Host "后端服务 PID: $backendPid"
    }

    Write-Host ""
    Write-Info "监控日志输出..."
    Write-Host ""

    # 等待用户中断
    Write-Host "按 Ctrl+C 停止所有服务..."
    try {
        while ($true) {
            Start-Sleep -Seconds 1
        }
    } catch {
        # 用户中断
    }
} else {
    Write-Info "服务已在后台运行"
    Write-Host ""
    Write-Host "要停止服务，请运行:"
    Write-Host "  Get-Process | Where-Object { `$_.ProcessName -eq 'python' -and `$_.CommandLine -match 'main.py start' } | Stop-Process"
    Write-Host "  Get-Process | Where-Object { `$_.ProcessName -match 'uvicorn|python' -and `$_.CommandLine -match 'app.main' } | Stop-Process"
    Write-Host ""
    Write-Host "或使用监控模式重新启动: .\start_all.ps1 -Monitor"
}

# 执行清理
Cleanup