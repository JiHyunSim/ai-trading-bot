#!/bin/bash

# AI Trading Bot Daemon Status Check Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/pids"
LOG_DIR="$PROJECT_DIR/logs"

echo "📊 AI Trading Bot Daemon Status"
echo "================================"

# 서비스 상태 확인 함수
check_service() {
    local service_name="$1"
    local port="$2"
    
    printf "%-12s" "$service_name:"
    
    if [ -f "$PID_DIR/${service_name}.pid" ]; then
        local pid=$(cat "$PID_DIR/${service_name}.pid")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "🟢 RUNNING (PID: $pid)"
            
            # 포트 체크
            if [ -n "$port" ] && nc -z localhost "$port" 2>/dev/null; then
                echo "             Port $port: LISTENING"
            fi
            
            # 최근 로그 확인
            if [ -f "$LOG_DIR/${service_name}.log" ]; then
                local log_size=$(wc -l < "$LOG_DIR/${service_name}.log" 2>/dev/null || echo 0)
                echo "             Log entries: $log_size lines"
            fi
        else
            echo "🔴 STOPPED (PID file exists but process not running)"
            rm -f "$PID_DIR/${service_name}.pid"
        fi
    else
        echo "⚪ STOPPED (no PID file)"
    fi
}

# 각 서비스 상태 확인
check_service "gateway" "8001"
check_service "collector" ""
check_service "processor" ""

echo ""
echo "🔗 Dependencies:"
printf "%-12s" "PostgreSQL:"
if nc -z localhost 5432 2>/dev/null; then
    echo "🟢 RUNNING"
else
    echo "🔴 NOT RUNNING"
fi

printf "%-12s" "Redis:"
if nc -z localhost 6379 2>/dev/null; then
    echo "🟢 RUNNING"
else
    echo "🔴 NOT RUNNING"
fi

echo ""

# 데이터베이스 상태 확인
if nc -z localhost 5432 2>/dev/null; then
    echo "📈 Data Collection Status:"
    
    cd "$PROJECT_DIR"
    source venv/bin/activate 2>/dev/null || true
    
    python3 -c "
import asyncio
import asyncpg
import redis.asyncio as redis
from datetime import datetime, timedelta

async def check_status():
    try:
        # PostgreSQL 연결
        conn = await asyncpg.connect(
            host='localhost',
            port=5432, 
            database='trading_bot',
            user='trading_bot',
            password='trading_bot_password'
        )
        
        # 최근 데이터 확인
        recent = await conn.fetchval(\"\"\"
            SELECT COUNT(*) FROM trading.candlesticks 
            WHERE created_at >= NOW() - INTERVAL '5 minutes'
        \"\"\")
        
        total = await conn.fetchval('SELECT COUNT(*) FROM trading.candlesticks')
        
        print(f'  📊 Total records: {total:,}')
        print(f'  🔄 Recent activity (5min): {recent} records')
        
        # 타임프레임별 최신 데이터
        latest = await conn.fetch(\"\"\"
            SELECT timeframe, MAX(created_at) as latest 
            FROM trading.candlesticks 
            WHERE symbol = 'BTC-USDT-SWAP'
            GROUP BY timeframe 
            ORDER BY timeframe
        \"\"\")
        
        print('  📈 Latest data by timeframe:')
        for row in latest:
            ago = datetime.now().replace(tzinfo=row['latest'].tzinfo) - row['latest']
            minutes_ago = int(ago.total_seconds() / 60)
            print(f'     {row[\"timeframe\"]:>4}: {minutes_ago}m ago')
        
        await conn.close()
        
        # Redis 큐 상태
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            password='redis_password',
            decode_responses=True
        )
        
        queue_len = await redis_client.llen('candle_data_queue')
        dlq_len = await redis_client.llen('dead_letter_queue')
        
        print(f'  📦 Queue length: {queue_len}')
        print(f'  ⚠️  DLQ length: {dlq_len}')
        
        await redis_client.aclose()
        
    except Exception as e:
        print(f'  ❌ Error checking status: {e}')

asyncio.run(check_status())
" 2>/dev/null || echo "  ❌ Unable to check database status"
fi

echo ""
echo "🔧 Quick Commands:"
echo "  Start:  $SCRIPT_DIR/start_daemon.sh"
echo "  Stop:   $SCRIPT_DIR/stop_daemon.sh"
echo "  Logs:   tail -f $LOG_DIR/{gateway,collector,processor}.log"
echo ""