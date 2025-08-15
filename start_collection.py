#!/usr/bin/env python3
"""
BTC-USDT 무기한 선물 실시간 캔들 데이터 수집 시작 스크립트
Gateway API를 통해 자동으로 구독을 시작합니다.
"""

import asyncio
import json
import os
import sys
import time
from typing import List, Optional

import aiohttp
import structlog

# 로깅 설정
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class CollectionStarter:
    """데이터 수집 시작 관리자"""
    
    def __init__(self, gateway_host: str = "localhost", gateway_port: int = 8000):
        self.gateway_host = gateway_host
        self.gateway_port = gateway_port
        self.base_url = f"http://{gateway_host}:{gateway_port}/api/v1"
        
    async def wait_for_gateway(self, max_attempts: int = 30, delay: int = 2) -> bool:
        """Gateway 서비스 시작 대기"""
        logger.info(f"Waiting for Gateway service at {self.base_url}")
        
        for attempt in range(1, max_attempts + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://{self.gateway_host}:{self.gateway_port}/health", 
                                         timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            logger.info(f"Gateway service is ready (attempt {attempt})")
                            return True
            except Exception as e:
                logger.debug(f"Gateway not ready (attempt {attempt}/{max_attempts}): {e}")
                
            if attempt < max_attempts:
                await asyncio.sleep(delay)
        
        logger.error(f"Gateway service not available after {max_attempts} attempts")
        return False
    
    async def subscribe_to_symbols(self, symbols: List[str], timeframes: List[str], 
                                 webhook_url: Optional[str] = None) -> bool:
        """심볼 구독 요청"""
        try:
            subscription_data = {
                "symbols": symbols,
                "timeframes": timeframes,
            }
            
            if webhook_url:
                subscription_data["webhook_url"] = webhook_url
            
            logger.info(f"Subscribing to {symbols} with timeframes {timeframes}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/subscribe",
                    json=subscription_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Subscription successful: {result}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Subscription failed: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False
    
    async def check_subscription_status(self, symbol: str) -> dict:
        """구독 상태 확인"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/status/{symbol}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    
                    if response.status == 200:
                        status = await response.json()
                        return status
                    else:
                        logger.warning(f"Status check failed for {symbol}: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.warning(f"Failed to check status for {symbol}: {e}")
            return {}
    
    async def list_active_subscriptions(self) -> List[dict]:
        """활성 구독 목록 조회"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/subscriptions",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        return result.get("subscriptions", [])
                    else:
                        logger.warning(f"Failed to get subscriptions: {response.status}")
                        return []
                        
        except Exception as e:
            logger.warning(f"Failed to list subscriptions: {e}")
            return []


async def start_btc_usdt_collection(
    symbols: List[str] = None, 
    timeframes: List[str] = None,
    gateway_host: str = "localhost",
    gateway_port: int = 8000,
    wait_for_service: bool = True
):
    """BTC-USDT 무기한 선물 데이터 수집 시작"""
    
    # 기본값 설정
    if symbols is None:
        symbols = ["BTC-USDT-SWAP"]
    
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h", "1d"]
    
    starter = CollectionStarter(gateway_host, gateway_port)
    
    # Gateway 서비스 대기
    if wait_for_service:
        if not await starter.wait_for_gateway():
            logger.error("Gateway service is not available. Please start the services first.")
            return False
    
    # 구독 시작
    success = await starter.subscribe_to_symbols(symbols, timeframes)
    
    if success:
        logger.info("🎉 Collection started successfully!")
        
        # 잠시 대기 후 상태 확인
        await asyncio.sleep(3)
        
        for symbol in symbols:
            status = await starter.check_subscription_status(symbol)
            if status:
                logger.info(f"📊 {symbol} status: {status.get('status', 'unknown')}")
                logger.info(f"📈 Timeframes: {status.get('timeframes', [])}")
            else:
                logger.warning(f"⚠️ Could not get status for {symbol}")
        
        # 활성 구독 목록 표시
        subscriptions = await starter.list_active_subscriptions()
        logger.info(f"📋 Total active subscriptions: {len(subscriptions)}")
        
        for sub in subscriptions:
            logger.info(f"   - {sub.get('symbol')}: {sub.get('timeframes')}")
        
        return True
    else:
        logger.error("❌ Failed to start collection")
        return False


async def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Start BTC-USDT perpetual futures data collection")
    parser.add_argument("--symbols", nargs="+", default=["BTC-USDT-SWAP"], 
                       help="Symbols to collect (default: BTC-USDT-SWAP)")
    parser.add_argument("--timeframes", nargs="+", default=["5m", "15m", "1h", "4h", "1d"],
                       help="Timeframes to collect (default: 5m 15m 1h 4h 1d)")
    parser.add_argument("--gateway-host", default="localhost", 
                       help="Gateway service host (default: localhost)")
    parser.add_argument("--gateway-port", type=int, default=8000,
                       help="Gateway service port (default: 8000)")
    parser.add_argument("--no-wait", action="store_true",
                       help="Don't wait for Gateway service to be ready")
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting BTC-USDT perpetual futures data collection")
    logger.info(f"   Symbols: {args.symbols}")
    logger.info(f"   Timeframes: {args.timeframes}")
    logger.info(f"   Gateway: {args.gateway_host}:{args.gateway_port}")
    
    success = await start_btc_usdt_collection(
        symbols=args.symbols,
        timeframes=args.timeframes,
        gateway_host=args.gateway_host,
        gateway_port=args.gateway_port,
        wait_for_service=not args.no_wait
    )
    
    if success:
        logger.info("✅ Collection setup completed successfully!")
        logger.info("📊 Real-time candle data collection is now running")
        logger.info(f"🌐 Monitor status at: http://{args.gateway_host}:{args.gateway_port}/api/v1/subscriptions")
        sys.exit(0)
    else:
        logger.error("❌ Failed to setup collection")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        sys.exit(1)