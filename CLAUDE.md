# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a documentation repository for an **OKX Real-time Candlestick Data Collection System** - a comprehensive microservices-based trading data collection and processing system. The project documentation is written in Korean and provides complete implementation guides for building a production-ready trading system.

## System Architecture

**Core Components:**
- **Gateway Service**: FastAPI-based REST API and subscription management
- **Data Collector**: WebSocket clients for real-time data collection from OKX API
- **Data Processor**: Batch processing and PostgreSQL storage with partitioning
- **Message Queue**: Redis-based asynchronous message delivery

**Technology Stack:**
- Backend: Python 3.11+, FastAPI, AsyncIO
- Database: PostgreSQL 15+ with monthly partitioning, Redis 7+
- Containerization: Docker, Kubernetes
- Monitoring: Prometheus, Grafana

## Documentation Structure

### Core Implementation Guides
- `OKX_TRADING_SYSTEM_IMPLEMENTATION_GUIDE.md` - Main system implementation guide with complete architecture and code examples
- `API_DOCUMENTATION.md` - REST API specifications and client examples
- `DATABASE_SCHEMA_GUIDE.md` - PostgreSQL schema, partitioning, and optimization
- `CODE_TEMPLATES_EXAMPLES.md` - Complete code templates and project structure
- `DEPLOYMENT_OPERATIONS_GUIDE.md` - Docker, Kubernetes deployment and operations

### Key Implementation Details

**Database Design:**
- PostgreSQL with monthly partitioning for candlestick data
- Automated partition management functions
- Performance optimization with proper indexing
- Data quality validation and monitoring

**API Endpoints:**
- `/api/v1/subscribe` - Symbol subscription management
- `/api/v1/data/{symbol}/{timeframe}` - Historical data queries
- `/api/v1/status/{symbol}` - Real-time status monitoring
- `/health` - System health checks

**WebSocket Integration:**
- OKX WebSocket API integration (`wss://ws.okx.com:8443/ws/v5/public`)
- Automatic reconnection with exponential backoff
- Dead Letter Queue for failed message processing

## Development Commands

Since this is a documentation-only repository, there are no build/test commands. When implementing the actual system:

```bash
# Development environment setup
docker-compose -f docker-compose.dev.yml up -d

# Production deployment  
kubectl apply -f k8s/

# Database initialization
psql -f sql/init/01_extensions.sql
psql -f sql/init/02_schema.sql

# Service testing
curl -X POST "http://localhost:8000/api/v1/subscribe" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["BTC-USDT"], "timeframes": ["1m"]}'
```

## Architecture Patterns

**Microservices Design:**
- Each service (Gateway, Collector, Processor) is independently deployable
- Redis message bus for loose coupling between services
- Horizontal scaling through container replication

**Data Flow:**
```
OKX WebSocket → Collector → Redis Queue → Processor → PostgreSQL
                    ↓
              Gateway API ← Redis ← Status Updates
```

**High Availability:**
- PostgreSQL master-slave replication
- Redis clustering for message queue reliability
- Kubernetes deployment with health checks and auto-scaling

## Configuration Management

**Environment Variables:**
- `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE` - OKX API credentials
- `DB_HOST`, `DB_PASSWORD` - Database connection
- `REDIS_HOST` - Message queue connection
- `BATCH_SIZE`, `BATCH_TIMEOUT` - Processing optimization

**Key Configuration Files:**
- `.env` - Environment-specific settings
- `docker-compose.yml` - Container orchestration
- `k8s/` - Kubernetes manifests
- `sql/init/` - Database initialization scripts

## Monitoring and Operations

**Health Monitoring:**
- Prometheus metrics collection
- Grafana dashboards for visualization
- Database performance monitoring
- WebSocket connection status tracking

**Key Metrics:**
- Messages per second processing rate
- Queue length and backlog monitoring
- Database connection pool status
- Error rates and failed message tracking

## Security Considerations

**API Security:**
- Rate limiting implementation
- Input validation and sanitization
- Database access control

**Operational Security:**
- API key rotation procedures
- VPC network isolation
- TLS/SSL encryption for data in transit

## Implementation Notes

When implementing this system with Claude Code:

1. **Start with Database Setup**: Initialize PostgreSQL schema and partitioning first
2. **Implement Services Incrementally**: Begin with Gateway API, then Collector, then Processor
3. **Use Provided Templates**: All code templates are production-ready and include error handling
4. **Follow Korean Documentation**: The guides provide step-by-step implementation details
5. **Test Each Component**: Each service includes health checks and test endpoints

This documentation provides a complete blueprint for implementing a production-grade cryptocurrency trading data collection system using modern Python microservices architecture.