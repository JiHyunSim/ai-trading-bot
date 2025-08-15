# AI Trading Bot Daemon Guide

BTC-USDT-SWAP 무기한 선물 실시간 데이터 수집 데몬 시스템

## 🚀 Quick Start

### 데몬 시작
```bash
./scripts/manage_daemon.sh start
```

### 상태 확인
```bash
./scripts/manage_daemon.sh status
```

### 데몬 중지
```bash
./scripts/manage_daemon.sh stop
```

## 📋 관리 명령어

| 명령어 | 설명 |
|--------|------|
| `start` | 모든 데몬 서비스 시작 |
| `stop` | 모든 데몬 서비스 중지 |
| `restart` | 모든 데몬 서비스 재시작 |
| `status` | 서비스 상태 및 데이터 수집 통계 |
| `logs` | 최근 로그 보기 |
| `install` | 시스템 서비스로 설치 (자동 시작) |
| `uninstall` | 시스템 서비스 제거 |
| `test` | 시스템 상태 테스트 |

## 🔧 시스템 서비스 설치

### 자동 시작 설정
```bash
./scripts/manage_daemon.sh install
```

이 명령어는:
- **macOS**: launchd 서비스로 등록 (시스템 부팅 시 자동 시작)
- **Linux**: systemd 서비스로 등록

### 시스템 서비스 관리 (설치 후)

#### macOS (launchd)
```bash
# 시작
launchctl start com.ai-trading-bot

# 중지  
launchctl stop com.ai-trading-bot

# 상태 확인
launchctl list | grep ai-trading-bot

# 로그 확인
tail -f ~/claude-projects/ai-trading-bot/logs/launchd.{out,err}
```

#### Linux (systemd)
```bash
# 시작
sudo systemctl start ai-trading-bot

# 중지
sudo systemctl stop ai-trading-bot

# 상태 확인
sudo systemctl status ai-trading-bot

# 로그 확인
journalctl -u ai-trading-bot -f
```

## 📊 데이터 수집 정보

### 수집 대상
- **심볼**: BTC-USDT-SWAP (무기한 선물)
- **타임프레임**: 5m, 15m, 1h, 4h, 1d
- **데이터**: 실시간 캔들스틱 데이터

### 저장 위치
- **데이터베이스**: PostgreSQL `trading.candlesticks` 테이블
- **큐**: Redis `candle_data_queue`
- **로그**: `logs/` 디렉토리

## 🔍 모니터링

### 실시간 로그 모니터링
```bash
# 모든 서비스 로그
tail -f logs/{gateway,collector,processor}.log

# 개별 서비스 로그
tail -f logs/gateway.log     # API Gateway
tail -f logs/collector.log   # OKX 데이터 수집
tail -f logs/processor.log   # 데이터 처리
```

### 데이터베이스 확인
```bash
# 최근 데이터 확인
psql -h localhost -U trading_bot -d trading_bot -c "
SELECT symbol, timeframe, COUNT(*) as records, 
       MAX(created_at) as latest_data
FROM trading.candlesticks 
GROUP BY symbol, timeframe 
ORDER BY symbol, timeframe;"
```

## 🛠️ 문제 해결

### 의존성 확인
```bash
# PostgreSQL 상태
brew services list | grep postgresql

# Redis 상태  
brew services list | grep redis

# 포트 확인
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8001  # Gateway
```

### 서비스 재시작
```bash
# 데몬 재시작
./scripts/manage_daemon.sh restart

# 개별 서비스 재시작 (수동)
./scripts/stop_daemon.sh
./scripts/start_daemon.sh
```

### 로그 정리
```bash
# 로그 파일 정리
rm -f logs/*.log

# PID 파일 정리
rm -f pids/*.pid
```

## 📈 성능 지표

시스템이 정상 동작 중일 때:
- **데이터 수집률**: 초당 약 1-5개 레코드
- **큐 길이**: 일반적으로 0-10 (백로그 없음)
- **메모리 사용량**: 서비스당 약 50-100MB
- **CPU 사용량**: 평상시 1-5%

## 🔒 보안 설정

### 파일 권한
```bash
# 스크립트 실행 권한 확인
ls -la scripts/*.sh

# 환경 변수 파일 보안
chmod 600 .env
```

### 네트워크 보안
- Gateway API는 localhost:8001에서만 접근 가능
- PostgreSQL과 Redis는 로컬 접속만 허용
- OKX WebSocket은 안전한 wss:// 연결 사용

## 📞 지원

문제 발생 시:
1. `./scripts/manage_daemon.sh test` 실행
2. `./scripts/manage_daemon.sh status` 확인  
3. `./scripts/manage_daemon.sh logs` 로그 확인
4. 필요시 `./scripts/manage_daemon.sh restart` 재시작

---

**🎉 축하합니다! BTC-USDT-SWAP 무기한 선물 데이터가 24/7 실시간으로 수집되고 있습니다!**