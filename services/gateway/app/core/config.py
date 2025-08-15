"""Gateway Service Configuration"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Gateway Service 설정"""
    
    # 환경 설정
    ENV: str = Field(default="development", description="Environment")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # API 설정
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    
    # Redis 설정
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    REDIS_SSL: bool = Field(default=False, description="Redis SSL")
    
    # 로깅 설정
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    LOG_FORMAT: str = Field(default="json", description="Log format")
    
    # 모니터링 설정
    PROMETHEUS_PORT: int = Field(default=8080, description="Prometheus metrics port")
    METRICS_ENABLED: bool = Field(default=True, description="Enable metrics")
    
    # 보안 설정
    SECRET_KEY: str = Field(default="dev-secret-key", description="Secret key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Token expiry minutes")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()