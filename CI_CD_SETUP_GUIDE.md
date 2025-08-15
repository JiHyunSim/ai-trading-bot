# CI/CD 설정 가이드

## 📋 개요

이 문서는 AI 트레이딩 봇 프로젝트의 GitHub Actions CI/CD 파이프라인 설정 가이드입니다.

## 🔑 GitHub Secrets 설정

### 1. Repository Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions에서 다음 시크릿들을 설정하세요:

#### OKX API 관련
```
OKX_API_KEY=your_okx_api_key_here
OKX_SECRET_KEY=your_okx_secret_key_here
OKX_PASSPHRASE=your_okx_passphrase_here
```

#### 데이터베이스 관련
```
DB_PASSWORD=your_production_db_password
DB_HOST=your_production_db_host
DB_NAME=your_production_db_name
DB_USER=your_production_db_user
```

#### Redis 관련
```
REDIS_HOST=your_production_redis_host
REDIS_PASSWORD=your_production_redis_password
```

#### Codecov 관련 (선택사항)
```
CODECOV_TOKEN=your_codecov_token
```

#### Docker Hub 관련 (선택사항)
```
DOCKERHUB_USERNAME=your_dockerhub_username
DOCKERHUB_TOKEN=your_dockerhub_access_token
```

#### 배포 관련 (선택사항)
```
DEPLOY_SSH_KEY=your_deployment_ssh_private_key
DEPLOY_HOST=your_production_server_host
DEPLOY_USER=your_production_server_user
```

### 2. Environment Secrets 설정

Production 환경용 추가 시크릿 설정:

#### 모니터링 관련
```
PROMETHEUS_URL=your_prometheus_endpoint
GRAFANA_API_KEY=your_grafana_api_key
SLACK_WEBHOOK_URL=your_slack_notification_webhook
```

## 🚀 CI/CD 파이프라인 구조

### 워크플로우 단계
1. **Lint**: 코드 품질 검사 (flake8, black, isort, mypy)
2. **Test**: 단위 테스트 및 커버리지 (pytest, PostgreSQL, Redis)
3. **Security & Docker**: 보안 검사 및 Docker 빌드
4. **Deploy**: 프로덕션 배포 (main 브랜치만)

### 트리거 조건
- `push`: main, develop 브랜치
- `pull_request`: main, develop 브랜치
- `workflow_dispatch`: 수동 실행

## 🔧 로컬 개발 환경 설정

### 1. Pre-commit Hooks 설정
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files  # 최초 실행
```

### 2. 개발 의존성 설치
```bash
pip install -r requirements-dev.txt
```

### 3. 환경변수 파일 생성
```bash
cp .env.example .env
# .env 파일을 편집하여 로컬 개발용 값 설정
```

### 4. 로컬 테스트 실행
```bash
# 단위 테스트
pytest tests/ -v

# 커버리지 포함 테스트
pytest tests/ --cov=. --cov-report=html

# 특정 테스트 실행
pytest tests/test_gateway.py::test_subscribe -v
```

### 5. Docker Compose 테스트
```bash
# CI 환경 테스트
docker-compose -f docker-compose.ci.yml up --build

# 개발 환경 실행
docker-compose -f docker-compose.dev.yml up -d
```

## 📊 모니터링 및 알림

### 1. 테스트 커버리지
- Codecov 통합으로 커버리지 추적
- 최소 80% 커버리지 권장

### 2. 보안 검사
- Trivy 취약점 스캔
- Bandit 보안 분석
- Safety 의존성 보안 검사

### 3. 코드 품질
- SonarCloud 통합 (선택사항)
- CodeClimate 통합 (선택사항)

## 🔄 브랜치 전략

### GitFlow 기반 브랜치 전략
```
main (프로덕션)
├── develop (개발)
├── feature/feature-name (기능 개발)
├── hotfix/fix-name (긴급 수정)
└── release/version-number (릴리즈 준비)
```

### 브랜치별 CI/CD 동작
- **main**: 전체 파이프라인 + 프로덕션 배포
- **develop**: 전체 파이프라인 (배포 제외)
- **feature/***: Lint + Test 만 실행
- **hotfix/***: 전체 파이프라인 + 프로덕션 배포

## 🛠 문제 해결

### 1. 테스트 실패 시
```bash
# 로컬에서 동일한 환경으로 테스트
docker-compose -f docker-compose.ci.yml run gateway-test

# 특정 서비스 로그 확인
docker-compose -f docker-compose.ci.yml logs gateway-test
```

### 2. Docker 빌드 실패 시
```bash
# 로컬 Docker 빌드 테스트
docker build -t test-gateway ./services/gateway/

# 빌드 캐시 제거 후 재시도
docker system prune -a
```

### 3. 의존성 문제 시
```bash
# 의존성 업데이트
pip-compile requirements.in
pip-compile requirements-dev.in

# 보안 취약점 확인
safety check
```

## 📈 성능 최적화

### 1. CI 실행 시간 단축
- Docker layer 캐싱 활용
- 의존성 캐싱 최적화
- 병렬 테스트 실행

### 2. 리소스 사용량 최적화
- 테스트용 서비스 리소스 제한
- 불필요한 로그 출력 제거

## 🚦 배포 프로세스

### 1. 스테이징 배포
```yaml
# .github/workflows/staging.yml 참조
# develop 브랜치 → 스테이징 환경
```

### 2. 프로덕션 배포
```yaml
# main 브랜치 merge 시 자동 배포
# 또는 GitHub Release 생성 시 배포
```

### 3. 롤백 프로세스
```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/gateway
kubectl rollout undo deployment/collector
kubectl rollout undo deployment/processor
```

## 📝 체크리스트

### PR 생성 전 확인사항
- [ ] 모든 테스트 통과
- [ ] 커버리지 80% 이상 유지
- [ ] Pre-commit hooks 통과
- [ ] 문서 업데이트
- [ ] 환경변수 가이드 업데이트

### 배포 전 확인사항
- [ ] 스테이징 환경에서 검증 완료
- [ ] 데이터베이스 마이그레이션 준비
- [ ] 백업 계획 수립
- [ ] 롤백 계획 수립
- [ ] 모니터링 대시보드 준비

이 가이드를 따라 CI/CD 파이프라인을 구성하면 안정적이고 확장 가능한 AI 트레이딩 봇 시스템을 구축할 수 있습니다.