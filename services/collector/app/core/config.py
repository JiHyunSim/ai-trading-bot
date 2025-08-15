"""Collector Service Configuration"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Collector Service 설정"""
    
    # 환경 설정
    ENV: str = Field(default="development", description="Environment")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # OKX API 설정
    OKX_API_KEY: Optional[str] = Field(default=None, description="OKX API key")
    OKX_SECRET_KEY: Optional[str] = Field(default=None, description="OKX secret key")
    OKX_PASSPHRASE: Optional[str] = Field(default=None, description="OKX passphrase")
    OKX_SANDBOX: bool = Field(default=True, description="Use OKX sandbox")
    
    # WebSocket 설정
    WS_URL: str = Field(
        default="wss://ws.okx.com:8443/ws/v5/public",
        description="OKX WebSocket URL"
    )
    WS_SANDBOX_URL: str = Field(
        default="wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999",
        description="OKX Sandbox WebSocket URL"
    )
    
    # Redis 설정
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_DB: int = Field(default=0, description="Redis database")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    
    # 재연결 설정
    INITIAL_RECONNECT_DELAY: int = Field(default=5, description="Initial reconnect delay in seconds")
    MAX_RECONNECT_DELAY: int = Field(default=300, description="Max reconnect delay in seconds")
    MAX_RECONNECT_ATTEMPTS: int = Field(default=0, description="Max reconnect attempts (0 = infinite)")
    
    # 메시지 처리 설정
    MESSAGE_QUEUE_SIZE: int = Field(default=1000, description="Message queue size")
    BATCH_SIZE: int = Field(default=100, description="Batch processing size")
    
    # 로깅 설정
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    
    # 심볼 설정 (환경변수로 설정 가능)
    SYMBOL: Optional[str] = Field(default=None, description="Default symbol to collect")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def websocket_url(self) -> str:
        """환경에 따른 WebSocket URL 반환"""
        return self.WS_SANDBOX_URL if self.OKX_SANDBOX else self.WS_URL


@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()