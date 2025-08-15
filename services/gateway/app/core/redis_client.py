"""Redis Client Configuration"""

import redis.asyncio as redis
from app.core.config import get_settings

_redis_client: redis.Redis = None


async def get_redis_client() -> redis.Redis:
    """Redis 클라이언트 인스턴스 반환"""
    global _redis_client
    
    if _redis_client is None:
        settings = get_settings()
        
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            decode_responses=True,
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={},
        )
    
    return _redis_client


async def close_redis_client():
    """Redis 클라이언트 연결 종료"""
    global _redis_client
    
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None