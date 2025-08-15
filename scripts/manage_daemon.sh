#!/bin/bash

# AI Trading Bot Daemon Management Script
# 통합 관리 스크립트

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}🤖 AI Trading Bot Daemon Management${NC}"
    echo -e "${BLUE}   BTC-USDT-SWAP Perpetual Futures Collection${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
}

print_usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|install|uninstall|test|validate|fill-gaps|dedupe}"
    echo ""
    echo "Commands:"
    echo -e "  ${GREEN}start${NC}     - Start all daemon services"
    echo -e "  ${RED}stop${NC}      - Stop all daemon services"
    echo -e "  ${YELLOW}restart${NC}   - Restart all daemon services"
    echo -e "  ${BLUE}status${NC}    - Show service status and data collection stats"
    echo -e "  ${BLUE}logs${NC}      - Show recent logs from all services"
    echo -e "  ${GREEN}install${NC}   - Install as system service (auto-start)"
    echo -e "  ${RED}uninstall${NC} - Remove system service"
    echo -e "  ${YELLOW}test${NC}      - Test data collection and system health"
    echo -e "  ${BLUE}validate${NC}  - Validate data integrity and completeness"
    echo -e "  ${YELLOW}fill-gaps${NC} - Detect and fill missing data gaps"
    echo -e "  ${RED}dedupe${NC}    - Remove duplicate data records"
    echo ""
}

start_daemon() {
    echo -e "${GREEN}🚀 Starting AI Trading Bot Daemon...${NC}"
    "$SCRIPT_DIR/start_daemon.sh"
}

stop_daemon() {
    echo -e "${RED}🛑 Stopping AI Trading Bot Daemon...${NC}"
    "$SCRIPT_DIR/stop_daemon.sh"
}

restart_daemon() {
    echo -e "${YELLOW}🔄 Restarting AI Trading Bot Daemon...${NC}"
    stop_daemon
    sleep 2
    start_daemon
}

show_status() {
    "$SCRIPT_DIR/status_daemon.sh"
}

show_logs() {
    echo -e "${BLUE}📋 Recent Logs (Press Ctrl+C to exit)${NC}"
    echo ""
    
    LOG_DIR="$PROJECT_DIR/logs"
    
    if [ -d "$LOG_DIR" ]; then
        echo "Gateway logs:"
        echo "-------------"
        tail -n 20 "$LOG_DIR/gateway.log" 2>/dev/null || echo "No gateway logs"
        echo ""
        
        echo "Collector logs:"
        echo "---------------"
        tail -n 20 "$LOG_DIR/collector.log" 2>/dev/null || echo "No collector logs"
        echo ""
        
        echo "Processor logs:"
        echo "---------------"
        tail -n 20 "$LOG_DIR/processor.log" 2>/dev/null || echo "No processor logs"
        echo ""
        
        echo -e "${YELLOW}💡 For live monitoring, use:${NC}"
        echo "   tail -f $LOG_DIR/{gateway,collector,processor}.log"
    else
        echo "No log directory found"
    fi
}

install_service() {
    echo -e "${GREEN}📦 Installing AI Trading Bot as system service...${NC}"
    "$SCRIPT_DIR/install_service.sh"
}

uninstall_service() {
    echo -e "${RED}🗑️  Uninstalling AI Trading Bot system service...${NC}"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        PLIST_FILE="$HOME/Library/LaunchAgents/com.ai-trading-bot.plist"
        if [ -f "$PLIST_FILE" ]; then
            launchctl unload "$PLIST_FILE" 2>/dev/null || true
            rm "$PLIST_FILE"
            echo "✅ Removed launchd service"
        else
            echo "⚠️  Service not found"
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if systemctl is-enabled ai-trading-bot >/dev/null 2>&1; then
            sudo systemctl stop ai-trading-bot 2>/dev/null || true
            sudo systemctl disable ai-trading-bot
            sudo rm -f /etc/systemd/system/ai-trading-bot.service
            sudo systemctl daemon-reload
            echo "✅ Removed systemd service"
        else
            echo "⚠️  Service not found"
        fi
    fi
}

test_system() {
    echo -e "${YELLOW}🧪 Testing AI Trading Bot System...${NC}"
    echo ""
    
    # 의존성 확인
    echo "1. Checking dependencies..."
    
    if nc -z localhost 5432 2>/dev/null; then
        echo -e "   ✅ PostgreSQL: ${GREEN}RUNNING${NC}"
    else
        echo -e "   ❌ PostgreSQL: ${RED}NOT RUNNING${NC}"
        return 1
    fi
    
    if nc -z localhost 6379 2>/dev/null; then
        echo -e "   ✅ Redis: ${GREEN}RUNNING${NC}"
    else
        echo -e "   ❌ Redis: ${RED}NOT RUNNING${NC}"
        return 1
    fi
    
    # 가상환경 확인
    echo "2. Checking Python environment..."
    if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
        echo -e "   ✅ Virtual environment: ${GREEN}FOUND${NC}"
    else
        echo -e "   ❌ Virtual environment: ${RED}NOT FOUND${NC}"
        return 1
    fi
    
    # 서비스 확인
    echo "3. Checking services..."
    show_status
    
    echo ""
    echo -e "${GREEN}🎉 System test completed!${NC}"
}

validate_data() {
    echo -e "${BLUE}🔍 Validating Data Integrity...${NC}"
    source "$PROJECT_DIR/venv/bin/activate"
    python "$PROJECT_DIR/scripts/validate_data.py" --hours 24
}

fill_gaps() {
    echo -e "${YELLOW}📥 Filling Data Gaps...${NC}"
    source "$PROJECT_DIR/venv/bin/activate"
    python "$PROJECT_DIR/scripts/fill_gaps.py" --hours 24
}

deduplicate_data() {
    echo -e "${RED}🗑️  Removing Duplicate Data...${NC}"
    source "$PROJECT_DIR/venv/bin/activate"
    python "$PROJECT_DIR/scripts/deduplicate_data.py"
}

# 메인 실행 부분
print_header

case "${1:-}" in
    start)
        start_daemon
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        restart_daemon
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    test)
        test_system
        ;;
    validate)
        validate_data
        ;;
    fill-gaps)
        fill_gaps
        ;;
    dedupe)
        deduplicate_data
        ;;
    *)
        print_usage
        exit 1
        ;;
esac

echo ""