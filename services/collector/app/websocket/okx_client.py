"""OKX WebSocket Client Implementation"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as redis
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class OKXDataCollector:
    """OKX WebSocket 데이터 컬렉터"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.settings = get_settings()
        self.websocket = None
        self.redis_client = None
        self.is_running = False
        self.is_connected = False
        self.reconnect_count = 0
        self.last_reconnect = None
        self.start_time = None
        self.message_count = 0
        self.error_count = 0
        self.subscribed_channels = []
        
        # 재연결 설정
        self.reconnect_delay = self.settings.INITIAL_RECONNECT_DELAY
        
        logger.info(f"Initialized OKX collector for {symbol}")
    
    async def initialize(self):
        """컬렉터 초기화"""
        try:
            # Redis 클라이언트 초기화
            self.redis_client = redis.Redis(
                host=self.settings.REDIS_HOST,
                port=self.settings.REDIS_PORT,
                db=self.settings.REDIS_DB,
                password=self.settings.REDIS_PASSWORD,
                decode_responses=True,
                retry_on_timeout=True
            )
            
            # Redis 연결 테스트
            await self.redis_client.ping()
            logger.info(f"Redis connection established for {self.symbol}")
            
            self.start_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Failed to initialize collector for {self.symbol}", error=str(e))
            raise
    
    async def connect_websocket(self):
        """WebSocket 연결"""
        try:
            logger.info(f"Connecting to OKX WebSocket for {self.symbol}")
            
            self.websocket = await websockets.connect(
                self.settings.websocket_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.is_connected = True
            logger.info(f"WebSocket connected for {self.symbol}")
            
            # 연결 상태 업데이트
            await self.update_status("connected")
            
        except Exception as e:
            self.is_connected = False
            logger.error(f"WebSocket connection failed for {self.symbol}", error=str(e))
            raise
    
    async def subscribe_channels(self, timeframes: List[str] = None):
        """채널 구독"""
        if not self.websocket or not self.is_connected:
            raise Exception("WebSocket not connected")
        
        if timeframes is None:
            timeframes = ["1m", "5m", "1H"]  # 기본 시간프레임
        
        try:
            # 구독 메시지 생성
            subscription_args = []
            for timeframe in timeframes:
                channel = f"candle{timeframe}"
                subscription_args.append({
                    "channel": channel,
                    "instId": self.symbol
                })
            
            subscribe_msg = {
                "op": "subscribe",
                "args": subscription_args
            }
            
            # 구독 메시지 전송
            await self.websocket.send(json.dumps(subscribe_msg))
            
            self.subscribed_channels = [f"candle{tf}" for tf in timeframes]
            
            logger.info(
                f"Subscribed to channels for {self.symbol}",
                timeframes=timeframes,
                channels=self.subscribed_channels
            )
            
        except Exception as e:
            logger.error(f"Failed to subscribe channels for {self.symbol}", error=str(e))
            raise
    
    async def process_message(self, message: str):
        """수신 메시지 처리"""
        try:
            data = json.loads(message)
            
            # 구독 응답 처리
            if data.get('event') == 'subscribe':
                logger.info(f"Subscription confirmed for {self.symbol}", channel=data.get('arg'))
                return
            
            # 에러 응답 처리
            if data.get('event') == 'error':
                logger.error(f"WebSocket error for {self.symbol}", error=data)
                self.error_count += 1
                return
            
            # 캔들 데이터 처리
            if 'data' in data and data['data']:
                await self.process_candle_data(data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message for {self.symbol}", error=str(e), message=message[:200])
            self.error_count += 1
        except Exception as e:
            logger.error(f"Failed to process message for {self.symbol}", error=str(e))
            self.error_count += 1
    
    async def process_candle_data(self, data: Dict):
        """캔들 데이터 처리 및 Redis 큐 전송"""
        try:
            channel_info = data.get('arg', {})
            candle_data_list = data.get('data', [])
            
            for candle_data in candle_data_list:
                if len(candle_data) < 9:
                    logger.warning(f"Invalid candle data format for {self.symbol}", data=candle_data)
                    continue
                
                processed_data = {
                    "symbol": self.symbol,
                    "timeframe": channel_info.get('channel', '').replace('candle', ''),
                    "timestamp": int(candle_data[0]),
                    "open": float(candle_data[1]),
                    "high": float(candle_data[2]),
                    "low": float(candle_data[3]),
                    "close": float(candle_data[4]),
                    "volume": float(candle_data[5]),
                    "volume_currency": float(candle_data[6]),
                    "confirm": candle_data[8] == "1",
                    "received_at": datetime.utcnow().isoformat(),
                    "source": "okx_websocket"
                }
                
                # Redis 큐에 전송
                await self.redis_client.lpush(
                    "candle_data_queue",
                    json.dumps(processed_data)
                )
                
                self.message_count += 1
                
                logger.debug(
                    f"Processed candle data for {self.symbol}",
                    timeframe=processed_data['timeframe'],
                    close=processed_data['close'],
                    confirm=processed_data['confirm']
                )
                
        except Exception as e:
            logger.error(f"Failed to process candle data for {self.symbol}", error=str(e))
            self.error_count += 1
    
    async def listen_messages(self):
        """메시지 수신 루프"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break
                await self.process_message(message)
                
        except ConnectionClosed:
            logger.warning(f"WebSocket connection closed for {self.symbol}")
            self.is_connected = False
        except ConnectionClosedError as e:
            logger.error(f"WebSocket connection closed with error for {self.symbol}", error=str(e))
            self.is_connected = False
        except ConnectionClosedOK:
            logger.info(f"WebSocket connection closed normally for {self.symbol}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"WebSocket message listening failed for {self.symbol}", error=str(e))
            self.is_connected = False
    
    async def update_status(self, status: str):
        """상태 업데이트"""
        try:
            status_data = {
                "symbol": self.symbol,
                "status": status,
                "is_connected": self.is_connected,
                "reconnect_count": self.reconnect_count,
                "last_reconnect": self.last_reconnect.isoformat() if self.last_reconnect else None,
                "message_count": self.message_count,
                "error_count": self.error_count,
                "subscribed_channels": self.subscribed_channels,
                "uptime_seconds": int((datetime.utcnow() - self.start_time).total_seconds()) if self.start_time else 0,
                "last_update": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set(
                f"status:{self.symbol}",
                json.dumps(status_data),
                ex=300  # 5분 TTL
            )
            
        except Exception as e:
            logger.error(f"Failed to update status for {self.symbol}", error=str(e))
    
    async def get_status(self) -> Dict:
        """현재 상태 반환"""
        return {
            "symbol": self.symbol,
            "status": "connected" if self.is_connected else "disconnected",
            "is_connected": self.is_connected,
            "reconnect_count": self.reconnect_count,
            "last_reconnect": self.last_reconnect.isoformat() if self.last_reconnect else None,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "subscribed_channels": self.subscribed_channels,
            "uptime_seconds": int((datetime.utcnow() - self.start_time).total_seconds()) if self.start_time else 0,
            "last_update": datetime.utcnow().isoformat()
        }
    
    async def run(self):
        """메인 실행 루프"""
        self.is_running = True
        
        while self.is_running:
            try:
                # WebSocket 연결
                await self.connect_websocket()
                
                # 기본 채널 구독
                await self.subscribe_channels()
                
                # 연결 성공 시 재연결 딜레이 리셋
                self.reconnect_delay = self.settings.INITIAL_RECONNECT_DELAY
                
                # 메시지 수신 시작
                await self.listen_messages()
                
            except Exception as e:
                logger.error(f"WebSocket error for {self.symbol}", error=str(e))
                
                # 연결 실패 상태 업데이트
                await self.update_status("disconnected")
                self.error_count += 1
                
            finally:
                # WebSocket 연결 정리
                if self.websocket:
                    try:
                        await self.websocket.close()
                    except:
                        pass
                    self.websocket = None
                
                self.is_connected = False
            
            # 재연결 로직
            if self.is_running:
                self.reconnect_count += 1
                self.last_reconnect = datetime.utcnow()
                
                logger.info(
                    f"Attempting to reconnect {self.symbol}",
                    attempt=self.reconnect_count,
                    delay=self.reconnect_delay
                )
                
                await asyncio.sleep(self.reconnect_delay)
                
                # 지수 백오프
                self.reconnect_delay = min(
                    self.reconnect_delay * 2,
                    self.settings.MAX_RECONNECT_DELAY
                )
    
    async def stop(self):
        """컬렉터 중지"""
        logger.info(f"Stopping collector for {self.symbol}")
        
        self.is_running = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None
        
        if self.redis_client:
            try:
                await self.update_status("stopped")
                await self.redis_client.close()
            except:
                pass
        
        logger.info(f"Collector stopped for {self.symbol}")