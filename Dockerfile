FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 요구사항 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# CCXT 추가 설치
RUN pip install --no-cache-dir ccxt aiodns pycares

# 애플리케이션 코드 복사
COPY . .

# 스크립트 실행 권한 부여
RUN chmod +x scripts/*.py
RUN chmod +x run_ccxt_backfill.sh

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 헬스체크 스크립트 생성
RUN echo '#!/bin/bash\npython -c "import asyncpg, ccxt, structlog; print(\"Dependencies OK\")"' > /app/healthcheck.sh
RUN chmod +x /app/healthcheck.sh

# 헬스체크 설정
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /app/healthcheck.sh

# 기본 명령어
CMD ["python", "scripts/ccxt_daily_maintenance.py"]