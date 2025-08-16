# 🐳 Docker 배치 실행 가이드

CCXT 기반 데이터 유지보수를 Docker 환경에서 실행하는 완전 자동화 시스템입니다.

## 📋 시스템 구성

### 컨테이너 서비스
- **postgres**: PostgreSQL 데이터베이스
- **ccxt-backfill**: 과거 데이터 일괄 수집
- **ccxt-maintenance**: 일회성 데이터 유지보수
- **ccxt-cron**: 자동 일일 유지보수 (크론 배치)

### 주요 파일
```
├── Dockerfile                     # 메인 애플리케이션 이미지
├── docker-compose.maintenance.yml # 유지보수 서비스 정의
├── .env.docker                   # 환경 변수 설정
└── scripts/docker-maintenance.sh  # 통합 실행 스크립트
```

## 🚀 빠른 시작

### 1. 환경 설정
```bash
# API 키 설정 (필수)
cp .env.docker .env.docker.local
vi .env.docker.local

# OKX API 정보 입력
OKX_API_KEY=your_actual_api_key
OKX_SECRET_KEY=your_actual_secret_key
OKX_PASSPHRASE=your_actual_passphrase
```

### 2. Docker 이미지 빌드
```bash
./scripts/docker-maintenance.sh build
```

### 3. 초기 데이터 수집 (선택사항)
```bash
# BTC/USDT:USDT 30일 백필
./scripts/docker-maintenance.sh backfill BTC/USDT:USDT 30

# ETH/USDT:USDT 60일 백필
./scripts/docker-maintenance.sh backfill ETH/USDT:USDT 60
```

### 4. 자동 일일 유지보수 시작
```bash
# 매일 오전 10시 자동 실행
./scripts/docker-maintenance.sh start-cron
```

## 📊 실행 명령어

### 기본 명령어
```bash
# 도움말
./scripts/docker-maintenance.sh help

# 이미지 빌드
./scripts/docker-maintenance.sh build

# 일회성 유지보수 실행
./scripts/docker-maintenance.sh maintenance

# 자동 유지보수 시작/중지
./scripts/docker-maintenance.sh start-cron
./scripts/docker-maintenance.sh stop-cron

# 서비스 상태 확인
./scripts/docker-maintenance.sh status

# 로그 보기
./scripts/docker-maintenance.sh logs

# 정리
./scripts/docker-maintenance.sh clean
```

### 고급 명령어
```bash
# 특정 심볼 백필
./scripts/docker-maintenance.sh backfill "BTC/USDT:USDT" 90

# Docker Compose 직접 실행
docker-compose --env-file .env.docker -f docker-compose.maintenance.yml \
  run --rm --profile maintenance ccxt-maintenance

# 개별 컨테이너 실행
docker run --rm --env-file .env.docker \
  ai-trading-bot-ccxt:latest \
  python scripts/ccxt_daily_maintenance.py --hours 48
```

## ⚙️ 설정 옵션

### 환경 변수 (.env.docker)
```bash
# 데이터베이스
DB_PASSWORD=trading_bot_password

# OKX API (필수)
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
OKX_SANDBOX=false

# 크론 스케줄 (기본: 매일 오전 10시)
CRON_SCHEDULE=0 10 * * *
```

### 크론 스케줄 변경
```bash
# 매일 오전 2시
CRON_SCHEDULE=0 2 * * *

# 매 6시간마다
CRON_SCHEDULE=0 */6 * * *

# 평일 오전 9시
CRON_SCHEDULE=0 9 * * 1-5
```

## 📋 운영 가이드

### 로그 모니터링
```bash
# 실시간 로그 모니터링
./scripts/docker-maintenance.sh logs

# 특정 컨테이너 로그
docker logs -f ai-trading-bot-ccxt-cron

# 로그 파일 직접 확인
docker exec ai-trading-bot-ccxt-cron tail -f /var/log/maintenance.log
```

### 상태 확인
```bash
# 서비스 상태
./scripts/docker-maintenance.sh status

# 컨테이너 상태
docker ps -a | grep ai-trading-bot

# 데이터베이스 연결 테스트
docker exec ai-trading-bot-postgres pg_isready -U trading_bot
```

### 데이터 확인
```bash
# PostgreSQL 접속
docker exec -it ai-trading-bot-postgres psql -U trading_bot -d trading_bot

# 최근 유지보수 결과 확인
SELECT symbol, timeframe, COUNT(*) as records, 
       MAX(timestamp_ms) as latest_data
FROM trading.candlesticks 
GROUP BY symbol, timeframe 
ORDER BY symbol, timeframe;
```

## 🛠️ 트러블슈팅

### 일반적인 문제

#### 1. API 키 오류
```bash
# 환경 변수 확인
docker exec ai-trading-bot-ccxt-cron env | grep OKX

# 올바른 API 키 설정 후 재시작
./scripts/docker-maintenance.sh stop-cron
./scripts/docker-maintenance.sh start-cron
```

#### 2. 데이터베이스 연결 실패
```bash
# PostgreSQL 컨테이너 상태 확인
docker ps | grep postgres

# 데이터베이스 재시작
docker-compose --env-file .env.docker -f docker-compose.maintenance.yml restart postgres
```

#### 3. 메모리 부족
```bash
# 리소스 사용량 확인
docker stats

# 불필요한 컨테이너 정리
./scripts/docker-maintenance.sh clean
```

### 수동 디버깅
```bash
# 컨테이너 내부 접속
docker exec -it ai-trading-bot-ccxt-cron /bin/bash

# 수동 스크립트 실행
python scripts/ccxt_daily_maintenance.py --dry-run

# 로그 레벨 변경
python scripts/ccxt_daily_maintenance.py --hours 25 --debug
```

## 🔧 커스터마이징

### 새로운 심볼 추가
```bash
# 환경 변수로 대상 심볼 지정
docker-compose --env-file .env.docker -f docker-compose.maintenance.yml \
  run --rm --profile maintenance ccxt-maintenance \
  python scripts/ccxt_daily_maintenance.py --symbols "BTC/USDT:USDT,ETH/USDT:USDT"
```

### 다른 거래소 지원
```bash
# Binance 사용
python scripts/ccxt_daily_maintenance.py --exchange binance
```

### 커스텀 스케줄
```bash
# docker-compose.maintenance.yml 수정
environment:
  - CRON_SCHEDULE=0 */4 * * *  # 4시간마다
```

## 📊 성능 최적화

### 리소스 제한
```yaml
# docker-compose.maintenance.yml에 추가
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
```

### 병렬 처리
```bash
# 여러 심볼 동시 처리
docker-compose --env-file .env.docker -f docker-compose.maintenance.yml \
  run --rm --profile maintenance ccxt-maintenance \
  python scripts/ccxt_daily_maintenance.py --symbols "BTC/USDT:USDT,ETH/USDT:USDT" --parallel
```

## 🔐 보안 설정

### API 키 보안
```bash
# Docker Secrets 사용 (Swarm 모드)
echo "your_api_key" | docker secret create okx_api_key -
```

### 네트워크 격리
```yaml
# docker-compose.maintenance.yml
networks:
  trading-bot-network:
    driver: bridge
    internal: true  # 외부 접속 차단
```

## 📈 모니터링 및 알림

### 로그 집계
```bash
# ELK Stack 연동
docker run -d --name filebeat \
  -v /var/lib/docker/containers:/var/lib/docker/containers:ro \
  elastic/filebeat:latest
```

### 알림 설정
```bash
# Slack 웹훅 연동
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

이 Docker 배치 시스템으로 완전 자동화된 CCXT 데이터 유지보수를 운영할 수 있습니다.