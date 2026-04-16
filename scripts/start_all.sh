#!/bin/bash

# DigiPeople Core 启动脚本 (Linux/Mac)
# 启动 Fay、后端服务和前端界面

set -e  # 出错时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "命令 '$1' 不存在，请先安装"
        exit 1
    fi
}

# 显示帮助
show_help() {
    echo "DigiPeople Core 启动脚本"
    echo "用法: ./start_all.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help     显示此帮助信息"
    echo "  -f, --fay      启动 Fay 服务"
    echo "  -b, --backend  启动后端服务"
    echo "  -m, --monitor  监控模式，保持运行并显示日志"
    echo "  -a, --all      启动所有服务（默认）"
    echo ""
}

# 解析参数
START_FAY=true
START_BACKEND=true
MONITOR_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--fay)
            START_BACKEND=false
            shift
            ;;
        -b|--backend)
            START_FAY=false
            shift
            ;;
        -m|--monitor)
            MONITOR_MODE=true
            shift
            ;;
        -a|--all)
            # 默认就是全部启动
            shift
            ;;
        *)
            log_error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_info "项目根目录: $PROJECT_ROOT"

# 检查环境
log_info "检查环境依赖..."
check_command "python3"
check_command "pip3"

# 加载环境变量
if [ -f "$PROJECT_ROOT/.env" ]; then
    log_info "加载环境变量..."
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
else
    log_warning ".env 文件不存在，使用默认配置"
fi

# 启动函数
start_fay() {
    log_info "启动 Fay 服务..."

    if [ ! -d "$PROJECT_ROOT/Fay" ]; then
        log_error "Fay 目录不存在: $PROJECT_ROOT/Fay"
        return 1
    fi

    cd "$PROJECT_ROOT/Fay"

    # 检查 config_center 文件
    if [ ! -f "./config/config_center/d19f7b0a-2b8a-4503-8c0d-1a587b90eb69.json" ]; then
        log_warning "未找到默认配置中心文件，使用默认启动参数"
        python main.py start -config_center d19f7b0a-2b8a-4503-8c0d-1a587b90eb69 &
    else
        python main.py start -config_center d19f7b0a-2b8a-4503-8c0d-1a587b90eb69 &
    fi

    FAY_PID=$!
    echo $FAY_PID > "$PROJECT_ROOT/.fay.pid"
    log_success "Fay 服务已启动 (PID: $FAY_PID)"

    # 等待 Fay 启动完成
    log_info "等待 Fay WebSocket 服务就绪..."
    sleep 5

    # 检查端口
    if nc -z 127.0.0.1 10002; then
        log_success "Fay WebSocket 服务已就绪 (端口: 10002)"
    else
        log_warning "Fay WebSocket 服务可能未启动，请检查日志"
    fi

    return 0
}

start_backend() {
    log_info "启动后端服务..."

    if [ ! -d "$PROJECT_ROOT/backend" ]; then
        log_error "后端目录不存在: $PROJECT_ROOT/backend"
        return 1
    fi

    cd "$PROJECT_ROOT/backend"

    # 检查虚拟环境
    if [ -d "venv" ]; then
        log_info "激活 Python 虚拟环境..."
        source venv/bin/activate
    fi

    # 安装依赖
    if [ -f "requirements.txt" ]; then
        log_info "检查 Python 依赖..."
        pip3 install -r requirements.txt --quiet
    fi

    # 创建必要目录
    mkdir -p "$PROJECT_ROOT/data/uploads"
    mkdir -p "$PROJECT_ROOT/data/avatars"
    mkdir -p "$PROJECT_ROOT/data/audio"
    mkdir -p "$PROJECT_ROOT/data/videos"
    mkdir -p "$PROJECT_ROOT/data/logs"

    # 启动 FastAPI 服务
    export PYTHONPATH="$PROJECT_ROOT/backend:$PYTHONPATH"

    # 使用 uvicorn 启动
    if command -v uvicorn &> /dev/null; then
        log_info "使用 uvicorn 启动后端服务..."
        uvicorn app.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${BACKEND_PORT:-8000}" --reload &
    else
        log_info "使用 python 启动后端服务..."
        python -m app.main &
    fi

    BACKEND_PID=$!
    echo $BACKEND_PID > "$PROJECT_ROOT/.backend.pid"
    log_success "后端服务已启动 (PID: $BACKEND_PID)"

    # 等待后端启动完成
    log_info "等待后端服务就绪..."
    sleep 3

    # 检查健康接口
    if curl -s "http://127.0.0.1:${BACKEND_PORT:-8000}/api/health/" | grep -q "healthy"; then
        log_success "后端服务已就绪 (端口: ${BACKEND_PORT:-8000})"
    else
        log_warning "后端服务可能未完全启动，请检查日志"
    fi

    return 0
}

# 清理函数
cleanup() {
    log_info "清理进程..."

    if [ -f "$PROJECT_ROOT/.fay.pid" ]; then
        FAY_PID=$(cat "$PROJECT_ROOT/.fay.pid")
        if kill -0 $FAY_PID 2>/dev/null; then
            log_info "停止 Fay 服务 (PID: $FAY_PID)..."
            kill $FAY_PID
        fi
        rm -f "$PROJECT_ROOT/.fay.pid"
    fi

    if [ -f "$PROJECT_ROOT/.backend.pid" ]; then
        BACKEND_PID=$(cat "$PROJECT_ROOT/.backend.pid")
        if kill -0 $BACKEND_PID 2>/dev/null; then
            log_info "停止后端服务 (PID: $BACKEND_PID)..."
            kill $BACKEND_PID
        fi
        rm -f "$PROJECT_ROOT/.backend.pid"
    fi
}

# 注册清理函数
trap cleanup EXIT INT TERM

# 主启动逻辑
if [ "$START_FAY" = true ]; then
    start_fay
fi

if [ "$START_BACKEND" = true ]; then
    start_backend
fi

# 显示服务状态
echo ""
log_success "========================================"
log_success "DigiPeople Core 启动完成！"
log_success "========================================"
echo ""
echo "服务状态:"
echo "  Fay WebSocket:      ws://127.0.0.1:10002"
echo "  后端API:           http://127.0.0.1:${BACKEND_PORT:-8000}"
echo "  前端界面:          http://127.0.0.1:${BACKEND_PORT:-8000}"
echo ""
echo "健康检查:"
echo "  curl http://127.0.0.1:${BACKEND_PORT:-8000}/api/health/"
echo ""
echo "监控日志:"
echo "  tail -f backend/logs/app.log"
echo ""

# 监控模式
if [ "$MONITOR_MODE" = true ]; then
    log_info "进入监控模式，按 Ctrl+C 停止所有服务..."
    echo ""

    # 显示进程信息
    if [ -f "$PROJECT_ROOT/.fay.pid" ]; then
        FAY_PID=$(cat "$PROJECT_ROOT/.fay.pid")
        echo "Fay 服务 PID: $FAY_PID"
    fi

    if [ -f "$PROJECT_ROOT/.backend.pid" ]; then
        BACKEND_PID=$(cat "$PROJECT_ROOT/.backend.pid")
        echo "后端服务 PID: $BACKEND_PID"
    fi

    echo ""
    log_info "监控日志输出..."

    # 等待所有子进程
    wait
else
    log_info "服务已在后台运行"
    echo ""
    echo "要停止服务，请运行:"
    echo "  pkill -f \"python main.py\"  # 停止 Fay"
    echo "  pkill -f \"uvicorn\|app.main\"  # 停止后端"
    echo ""
    echo "或使用监控模式重新启动: ./start_all.sh --monitor"
fi