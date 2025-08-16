# 데이터 유지보수 시스템 가이드

## 개요

AI Trading Bot의 데이터 품질 유지를 위한 자동화된 유지보수 시스템입니다.

## 🛠️ 제공 도구

### 1. 일일 데이터 유지보수 배치 (`daily_data_maintenance.py`)

**목적**: 매일 오전 10시에 지난 25시간 동안의 데이터 무결성 검사 및 자동 수정

**주요 기능**:
- ✅ 데이터 갭 탐지 및 자동 백필
- 🔄 중복 데이터 제거  
- 🔧 잘못된 데이터 수정
- 📊 상세한 리포트 생성

**사용법**:
```bash
# 모든 활성 심볼 처리
python scripts/daily_data_maintenance.py

# 특정 심볼만 처리
python scripts/daily_data_maintenance.py --symbols BTC-USDT-SWAP,ETH-USDT-SWAP

# 드라이런 모드 (실제 변경 없이 확인만)
python scripts/daily_data_maintenance.py --dry-run
```

### 2. 과거 데이터 백필 스크립트 (`historical_data_backfill.py`)

**목적**: 심볼별 지난 2개월(또는 지정 기간) 캔들 데이터 일괄 수집

**주요 기능**:
- 📈 대량 과거 데이터 수집
- 🎯 심볼별 맞춤 처리
- ⚡ 병렬 처리로 고속 수집
- 📊 실시간 진행상황 추적

**사용법**:
```bash
# BTC-USDT-SWAP 2개월 데이터 백필
python scripts/historical_data_backfill.py BTC-USDT-SWAP

# 특정 타임프레임만 백필
python scripts/historical_data_backfill.py BTC-USDT-SWAP --timeframes 1h,4h,1d

# 6개월 데이터 백필
python scripts/historical_data_backfill.py BTC-USDT-SWAP --months 6

# 드라이런 모드
python scripts/historical_data_backfill.py BTC-USDT-SWAP --dry-run
```

### 3. 크론 스케줄러 (`cron_scheduler.py`)

**목적**: 일일 유지보수 배치의 자동 실행 스케줄 관리

**사용법**:
```bash
# 매일 오전 10시 크론 작업 설치
python scripts/cron_scheduler.py install

# 특정 심볼로 크론 작업 설치
python scripts/cron_scheduler.py install --symbols BTC-USDT-SWAP

# 커스텀 스케줄 (매일 오전 9시)
python scripts/cron_scheduler.py install --schedule "0 9 * * *"

# 현재 크론 작업 목록 확인
python scripts/cron_scheduler.py list

# 크론 작업 제거
python scripts/cron_scheduler.py remove

# Systemd 서비스 파일 생성
python scripts/cron_scheduler.py systemd
```

## 📅 일일 유지보수 프로세스

### 자동 실행 과정

1. **매일 오전 10시** 자동 실행
2. **활성 심볼 탐지** - 최근 25시간 내 데이터가 있는 심볼들
3. **타임프레임별 검사** - 5m, 15m, 1h, 4h, 1d
4. **무결성 검사**:
   - 데이터 갭 탐지
   - 중복 레코드 확인
   - 잘못된 데이터 식별
5. **자동 수정**:
   - OKX API로부터 누락 데이터 백필
   - 중복 데이터 제거
   - 유효하지 않은 데이터 삭제
6. **리포트 생성** - 처리 결과 상세 보고

### 처리 통계 예시

```
📊 DAILY DATA MAINTENANCE REPORT
============================================================
🕒 Started: 2024-01-15 10:00:01
🕒 Completed: 2024-01-15 10:05:23
⏱️  Duration: 322.1 seconds
📈 Symbols processed: 3
📊 Timeframes processed: 15
🔍 Gaps found: 7
✅ Gaps filled: 7
🔄 Duplicates removed: 12
🔧 Invalid data fixed: 2
============================================================
```

## 🎯 백필 프로세스

### 과거 데이터 수집

```bash
# 예시: BTC-USDT-SWAP 2개월 백필
python scripts/historical_data_backfill.py BTC-USDT-SWAP
```

**진행 과정**:
1. **데이터 범위 계산** - 현재로부터 2개월 전까지
2. **기존 데이터 확인** - 이미 저장된 데이터 범위 파악
3. **배치 단위 수집** - OKX API 제한 준수하여 300개씩 수집
4. **병렬 처리** - 여러 타임프레임 동시 처리
5. **중복 방지** - ON CONFLICT 처리로 중복 삽입 방지
6. **진행상황 추적** - 실시간 진행률 및 통계 표시

### 백필 리포트 예시

```
📈 HISTORICAL DATA BACKFILL PROGRESS
================================================================================
✅ BTC-USDT-SWAP/5m
    Expected: 17,280
    Fetched: 17,280
    Inserted: 15,432
    Duplicates: 1,848
    Completion: 100.0%
    Duration: 45.2s

✅ BTC-USDT-SWAP/1h
    Expected: 1,440
    Fetched: 1,440
    Inserted: 1,440
    Duplicates: 0
    Completion: 100.0%
    Duration: 12.1s

📊 OVERALL STATISTICS
----------------------------------------
Symbols Processed: 1
Timeframes Processed: 5
Total Api Calls: 124
Total Candles Fetched: 32,567
Total Candles Inserted: 30,245
Total Duplicates Skipped: 2,322

🎉 BACKFILL COMPLETED in 127.3 seconds
Success rate: 100.0%
```

## ⚙️ 설정 옵션

### 환경변수

```bash
# 데이터베이스 설정
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_bot
DB_PASSWORD=trading_bot_password
```

### 커맨드라인 옵션

**일일 유지보수**:
- `--symbols`: 처리할 심볼 목록 (쉼표 구분)
- `--db-*`: 데이터베이스 연결 설정
- `--dry-run`: 실제 변경 없이 시뮬레이션

**과거 데이터 백필**:
- `symbol`: 백필할 심볼 (필수)
- `--timeframes`: 타임프레임 목록 (기본: 5m,15m,1h,4h,1d)
- `--months`: 백필 기간 월수 (기본: 2)
- `--dry-run`: 실제 수집 없이 시뮬레이션

## 🔧 설치 및 설정

### 1. 의존성 설치

```bash
pip install aiohttp asyncpg structlog python-dotenv
```

### 2. 크론 작업 설치

```bash
# 기본 설정 (매일 오전 10시)
python scripts/cron_scheduler.py install

# 특정 심볼 지정
python scripts/cron_scheduler.py install --symbols BTC-USDT-SWAP,ETH-USDT-SWAP
```

### 3. Systemd 서비스 설치 (선택사항)

```bash
# 서비스 파일 생성
python scripts/cron_scheduler.py systemd

# 시스템에 설치
sudo cp scripts/systemd/ai-trading-bot-maintenance.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-trading-bot-maintenance.timer
sudo systemctl start ai-trading-bot-maintenance.timer
```

## 📊 모니터링

### 로그 확인

```bash
# 일일 유지보수 로그
tail -f logs/daily_maintenance.log

# Systemd 로그 (systemd 사용시)
journalctl -u ai-trading-bot-maintenance.service -f
```

### 크론 작업 상태 확인

```bash
# 크론 작업 목록
python scripts/cron_scheduler.py list

# 마지막 실행 시간 확인 (systemd)
systemctl status ai-trading-bot-maintenance.timer
```

## 🚨 문제 해결

### 일반적인 문제

1. **API 레이트 리미트**
   - 문제: OKX API 요청 제한 초과
   - 해결: 스크립트에 내장된 지연시간 조정 (0.2초 간격)

2. **데이터베이스 연결 실패**
   - 문제: PostgreSQL 연결 불가
   - 해결: DB 설정 및 방화벽 확인

3. **크론 작업 실행 안됨**
   - 문제: 크론탭이 실행되지 않음
   - 해결: 크론 데몬 상태 및 로그 확인

### 수동 실행 테스트

```bash
# 빠른 테스트 (드라이런)
python scripts/daily_data_maintenance.py --dry-run

# 특정 심볼 테스트
python scripts/daily_data_maintenance.py --symbols BTC-USDT-SWAP --dry-run

# 백필 테스트
python scripts/historical_data_backfill.py BTC-USDT-SWAP --dry-run
```

## 📈 성능 최적화

### 백필 성능

- **병렬 처리**: 최대 3개 심볼 동시 처리
- **배치 사이즈**: API 제한에 맞춘 300개 캔들/요청
- **연결 풀**: 효율적인 데이터베이스 연결 관리
- **요청 간격**: API 레이트 리미트 준수

### 일일 유지보수 성능

- **타겟 범위**: 지난 25시간으로 제한
- **스마트 갭 탐지**: 효율적인 누락 데이터 식별
- **배치 처리**: 대량 데이터 일괄 처리
- **중복 최적화**: 데이터베이스 레벨 중복 제거

## 🔒 보안 고려사항

### 데이터베이스 보안

- 환경변수로 민감정보 관리
- 최소 권한 원칙 적용
- 연결 암호화 권장

### API 보안

- 퍼블릭 API만 사용 (인증 불필요)
- 레이트 리미트 준수
- 에러 핸들링으로 서비스 안정성 확보

---

## 📞 지원

문제가 발생하거나 개선사항이 있으면 프로젝트 이슈로 등록해주세요.

**주요 파일**:
- `scripts/daily_data_maintenance.py` - 일일 유지보수 메인 스크립트
- `scripts/historical_data_backfill.py` - 과거 데이터 백필 스크립트  
- `scripts/cron_scheduler.py` - 크론 스케줄 관리 도구
- `README_DATA_MAINTENANCE.md` - 이 문서