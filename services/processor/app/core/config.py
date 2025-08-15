"""Processor Service Configuration"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Processor Service 설정"""
    
    # 환경 설정
    ENV: str = Field(default="development", description="Environment")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # Redis 설정
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    
    # PostgreSQL 설정
    DB_HOST: str = Field(default="localhost", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_NAME: str = Field(default="okx_trading_data", description="Database name")
    DB_USER: str = Field(default="postgres", description="Database user")
    DB_PASSWORD: str = Field(default="", description="Database password")
    DB_POOL_SIZE: int = Field(default=20, description="Database pool size")
    DB_MAX_OVERFLOW: int = Field(default=30, description="Database max overflow")
    
    # 배치 처리 설정
    BATCH_SIZE: int = Field(default=100, description="Batch processing size")
    BATCH_TIMEOUT: int = Field(default=5, description="Batch timeout in seconds")
    MAX_RETRIES: int = Field(default=3, description="Max retry attempts")
    
    # 로깅 설정
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()