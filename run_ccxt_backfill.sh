#!/bin/bash
#
# CCXT Historical Data Backfill 실행 래퍼 스크립트
# 가상환경을 자동으로 활성화하여 CCXT 백필 스크립트 실행
#

# 스크립트 위치 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# 가상환경 경로
VENV_PATH="$PROJECT_ROOT/venv"

# 가상환경 존재 확인
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at: $VENV_PATH"
    echo "🔧 Please create virtual environment first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# 가상환경 활성화
echo "🔧 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Python 및 필요 모듈 확인
if ! python -c "import asyncpg, ccxt, structlog" 2>/dev/null; then
    echo "❌ Required modules not found. Installing dependencies..."
    pip install asyncpg ccxt structlog python-dotenv
fi

# CCXT 백필 스크립트 실행
echo "🚀 Starting CCXT historical data backfill..."
echo "📍 Working directory: $PROJECT_ROOT"
echo ""

cd "$PROJECT_ROOT"

# 인자가 없으면 도움말 출력
if [ $# -eq 0 ]; then
    echo "📖 CCXT Historical Data Backfill Script"
    echo ""
    echo "사용법:"
    echo "  $0 <SYMBOL> [OPTIONS]"
    echo ""
    echo "예시:"
    echo "  $0 BTC/USDT:USDT                     # 30일 백필"
    echo "  $0 BTC/USDT:USDT --days 60           # 60일 백필"  
    echo "  $0 BTC/USDT:USDT --dry-run           # 시뮬레이션"
    echo "  $0 BTC/USDT:USDT --timeframes 1h,1d  # 특정 타임프레임만"
    echo "  $0 BTC/USDT:USDT --exchange binance  # 다른 거래소"
    echo ""
    python scripts/ccxt_historical_backfill.py --help
    exit 0
fi

# CCXT 백필 스크립트 실행
python scripts/ccxt_historical_backfill.py "$@"
exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✅ CCXT Backfill completed successfully!"
else
    echo "❌ CCXT Backfill failed with exit code: $exit_code"
fi

exit $exit_code