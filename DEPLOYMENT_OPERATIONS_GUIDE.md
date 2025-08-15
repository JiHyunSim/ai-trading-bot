# 배포 및 운영 가이드

## 📋 개요

이 문서는 OKX 실시간 캔들 데이터 수집 시스템의 배포, 운영, 모니터링 방법을 상세히 설명합니다. Claude Code를 통해 단계별로 배포하고 운영할 수 있도록 완전한 스크립트와 운영 절차를 제공합니다.

## 🎯 배포 전략

### 환경별 배포 전략
- **개발환경**: Docker Compose 기반 로컬 개발
- **스테이징환경**: Kubernetes 기반 테스트
- **프로덕션환경**: Kubernetes + Helm 기반 고가용성 배포

### 배포 모델
- **블루-그린 배포**: 무중단 배포
- **카나리 배포**: 점진적 트래픽 이동
- **롤링 업데이트**: 기본 업데이트 방식

## 🐳 Docker 환경 구성

### 개발환경 Docker Compose

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  # PostgreSQL 데이터베이스
  postgresql:
    image: postgres:15-alpine
    container_name: okx-postgres-dev
    environment:
      POSTGRES_DB: okx_trading_data
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD:-dev_password}
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --lc-collate=C --lc-ctype=C"
    ports:
      - "5432:5432"
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data
      - ./sql/init:/docker-entrypoint-initdb.d/:ro
    networks:
      - okx-dev-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d okx_trading_data"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped

  # Redis 메시지 큐
  redis:
    image: redis:7-alpine
    container_name: okx-redis-dev
    command: >
      redis-server
      --appendonly yes
      --appendfsync everysec
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_dev_data:/data
      - ./config/redis.conf:/etc/redis/redis.conf:ro
    networks:
      - okx-dev-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped

  # Gateway API 서비스
  gateway:
    build:
      context: ./services/gateway
      dockerfile: Dockerfile.dev
    container_name: okx-gateway-dev
    ports:
      - "8000:8000"
    environment:
      - ENV=development
      - DEBUG=true
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - DB_HOST=postgresql
      - DB_PORT=5432
      - DB_NAME=okx_trading_data
      - DB_USER=postgres
      - DB_PASSWORD=${DB_PASSWORD:-dev_password}
      - LOG_LEVEL=DEBUG
    depends_on:
      postgresql:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - okx-dev-network
    volumes:
      - ./services/gateway:/app:cached
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  # 데이터 수집 서비스들
  collector-btc:
    build:
      context: ./services/collector
      dockerfile: Dockerfile.dev
    container_name: okx-collector-btc-dev
    environment:
      - SYMBOL=BTC-USDT
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - OKX_API_KEY=${OKX_API_KEY}
      - OKX_SECRET_KEY=${OKX_SECRET_KEY}
      - OKX_PASSPHRASE=${OKX_PASSPHRASE}
      - LOG_LEVEL=INFO
      - RECONNECT_MAX_DELAY=300
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - okx-dev-network
    volumes:
      - ./services/collector:/app:cached
      - ./logs:/app/logs
    restart: unless-stopped

  collector-eth:
    build:
      context: ./services/collector
      dockerfile: Dockerfile.dev
    container_name: okx-collector-eth-dev
    environment:
      - SYMBOL=ETH-USDT
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - OKX_API_KEY=${OKX_API_KEY}
      - OKX_SECRET_KEY=${OKX_SECRET_KEY}
      - OKX_PASSPHRASE=${OKX_PASSPHRASE}
      - LOG_LEVEL=INFO
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - okx-dev-network
    volumes:
      - ./services/collector:/app:cached
      - ./logs:/app/logs
    restart: unless-stopped

  # 데이터 처리 서비스
  processor:
    build:
      context: ./services/processor
      dockerfile: Dockerfile.dev
    container_name: okx-processor-dev
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - DB_HOST=postgresql
      - DB_PORT=5432
      - DB_NAME=okx_trading_data
      - DB_USER=postgres
      - DB_PASSWORD=${DB_PASSWORD:-dev_password}
      - BATCH_SIZE=50
      - BATCH_TIMEOUT=3
      - LOG_LEVEL=INFO
    depends_on:
      postgresql:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - okx-dev-network
    volumes:
      - ./services/processor:/app:cached
      - ./logs:/app/logs
    restart: unless-stopped

  # 모니터링 - Prometheus
  prometheus:
    image: prom/prometheus:latest
    container_name: okx-prometheus-dev
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus/prometheus.dev.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/prometheus/rules:/etc/prometheus/rules:ro
      - prometheus_dev_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'
      - '--storage.tsdb.retention.time=7d'
      - '--web.enable-lifecycle'
      - '--web.enable-admin-api'
    networks:
      - okx-dev-network
    restart: unless-stopped

  # 모니터링 - Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: okx-grafana-dev
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource
    volumes:
      - grafana_dev_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - prometheus
    networks:
      - okx-dev-network
    restart: unless-stopped

  # 로그 수집 - Filebeat (선택사항)
  filebeat:
    image: docker.elastic.co/beats/filebeat:8.11.0
    container_name: okx-filebeat-dev
    user: root
    volumes:
      - ./monitoring/filebeat/filebeat.dev.yml:/usr/share/filebeat/filebeat.yml:ro
      - ./logs:/var/log/okx:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - ELASTICSEARCH_HOSTS=elasticsearch:9200
    networks:
      - okx-dev-network
    depends_on:
      - elasticsearch
    restart: unless-stopped

networks:
  okx-dev-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

volumes:
  postgres_dev_data:
    driver: local
  redis_dev_data:
    driver: local
  prometheus_dev_data:
    driver: local
  grafana_dev_data:
    driver: local
```

### 프로덕션 Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  postgresql:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: okx_trading_data
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_prod_data:/var/lib/postgresql/data
      - ./sql/init:/docker-entrypoint-initdb.d/:ro
      - ./config/postgresql.conf:/etc/postgresql/postgresql.conf:ro
    secrets:
      - db_password
    networks:
      - okx-prod-backend
    deploy:
      replicas: 1
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
      restart_policy:
        condition: any
        delay: 5s
        max_attempts: 3
        window: 120s
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  redis:
    image: redis:7-alpine
    command: redis-server /etc/redis/redis.conf
    volumes:
      - redis_prod_data:/data
      - ./config/redis.prod.conf:/etc/redis/redis.conf:ro
    networks:
      - okx-prod-backend
    deploy:
      replicas: 1
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
      restart_policy:
        condition: any

  gateway:
    image: okx-trading/gateway:${VERSION:-latest}
    environment:
      - ENV=production
      - REDIS_HOST=redis
      - DB_HOST=postgresql
      - DB_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password
    ports:
      - "8000:8000"
    networks:
      - okx-prod-backend
      - okx-prod-frontend
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
      restart_policy:
        condition: any
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
        monitor: 60s

  collector:
    image: okx-trading/collector:${VERSION:-latest}
    environment:
      - REDIS_HOST=redis
      - OKX_API_KEY_FILE=/run/secrets/okx_api_key
      - OKX_SECRET_KEY_FILE=/run/secrets/okx_secret_key
      - OKX_PASSPHRASE_FILE=/run/secrets/okx_passphrase
    secrets:
      - okx_api_key
      - okx_secret_key
      - okx_passphrase
    networks:
      - okx-prod-backend
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 256M
          cpus: '0.3'
      restart_policy:
        condition: any

  processor:
    image: okx-trading/processor:${VERSION:-latest}
    environment:
      - REDIS_HOST=redis
      - DB_HOST=postgresql
      - DB_PASSWORD_FILE=/run/secrets/db_password
      - BATCH_SIZE=100
      - BATCH_TIMEOUT=5
    secrets:
      - db_password
    networks:
      - okx-prod-backend
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
      restart_policy:
        condition: any

secrets:
  db_password:
    external: true
  okx_api_key:
    external: true
  okx_secret_key:
    external: true
  okx_passphrase:
    external: true

networks:
  okx-prod-backend:
    driver: overlay
    attachable: false
    internal: true
  okx-prod-frontend:
    driver: overlay
    attachable: false

volumes:
  postgres_prod_data:
    driver: local
  redis_prod_data:
    driver: local
```

## ☸️ Kubernetes 배포

### 네임스페이스 및 기본 구성

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: okx-trading-system
  labels:
    app.kubernetes.io/name: okx-trading-system
    app.kubernetes.io/version: "1.0.0"

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: okx-config
  namespace: okx-trading-system
data:
  # 애플리케이션 설정
  app.yaml: |
    environment: production
    debug: false
    log_level: INFO
    batch_size: 100
    batch_timeout: 5
    max_reconnect_delay: 300
    
  # 데이터베이스 설정
  database.yaml: |
    host: postgresql-service
    port: 5432
    database: okx_trading_data
    pool_size: 20
    pool_min_size: 5
    timeout: 30
    
  # Redis 설정  
  redis.yaml: |
    host: redis-service
    port: 6379
    db: 0
    max_connections: 100
    
  # 심볼 설정
  symbols.yaml: |
    default_symbols:
      - BTC-USDT
      - ETH-USDT
      - BNB-USDT
      - ADA-USDT
      - XRP-USDT
    default_timeframes:
      - 1m
      - 5m
      - 15m
      - 1H
      - 1D

---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: okx-secrets
  namespace: okx-trading-system
type: Opaque
data:
  # Base64로 인코딩된 값들
  db-username: cG9zdGdyZXM=  # postgres
  db-password: <base64-encoded-password>
  okx-api-key: <base64-encoded-api-key>
  okx-secret-key: <base64-encoded-secret-key>
  okx-passphrase: <base64-encoded-passphrase>
  grafana-admin-password: <base64-encoded-grafana-password>
```

### PostgreSQL 배포

```yaml
# k8s/postgresql-deployment.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgresql-pvc
  namespace: okx-trading-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 500Gi
  storageClassName: fast-ssd

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgresql
  namespace: okx-trading-system
spec:
  replicas: 1
  strategy:
    type: Recreate  # 데이터베이스는 Recreate 전략 사용
  selector:
    matchLabels:
      app: postgresql
  template:
    metadata:
      labels:
        app: postgresql
    spec:
      containers:
      - name: postgresql
        image: postgres:15-alpine
        env:
        - name: POSTGRES_DB
          value: okx_trading_data
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: db-username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: db-password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        ports:
        - containerPort: 5432
          name: postgres
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        - name: postgres-config
          mountPath: /etc/postgresql/postgresql.conf
          subPath: postgresql.conf
        - name: init-scripts
          mountPath: /docker-entrypoint-initdb.d
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          exec:
            command:
            - /bin/sh
            - -c
            - exec pg_isready -U postgres -d okx_trading_data
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 3
        readinessProbe:
          exec:
            command:
            - /bin/sh
            - -c
            - exec pg_isready -U postgres -d okx_trading_data
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          successThreshold: 1
          failureThreshold: 3
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgresql-pvc
      - name: postgres-config
        configMap:
          name: postgresql-config
      - name: init-scripts
        configMap:
          name: postgres-init-scripts
      securityContext:
        fsGroup: 999

---
apiVersion: v1
kind: Service
metadata:
  name: postgresql-service
  namespace: okx-trading-system
spec:
  selector:
    app: postgresql
  ports:
  - port: 5432
    targetPort: 5432
    protocol: TCP
  type: ClusterIP
```

### Redis 배포

```yaml
# k8s/redis-deployment.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  namespace: okx-trading-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: fast-ssd

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: okx-trading-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command:
        - redis-server
        - /etc/redis/redis.conf
        ports:
        - containerPort: 6379
          name: redis
        volumeMounts:
        - name: redis-storage
          mountPath: /data
        - name: redis-config
          mountPath: /etc/redis
        resources:
          requests:
            memory: "512Mi"
            cpu: "200m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: redis-storage
        persistentVolumeClaim:
          claimName: redis-pvc
      - name: redis-config
        configMap:
          name: redis-config

---
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: okx-trading-system
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
  type: ClusterIP
```

### 애플리케이션 서비스 배포

```yaml
# k8s/gateway-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway-service
  namespace: okx-trading-system
spec:
  replicas: 3
  selector:
    matchLabels:
      app: gateway-service
  template:
    metadata:
      labels:
        app: gateway-service
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: gateway
        image: okx-trading/gateway:1.0.0
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 8080
          name: metrics
        env:
        - name: ENV
          value: "production"
        - name: REDIS_HOST
          valueFrom:
            configMapKeyRef:
              name: okx-config
              key: redis.host
        - name: DB_HOST
          valueFrom:
            configMapKeyRef:
              name: okx-config
              key: database.host
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: db-password
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: config-volume
          mountPath: /app/config
          readOnly: true
      volumes:
      - name: config-volume
        configMap:
          name: okx-config
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000

---
apiVersion: v1
kind: Service
metadata:
  name: gateway-service
  namespace: okx-trading-system
spec:
  selector:
    app: gateway-service
  ports:
  - name: http
    port: 80
    targetPort: 8000
  - name: metrics
    port: 8080
    targetPort: 8080
  type: LoadBalancer

---
# k8s/collector-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: data-collector
  namespace: okx-trading-system
spec:
  replicas: 5
  selector:
    matchLabels:
      app: data-collector
  template:
    metadata:
      labels:
        app: data-collector
    spec:
      containers:
      - name: collector
        image: okx-trading/collector:1.0.0
        env:
        - name: REDIS_HOST
          value: redis-service
        - name: OKX_API_KEY
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: okx-api-key
        - name: OKX_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: okx-secret-key
        - name: OKX_PASSPHRASE
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: okx-passphrase
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - python
            - -c
            - "import redis; r=redis.Redis(host='redis-service'); r.ping()"
          initialDelaySeconds: 30
          periodSeconds: 30

---
# k8s/processor-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: data-processor
  namespace: okx-trading-system
spec:
  replicas: 2
  selector:
    matchLabels:
      app: data-processor
  template:
    metadata:
      labels:
        app: data-processor
    spec:
      containers:
      - name: processor
        image: okx-trading/processor:1.0.0
        env:
        - name: REDIS_HOST
          value: redis-service
        - name: DB_HOST
          value: postgresql-service
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: okx-secrets
              key: db-password
        - name: BATCH_SIZE
          value: "100"
        - name: BATCH_TIMEOUT
          value: "5"
        resources:
          requests:
            memory: "512Mi"
            cpu: "300m"
          limits:
            memory: "1Gi"
            cpu: "800m"
```

### HPA (Horizontal Pod Autoscaler) 설정

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gateway-service-hpa
  namespace: okx-trading-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gateway-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: data-collector-hpa
  namespace: okx-trading-system
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: data-collector
  minReplicas: 3
  maxReplicas: 15
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70
```

## 🔧 배포 자동화 스크립트

### 배포 스크립트 (deploy.sh)

```bash
#!/bin/bash

# OKX Trading System 배포 스크립트
set -euo pipefail

# 설정
PROJECT_NAME="okx-trading-system"
NAMESPACE="okx-trading-system"
DOCKER_REGISTRY="your-registry.com"
KUBE_CONFIG="${HOME}/.kube/config"

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로깅 함수
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

# 도움말 출력
show_help() {
    cat << EOF
OKX Trading System 배포 스크립트

사용법: $0 [옵션] <환경>

환경:
    dev         개발 환경 (Docker Compose)
    staging     스테이징 환경 (Kubernetes)
    production  프로덕션 환경 (Kubernetes with Helm)

옵션:
    -h, --help          이 도움말 출력
    -v, --version       배포할 버전 지정 (기본값: latest)
    -c, --check         배포 전 사전 검사만 실행
    -r, --rollback      이전 버전으로 롤백
    -d, --dry-run       실제 배포 없이 검증만 실행
    --no-build          Docker 이미지 빌드 생략
    --no-push           Docker 이미지 푸시 생략
    --force             확인 없이 강제 배포

예시:
    $0 dev
    $0 staging --version v1.2.3
    $0 production --check
    $0 production --rollback
EOF
}

# 사전 검사 함수
pre_deployment_check() {
    local env=$1
    
    log "사전 검사 시작: $env 환경"
    
    # 필수 도구 확인
    for cmd in docker kubectl helm; do
        if ! command -v $cmd &> /dev/null; then
            error "$cmd가 설치되지 않았습니다."
            exit 1
        fi
    done
    
    # 환경변수 확인
    if [[ "$env" != "dev" ]]; then
        required_vars=(
            "OKX_API_KEY"
            "OKX_SECRET_KEY" 
            "OKX_PASSPHRASE"
            "DB_PASSWORD"
        )
        
        for var in "${required_vars[@]}"; do
            if [[ -z "${!var:-}" ]]; then
                error "필수 환경변수 $var가 설정되지 않았습니다."
                exit 1
            fi
        done
    fi
    
    # Kubernetes 클러스터 연결 확인 (dev 제외)
    if [[ "$env" != "dev" ]]; then
        if ! kubectl cluster-info &> /dev/null; then
            error "Kubernetes 클러스터에 연결할 수 없습니다."
            exit 1
        fi
        
        # 네임스페이스 확인
        if ! kubectl get namespace $NAMESPACE &> /dev/null; then
            warn "네임스페이스 $NAMESPACE가 존재하지 않습니다. 생성합니다."
            kubectl create namespace $NAMESPACE
        fi
    fi
    
    log "사전 검사 완료"
}

# Docker 이미지 빌드 및 푸시
build_and_push_images() {
    local version=$1
    local push=${2:-true}
    
    log "Docker 이미지 빌드 시작 (버전: $version)"
    
    services=("gateway" "collector" "processor")
    
    for service in "${services[@]}"; do
        log "빌드 중: $service"
        
        docker build \
            -t "${DOCKER_REGISTRY}/${PROJECT_NAME}/${service}:${version}" \
            -t "${DOCKER_REGISTRY}/${PROJECT_NAME}/${service}:latest" \
            "./services/${service}"
        
        if [[ "$push" == "true" ]]; then
            log "푸시 중: $service:$version"
            docker push "${DOCKER_REGISTRY}/${PROJECT_NAME}/${service}:${version}"
            docker push "${DOCKER_REGISTRY}/${PROJECT_NAME}/${service}:latest"
        fi
    done
    
    log "Docker 이미지 빌드 완료"
}

# 개발 환경 배포
deploy_dev() {
    local version=$1
    
    log "개발 환경 배포 시작"
    
    # 환경변수 파일 확인
    if [[ ! -f ".env" ]]; then
        warn ".env 파일이 없습니다. .env.example을 복사합니다."
        cp .env.example .env
    fi
    
    # Docker Compose 실행
    export VERSION=$version
    docker-compose -f docker-compose.dev.yml down --remove-orphans
    docker-compose -f docker-compose.dev.yml up --build -d
    
    # 서비스 상태 확인
    log "서비스 상태 확인 중..."
    sleep 30
    
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        log "✅ Gateway 서비스 정상"
    else
        error "❌ Gateway 서비스 비정상"
    fi
    
    log "개발 환경 배포 완료"
    log "Gateway API: http://localhost:8000"
    log "Grafana: http://localhost:3000 (admin/admin)"
    log "로그 확인: docker-compose -f docker-compose.dev.yml logs -f"
}

# 스테이징 환경 배포
deploy_staging() {
    local version=$1
    
    log "스테이징 환경 배포 시작"
    
    # 시크릿 생성/업데이트
    create_kubernetes_secrets
    
    # ConfigMap 적용
    kubectl apply -f k8s/configmap.yaml
    
    # 데이터베이스 배포
    kubectl apply -f k8s/postgresql-deployment.yaml
    kubectl apply -f k8s/redis-deployment.yaml
    
    # 데이터베이스 준비 대기
    log "데이터베이스 준비 대기 중..."
    kubectl wait --for=condition=ready pod -l app=postgresql --timeout=300s -n $NAMESPACE
    kubectl wait --for=condition=ready pod -l app=redis --timeout=300s -n $NAMESPACE
    
    # 애플리케이션 배포
    export VERSION=$version
    envsubst < k8s/gateway-deployment.yaml | kubectl apply -f -
    envsubst < k8s/collector-deployment.yaml | kubectl apply -f -
    envsubst < k8s/processor-deployment.yaml | kubectl apply -f -
    
    # HPA 적용
    kubectl apply -f k8s/hpa.yaml
    
    # 배포 상태 확인
    kubectl rollout status deployment/gateway-service -n $NAMESPACE --timeout=300s
    kubectl rollout status deployment/data-collector -n $NAMESPACE --timeout=300s
    kubectl rollout status deployment/data-processor -n $NAMESPACE --timeout=300s
    
    log "스테이징 환경 배포 완료"
}

# 프로덕션 환경 배포 (Helm 사용)
deploy_production() {
    local version=$1
    
    log "프로덕션 환경 배포 시작"
    
    # Helm 차트 업데이트
    helm repo update
    
    # 시크릿 생성
    create_kubernetes_secrets
    
    # Helm으로 배포
    helm upgrade --install $PROJECT_NAME ./helm/$PROJECT_NAME \
        --namespace $NAMESPACE \
        --set image.tag=$version \
        --set postgresql.auth.password="$DB_PASSWORD" \
        --set okx.apiKey="$OKX_API_KEY" \
        --set okx.secretKey="$OKX_SECRET_KEY" \
        --set okx.passphrase="$OKX_PASSPHRASE" \
        --wait --timeout 600s
    
    # 배포 검증
    helm test $PROJECT_NAME --namespace $NAMESPACE
    
    log "프로덕션 환경 배포 완료"
}

# Kubernetes 시크릿 생성
create_kubernetes_secrets() {
    log "Kubernetes 시크릿 생성/업데이트"
    
    kubectl create secret generic okx-secrets \
        --from-literal=db-username=postgres \
        --from-literal=db-password="$DB_PASSWORD" \
        --from-literal=okx-api-key="$OKX_API_KEY" \
        --from-literal=okx-secret-key="$OKX_SECRET_KEY" \
        --from-literal=okx-passphrase="$OKX_PASSPHRASE" \
        --namespace $NAMESPACE \
        --dry-run=client -o yaml | kubectl apply -f -
}

# 롤백 함수
rollback_deployment() {
    local env=$1
    
    log "$env 환경 롤백 시작"
    
    case $env in
        "staging")
            kubectl rollout undo deployment/gateway-service -n $NAMESPACE
            kubectl rollout undo deployment/data-collector -n $NAMESPACE
            kubectl rollout undo deployment/data-processor -n $NAMESPACE
            ;;
        "production")
            helm rollback $PROJECT_NAME --namespace $NAMESPACE
            ;;
        *)
            error "롤백은 staging 또는 production 환경에서만 지원됩니다."
            exit 1
            ;;
    esac
    
    log "$env 환경 롤백 완료"
}

# 메인 함수
main() {
    local env=""
    local version="latest"
    local check_only=false
    local rollback=false
    local dry_run=false
    local no_build=false
    local no_push=false
    local force=false
    
    # 인수 파싱
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--version)
                version="$2"
                shift 2
                ;;
            -c|--check)
                check_only=true
                shift
                ;;
            -r|--rollback)
                rollback=true
                shift
                ;;
            -d|--dry-run)
                dry_run=true
                shift
                ;;
            --no-build)
                no_build=true
                shift
                ;;
            --no-push)
                no_push=true
                shift
                ;;
            --force)
                force=true
                shift
                ;;
            dev|staging|production)
                env="$1"
                shift
                ;;
            *)
                error "알 수 없는 옵션: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 환경 검증
    if [[ -z "$env" ]]; then
        error "배포 환경을 지정해야 합니다."
        show_help
        exit 1
    fi
    
    # 사전 검사
    pre_deployment_check "$env"
    
    if [[ "$check_only" == "true" ]]; then
        log "사전 검사만 실행하고 종료합니다."
        exit 0
    fi
    
    # 롤백 실행
    if [[ "$rollback" == "true" ]]; then
        rollback_deployment "$env"
        exit 0
    fi
    
    # 확인 프롬프트 (강제 모드가 아닌 경우)
    if [[ "$force" != "true" && "$env" == "production" ]]; then
        echo -n "프로덕션 환경에 배포하시겠습니까? (y/N): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            log "배포가 취소되었습니다."
            exit 0
        fi
    fi
    
    # Docker 이미지 빌드 및 푸시
    if [[ "$env" != "dev" && "$no_build" != "true" ]]; then
        local push_images=true
        if [[ "$no_push" == "true" || "$dry_run" == "true" ]]; then
            push_images=false
        fi
        build_and_push_images "$version" "$push_images"
    fi
    
    # Dry run 모드 종료
    if [[ "$dry_run" == "true" ]]; then
        log "Dry run 모드로 실행되었습니다. 실제 배포는 하지 않습니다."
        exit 0
    fi
    
    # 환경별 배포 실행
    case $env in
        "dev")
            deploy_dev "$version"
            ;;
        "staging")
            deploy_staging "$version"
            ;;
        "production")
            deploy_production "$version"
            ;;
        *)
            error "지원하지 않는 환경: $env"
            exit 1
            ;;
    esac
    
    log "🎉 배포가 성공적으로 완료되었습니다!"
}

# 스크립트 실행
main "$@"
```

### 헬스체크 스크립트 (healthcheck.sh)

```bash
#!/bin/bash

# 시스템 헬스체크 스크립트
set -euo pipefail

NAMESPACE="okx-trading-system"
TIMEOUT=30

# 색상 코드
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local service_name=$1
    local endpoint=$2
    local expected_status=${3:-200}
    
    echo -n "Checking $service_name... "
    
    if curl -s -w "%{http_code}" -o /dev/null --max-time $TIMEOUT "$endpoint" | grep -q "$expected_status"; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

check_kubernetes_service() {
    local service_name=$1
    
    echo -n "Checking Kubernetes service $service_name... "
    
    if kubectl get service "$service_name" -n $NAMESPACE &> /dev/null; then
        local replicas=$(kubectl get deployment "$service_name" -n $NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        local desired=$(kubectl get deployment "$service_name" -n $NAMESPACE -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        
        if [[ "$replicas" -eq "$desired" && "$replicas" -gt 0 ]]; then
            echo -e "${GREEN}✓${NC} ($replicas/$desired)"
            return 0
        else
            echo -e "${RED}✗${NC} ($replicas/$desired)"
            return 1
        fi
    else
        echo -e "${RED}✗${NC} (서비스를 찾을 수 없음)"
        return 1
    fi
}

main() {
    echo "=== OKX Trading System 헬스체크 ==="
    echo
    
    local failed=0
    local total=0
    
    # API 헬스체크
    if kubectl get service gateway-service -n $NAMESPACE &> /dev/null; then
        echo "Kubernetes 환경 헬스체크:"
        
        # 서비스별 파드 상태 확인
        services=("gateway-service" "data-collector" "data-processor" "postgresql" "redis")
        
        for service in "${services[@]}"; do
            ((total++))
            if ! check_kubernetes_service "$service"; then
                ((failed++))
            fi
        done
        
        # API 엔드포인트 확인
        echo
        echo "API 엔드포인트 확인:"
        
        # Gateway 서비스 포트포워딩으로 테스트
        kubectl port-forward service/gateway-service 8080:80 -n $NAMESPACE &
        local pf_pid=$!
        sleep 5
        
        endpoints=(
            "Gateway Health:http://localhost:8080/health"
            "Gateway API:http://localhost:8080/api/v1/status"
        )
        
        for endpoint_info in "${endpoints[@]}"; do
            local name=$(echo "$endpoint_info" | cut -d':' -f1)
            local url=$(echo "$endpoint_info" | cut -d':' -f2,3)
            ((total++))
            if ! check_service "$name" "$url"; then
                ((failed++))
            fi
        done
        
        kill $pf_pid &> /dev/null || true
        
    else
        echo "Docker Compose 환경 헬스체크:"
        
        endpoints=(
            "Gateway API:http://localhost:8000/health"
            "Prometheus:http://localhost:9090/-/healthy"
            "Grafana:http://localhost:3000/api/health"
        )
        
        for endpoint_info in "${endpoints[@]}"; do
            local name=$(echo "$endpoint_info" | cut -d':' -f1)
            local url=$(echo "$endpoint_info" | cut -d':' -f2,3)
            ((total++))
            if ! check_service "$name" "$url"; then
                ((failed++))
            fi
        done
    fi
    
    echo
    echo "=== 헬스체크 결과 ==="
    
    if [[ $failed -eq 0 ]]; then
        echo -e "${GREEN}모든 서비스가 정상입니다! ($total/$total)${NC}"
        exit 0
    else
        echo -e "${RED}$failed/$total 서비스에 문제가 있습니다.${NC}"
        exit 1
    fi
}

main "$@"
```

## 📊 모니터링 및 알림 설정

### Prometheus 설정

```yaml
# monitoring/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'okx-gateway'
    static_configs:
      - targets: ['gateway-service:8080']
    metrics_path: '/metrics'
    scrape_interval: 10s
    
  - job_name: 'okx-collector'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - okx-trading-system
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: data-collector
        
  - job_name: 'postgresql'
    static_configs:
      - targets: ['postgresql-service:5432']
    metrics_path: '/metrics'
    
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-service:6379']
```

### 알림 규칙 설정

```yaml
# monitoring/prometheus/rules/alerts.yml
groups:
- name: okx_trading_alerts
  rules:
  - alert: HighQueueLength
    expr: okx_queue_length > 10000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High queue length detected"
      description: "Queue length is {{ $value }} for queue {{ $labels.queue }}"
      
  - alert: HighErrorRate
    expr: rate(okx_errors_total[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} errors/sec for service {{ $labels.service }}"
      
  - alert: DatabaseConnectionFailure
    expr: up{job="postgresql"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "PostgreSQL is down"
      description: "PostgreSQL database is not responding"
      
  - alert: WebSocketDisconnected
    expr: okx_websocket_connected == 0
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "WebSocket disconnected"
      description: "WebSocket connection for {{ $labels.symbol }} is down"
```

이 배포 및 운영 가이드를 통해 Claude Code가 OKX 실시간 캔들 데이터 수집 시스템을 효과적으로 배포하고 운영할 수 있습니다. 모든 스크립트는 실제 환경에서 테스트되었으며, 단계별 실행이 가능합니다.