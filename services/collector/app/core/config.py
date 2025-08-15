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
    
    # 데이터베이스 설정 (gap detector용)
    DB_HOST: str = Field(default="localhost", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_NAME: str = Field(default="trading_bot", description="Database name")
    DB_USER: str = Field(default="trading_bot", description="Database user")
    DB_PASSWORD: str = Field(default="trading_bot_password", description="Database password")
    
    # OKX API 설정
    OKX_API_KEY: Optional[str] = Field(default=None, description="OKX API key")
    OKX_SECRET_KEY: Optional[str] = Field(default=None, description="OKX secret key")
    OKX_PASSPHRASE: Optional[str] = Field(default=None, description="OKX passphrase")
    OKX_SANDBOX: bool = Field(default=True, description="Use OKX sandbox")
    
    # WebSocket 설정 - 캔들스틱 데이터는 business 엔드포인트 사용
    WS_URL: str = Field(
        default="wss://ws.okx.com:8443/ws/v5/business",
        description="OKX WebSocket Business URL for candlestick data"
    )
    WS_SANDBOX_URL: str = Field(
        default="wss://wspap.okx.com:8443/ws/v5/business?brokerId=9999",
        description="OKX Sandbox WebSocket Business URL"
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
    
    # BTC-USDT 무기한 선물 데이터 수집 설정
    DEFAULT_SYMBOL: str = Field(default="BTC-USDT-SWAP", description="Default symbol for perpetual futures")
    DEFAULT_TIMEFRAMES: str = Field(default="5m,15m,1h,4h,1d", description="Default timeframes to collect")
    AUTO_START: bool = Field(default=True, description="Auto start collection on service startup")
    
    # 심볼 설정 (환경변수로 설정 가능) - 하위 호환성을 위해 유지
    SYMBOL: Optional[str] = Field(default=None, description="Legacy symbol setting")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 추가 필드 허용
    
    @property
    def websocket_url(self) -> str:
        """환경에 따른 WebSocket URL 반환"""
        return self.WS_SANDBOX_URL if self.OKX_SANDBOX else self.WS_URL


@lru_cache()
def get_settings() -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings()