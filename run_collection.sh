#!/bin/bash
"""
BTC-USDT 무기한 선물 실시간 캔들 데이터 수집 통합 실행 스크립트
모든 서비스를 시작하고 자동으로 데이터 수집을 시작합니다.
"""

set -e  # 에러 발생시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수들
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 설정 변수
PYTHON_VENV="./venv/bin/python"
DOCKER_COMPOSE_FILE="docker-compose.local.yml"
GATEWAY_HOST="localhost"
GATEWAY_PORT="8000"
SERVICES_READY_TIMEOUT=60  # 서비스 준비 대기 시간 (초)

# 도움말 표시 함수
show_help() {
    cat << EOF
BTC-USDT Perpetual Futures Data Collection Runner

Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    -s, --start-only        Only start services, don't auto-subscribe
    -m, --monitor           Start monitoring after setup
    -v, --validate          Run data validation after setup
    --skip-docker          Skip Docker containers (assume already running)
    --gateway-port PORT    Gateway service port (default: 8000)

Examples:
    $0                     # Start everything with auto-subscription
    $0 --monitor           # Start and monitor
    $0 --validate          # Start and validate data
    $0 --start-only        # Only start services

EOF
}

# 파라미터 파싱
START_ONLY=false
RUN_MONITOR=false
RUN_VALIDATE=false
SKIP_DOCKER=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--start-only)
            START_ONLY=true
            shift
            ;;
        -m|--monitor)
            RUN_MONITOR=true
            shift
            ;;
        -v|--validate)
            RUN_VALIDATE=true
            shift
            ;;
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --gateway-port)
            GATEWAY_PORT="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# 필수 파일 존재 확인
check_prerequisites() {
    log_step "Checking prerequisites..."
    
    # Python 가상환경 확인
    if [ ! -f "$PYTHON_VENV" ]; then
        log_error "Python virtual environment not found at $PYTHON_VENV"
        log_error "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    
    # Docker Compose 파일 확인
    if [ ! -f "$DOCKER_COMPOSE_FILE" ] && [ "$SKIP_DOCKER" = false ]; then
        log_error "Docker Compose file not found: $DOCKER_COMPOSE_FILE"
        exit 1
    fi
    
    # 환경 변수 파일 확인
    if [ ! -f ".env" ]; then
        if [ -f ".env.local" ]; then
            log_warn ".env not found, copying from .env.local"
            cp .env.local .env
        else
            log_error "Environment file (.env) not found"
            exit 1
        fi
    fi
    
    # 스크립트 파일들 확인
    for script in "start_collection.py" "monitor_collection.py" "validate_data.py"; do
        if [ ! -f "$script" ]; then
            log_error "Required script not found: $script"
            exit 1
        fi
    done
    
    log_info "Prerequisites check completed ✓"
}

# Docker 컨테이너 시작
start_docker_services() {
    if [ "$SKIP_DOCKER" = true ]; then
        log_info "Skipping Docker containers (--skip-docker flag)"
        return 0
    fi
    
    log_step "Starting Docker services (PostgreSQL, Redis)..."
    
    # 기존 컨테이너 정리
    docker-compose -f $DOCKER_COMPOSE_FILE down > /dev/null 2>&1 || true
    
    # 컨테이너 시작
    if ! docker-compose -f $DOCKER_COMPOSE_FILE up -d; then
        log_error "Failed to start Docker services"
        exit 1
    fi
    
    # 서비스 헬스체크 대기
    log_info "Waiting for Docker services to be healthy..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        local postgres_health=$(docker inspect --format='{{.State.Health.Status}}' ai-trading-bot-postgres 2>/dev/null || echo "unknown")
        local redis_health=$(docker inspect --format='{{.State.Health.Status}}' ai-trading-bot-redis 2>/dev/null || echo "unknown")
        
        if [ "$postgres_health" = "healthy" ] && [ "$redis_health" = "healthy" ]; then
            log_info "Docker services are healthy ✓"
            return 0
        fi
        
        log_info "Docker services status: PostgreSQL=$postgres_health, Redis=$redis_health (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    log_error "Docker services did not become healthy within expected time"
    docker-compose -f $DOCKER_COMPOSE_FILE logs --tail=20
    exit 1
}

# Python 서비스들 시작
start_python_services() {
    log_step "Starting Python services..."
    
    # 환경 변수 설정
    export REDIS_PASSWORD=redis_password
    export DB_PASSWORD=trading_bot_password
    export DB_NAME=trading_bot
    export DB_USER=trading_bot
    
    # Gateway 서비스 시작 (백그라운드)
    log_info "Starting Gateway service..."
    cd services/gateway
    nohup $PYTHON_VENV main.py > ../../logs/gateway.log 2>&1 &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > ../../logs/gateway.pid
    cd ../..
    
    # Collector 서비스 시작 (백그라운드)  
    log_info "Starting Collector service..."
    cd services/collector
    nohup $PYTHON_VENV main.py > ../../logs/collector.log 2>&1 &
    COLLECTOR_PID=$!
    echo $COLLECTOR_PID > ../../logs/collector.pid
    cd ../..
    
    # Processor 서비스 시작 (백그라운드)
    log_info "Starting Processor service..."
    cd services/processor
    nohup $PYTHON_VENV main.py > ../../logs/processor.log 2>&1 &
    PROCESSOR_PID=$!
    echo $PROCESSOR_PID > ../../logs/processor.pid
    cd ../..
    
    log_info "All Python services started ✓"
    log_info "Service PIDs: Gateway=$GATEWAY_PID, Collector=$COLLECTOR_PID, Processor=$PROCESSOR_PID"
}

# 서비스 준비 상태 확인
wait_for_services() {
    log_step "Waiting for services to be ready..."
    
    local max_attempts=$((SERVICES_READY_TIMEOUT / 2))
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        # Gateway 헬스체크
        if curl -s -f "http://$GATEWAY_HOST:$GATEWAY_PORT/health" > /dev/null 2>&1; then
            log_info "All services are ready ✓"
            return 0
        fi
        
        log_info "Waiting for services... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    log_error "Services did not become ready within $SERVICES_READY_TIMEOUT seconds"
    log_error "Check service logs in the logs/ directory"
    exit 1
}

# 자동 구독 시작
start_auto_subscription() {
    if [ "$START_ONLY" = true ]; then
        log_info "Skipping auto-subscription (--start-only flag)"
        return 0
    fi
    
    log_step "Starting automatic data collection subscription..."
    
    if $PYTHON_VENV start_collection.py --gateway-port $GATEWAY_PORT; then
        log_info "Auto-subscription completed successfully ✓"
    else
        log_error "Failed to start auto-subscription"
        log_error "You can manually start it later with: python start_collection.py"
        return 1
    fi
}

# 모니터링 시작
start_monitoring() {
    if [ "$RUN_MONITOR" = false ]; then
        return 0
    fi
    
    log_step "Starting real-time monitoring..."
    log_info "Monitoring will run in the foreground. Press Ctrl+C to stop."
    sleep 2
    
    $PYTHON_VENV monitor_collection.py --gateway-port $GATEWAY_PORT
}

# 데이터 검증 실행
run_validation() {
    if [ "$RUN_VALIDATE" = false ]; then
        return 0
    fi
    
    log_step "Running data validation..."
    sleep 5  # 데이터 수집이 시작되도록 잠시 대기
    
    $PYTHON_VENV validate_data.py
}

# 로그 디렉토리 생성
create_log_directory() {
    mkdir -p logs
}

# 종료 시 정리 작업
cleanup() {
    log_info "Cleaning up..."
    
    # Python 서비스 중지
    if [ -f "logs/gateway.pid" ]; then
        kill $(cat logs/gateway.pid) 2>/dev/null || true
        rm logs/gateway.pid
    fi
    
    if [ -f "logs/collector.pid" ]; then
        kill $(cat logs/collector.pid) 2>/dev/null || true
        rm logs/collector.pid
    fi
    
    if [ -f "logs/processor.pid" ]; then
        kill $(cat logs/processor.pid) 2>/dev/null || true
        rm logs/processor.pid
    fi
}

# 신호 핸들러 등록
trap cleanup EXIT INT TERM

# 메인 실행 흐름
main() {
    echo ""
    log_info "🚀 Starting BTC-USDT Perpetual Futures Data Collection System"
    echo ""
    
    # 1. 사전 조건 확인
    check_prerequisites
    
    # 2. 로그 디렉토리 생성
    create_log_directory
    
    # 3. Docker 서비스 시작
    start_docker_services
    
    # 4. Python 서비스 시작
    start_python_services
    
    # 5. 서비스 준비 대기
    wait_for_services
    
    # 6. 자동 구독 시작
    start_auto_subscription
    
    echo ""
    log_info "🎉 System is now running!"
    log_info "📊 BTC-USDT-SWAP data collection active for timeframes: 5m, 15m, 1h, 4h, 1d"
    log_info "🌐 Gateway API: http://$GATEWAY_HOST:$GATEWAY_PORT"
    log_info "📋 Active subscriptions: http://$GATEWAY_HOST:$GATEWAY_PORT/api/v1/subscriptions"
    echo ""
    log_info "📁 Service logs are available in the logs/ directory:"
    log_info "   - logs/gateway.log"
    log_info "   - logs/collector.log" 
    log_info "   - logs/processor.log"
    echo ""
    
    # 7. 추가 작업 (모니터링 또는 검증)
    run_validation
    start_monitoring
    
    # 모니터링이 실행되지 않은 경우 사용자 안내
    if [ "$RUN_MONITOR" = false ]; then
        log_info "💡 To monitor the system in real-time, run:"
        log_info "   python monitor_collection.py"
        echo ""
        log_info "💡 To validate data quality, run:"
        log_info "   python validate_data.py"
        echo ""
        log_info "⚠️  To stop all services, press Ctrl+C or run:"
        log_info "   docker-compose -f $DOCKER_COMPOSE_FILE down"
        echo ""
        
        # 백그라운드에서 실행 중이므로 무한 대기
        log_info "🔄 Services are running in the background. Press Ctrl+C to stop."
        while true; do
            sleep 1
        done
    fi
}

# 스크립트 실행
main "$@"