#!/bin/bash

# AI Trading Bot Daemon Startup Script
# BTC-USDT-SWAP 무기한 선물 실시간 데이터 수집 데몬

set -e

# 스크립트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PATH="$PROJECT_DIR/venv"
PID_DIR="$PROJECT_DIR/pids"
LOG_DIR="$PROJECT_DIR/logs"

# 디렉토리 생성
mkdir -p "$PID_DIR" "$LOG_DIR"

# 환경 변수 로드
cd "$PROJECT_DIR"
source .env 2>/dev/null || echo "Warning: .env file not found"

# 가상환경 활성화
source "$VENV_PATH/bin/activate"

echo "🚀 Starting AI Trading Bot Daemon Services..."
echo "Project Directory: $PROJECT_DIR"
echo "Virtual Environment: $VENV_PATH"
echo "PID Directory: $PID_DIR"
echo "Log Directory: $LOG_DIR"
echo ""

# 서비스 시작 함수
start_service() {
    local service_name="$1"
    local service_dir="$2"
    local main_file="$3"
    local port="$4"
    
    echo "📡 Starting $service_name service..."
    
    cd "$PROJECT_DIR/$service_dir"
    
    # 기존 프로세스 확인 및 종료
    if [ -f "$PID_DIR/${service_name}.pid" ]; then
        local old_pid=$(cat "$PID_DIR/${service_name}.pid")
        if ps -p "$old_pid" > /dev/null 2>&1; then
            echo "  Stopping existing $service_name process (PID: $old_pid)"
            kill "$old_pid" 2>/dev/null || true
            sleep 2
        fi
        rm -f "$PID_DIR/${service_name}.pid"
    fi
    
    # 서비스 시작
    if [ "$service_name" = "gateway" ]; then
        nohup uvicorn main:app --host 0.0.0.0 --port "$port" > "$LOG_DIR/${service_name}.log" 2>&1 &
    else
        nohup python "$main_file" > "$LOG_DIR/${service_name}.log" 2>&1 &
    fi
    
    local pid=$!
    echo "$pid" > "$PID_DIR/${service_name}.pid"
    
    # 서비스 시작 확인
    sleep 3
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "  ✅ $service_name started successfully (PID: $pid)"
        if [ -n "$port" ]; then
            echo "     Port: $port"
        fi
    else
        echo "  ❌ Failed to start $service_name"
        rm -f "$PID_DIR/${service_name}.pid"
        return 1
    fi
    
    cd "$PROJECT_DIR"
}

# PostgreSQL 및 Redis 서비스 확인
check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    # PostgreSQL 확인
    if ! nc -z localhost 5432 2>/dev/null; then
        echo "❌ PostgreSQL is not running on port 5432"
        echo "   Please start PostgreSQL: brew services start postgresql"
        exit 1
    else
        echo "✅ PostgreSQL is running"
    fi
    
    # Redis 확인
    if ! nc -z localhost 6379 2>/dev/null; then
        echo "❌ Redis is not running on port 6379"
        echo "   Please start Redis: brew services start redis"
        exit 1
    else
        echo "✅ Redis is running"
    fi
    
    echo ""
}

# 의존성 확인
check_dependencies

# 서비스 시작 순서: Gateway → Collector → Processor
start_service "gateway" "services/gateway" "main.py" "8001"
start_service "collector" "services/collector" "main.py" ""
start_service "processor" "services/processor" "main.py" ""

echo ""
echo "🎉 All services started successfully!"
echo ""
echo "📊 Service Status:"
echo "  Gateway:   http://localhost:8001/health"
echo "  Collector: Real-time BTC-USDT-SWAP data collection"
echo "  Processor: Data processing and PostgreSQL storage"
echo ""
echo "📁 Logs: $LOG_DIR/"
echo "📁 PIDs: $PID_DIR/"
echo ""
echo "🔧 Management Commands:"
echo "  Stop all:    $SCRIPT_DIR/stop_daemon.sh"
echo "  Check status: $SCRIPT_DIR/status_daemon.sh"
echo "  View logs:   tail -f $LOG_DIR/gateway.log"
echo ""
echo "🔄 Data Collection Status:"
echo "  Symbol: BTC-USDT-SWAP (Perpetual Futures)"
echo "  Timeframes: 5m, 15m, 1h, 4h, 1d"
echo "  Mode: Continuous real-time collection"
echo ""