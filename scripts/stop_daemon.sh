#!/bin/bash

# AI Trading Bot Daemon Stop Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/pids"

echo "🛑 Stopping AI Trading Bot Daemon Services..."

# 서비스 중지 함수
stop_service() {
    local service_name="$1"
    
    if [ -f "$PID_DIR/${service_name}.pid" ]; then
        local pid=$(cat "$PID_DIR/${service_name}.pid")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "  Stopping $service_name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            
            # 프로세스 종료 대기
            local count=0
            while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
                sleep 1
                count=$((count + 1))
            done
            
            # 강제 종료
            if ps -p "$pid" > /dev/null 2>&1; then
                echo "  Force killing $service_name..."
                kill -9 "$pid" 2>/dev/null || true
            fi
            
            echo "  ✅ $service_name stopped"
        else
            echo "  ⚠️  $service_name was not running"
        fi
        rm -f "$PID_DIR/${service_name}.pid"
    else
        echo "  ⚠️  $service_name PID file not found"
    fi
}

# 서비스 중지 (역순)
stop_service "processor"
stop_service "collector"
stop_service "gateway"

echo ""
echo "🏁 All services stopped successfully!"
echo ""