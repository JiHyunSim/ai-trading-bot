#!/bin/bash
#
# Docker를 통한 CCXT 데이터 유지보수 실행 스크립트
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로고 출력
echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════╗"
echo "║        CCXT Docker Maintenance System             ║"
echo "║              AI Trading Bot                       ║"
echo "╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

# 환경 변수 파일 확인
ENV_FILE=".env.docker"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ Environment file $ENV_FILE not found!${NC}"
    echo -e "${YELLOW}Please create $ENV_FILE with your API credentials${NC}"
    exit 1
fi

# Docker 및 Docker Compose 확인
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

# Docker Compose 명령어 결정
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# 사용법 출력 함수
usage() {
    echo -e "${YELLOW}Usage:${NC}"
    echo "  $0 <command> [options]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  build                    - Build Docker images"
    echo "  backfill <symbol> [days] - Run historical data backfill"
    echo "  maintenance              - Run one-time maintenance"
    echo "  start-cron              - Start automatic daily maintenance"
    echo "  stop-cron               - Stop automatic daily maintenance"
    echo "  logs                    - View maintenance logs"
    echo "  status                  - Check service status"
    echo "  clean                   - Clean up containers and images"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 build"
    echo "  $0 backfill BTC/USDT:USDT 30"
    echo "  $0 maintenance"
    echo "  $0 start-cron"
    echo "  $0 logs"
}

# 빌드 함수
build_images() {
    echo -e "${BLUE}🔨 Building Docker images...${NC}"
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml build
    echo -e "${GREEN}✅ Docker images built successfully${NC}"
}

# 백필 함수
run_backfill() {
    local symbol="${1:-BTC/USDT:USDT}"
    local days="${2:-30}"
    
    echo -e "${BLUE}📈 Running historical data backfill...${NC}"
    echo -e "${YELLOW}Symbol: $symbol${NC}"
    echo -e "${YELLOW}Days: $days${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml \
        run --rm ccxt-backfill \
        python scripts/ccxt_historical_backfill.py "$symbol" --days "$days"
    
    echo -e "${GREEN}✅ Backfill completed${NC}"
}

# 유지보수 함수
run_maintenance() {
    echo -e "${BLUE}🔧 Running one-time maintenance...${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml \
        run --rm ccxt-maintenance
    
    echo -e "${GREEN}✅ Maintenance completed${NC}"
}

# 크론 시작 함수
start_cron() {
    echo -e "${BLUE}⏰ Starting automatic daily maintenance...${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml \
        up -d ccxt-cron
    
    echo -e "${GREEN}✅ Automatic maintenance started${NC}"
    echo -e "${YELLOW}💡 Use '$0 logs' to view maintenance logs${NC}"
}

# 크론 중지 함수
stop_cron() {
    echo -e "${BLUE}🛑 Stopping automatic daily maintenance...${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml \
        stop ccxt-cron
    
    echo -e "${GREEN}✅ Automatic maintenance stopped${NC}"
}

# 로그 보기 함수
view_logs() {
    echo -e "${BLUE}📋 Viewing maintenance logs...${NC}"
    
    if $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml ps | grep -q ccxt-cron; then
        $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml \
            logs -f ccxt-cron
    else
        echo -e "${YELLOW}⚠️  Cron service is not running${NC}"
        echo -e "${YELLOW}💡 Use '$0 start-cron' to start automatic maintenance${NC}"
    fi
}

# 상태 확인 함수
check_status() {
    echo -e "${BLUE}📊 Checking service status...${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml ps
    
    if $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml ps | grep -q ccxt-cron; then
        echo -e "${GREEN}✅ Automatic maintenance is running${NC}"
    else
        echo -e "${YELLOW}⚠️  Automatic maintenance is not running${NC}"
    fi
}

# 정리 함수
clean_up() {
    echo -e "${BLUE}🧹 Cleaning up containers and images...${NC}"
    
    $DOCKER_COMPOSE --env-file "$ENV_FILE" -f docker-compose.maintenance.yml down --volumes
    docker system prune -f
    
    echo -e "${GREEN}✅ Cleanup completed${NC}"
}

# 메인 로직
case "${1:-}" in
    build)
        build_images
        ;;
    backfill)
        build_images
        run_backfill "$2" "$3"
        ;;
    maintenance)
        build_images
        run_maintenance
        ;;
    start-cron)
        build_images
        start_cron
        ;;
    stop-cron)
        stop_cron
        ;;
    logs)
        view_logs
        ;;
    status)
        check_status
        ;;
    clean)
        clean_up
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}❌ Unknown command: ${1:-}${NC}"
        echo ""
        usage
        exit 1
        ;;
esac