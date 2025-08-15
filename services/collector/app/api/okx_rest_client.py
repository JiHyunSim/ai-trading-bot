"""
OKX REST API Client for Historical Data
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import structlog
from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class OKXRestClient:
    """OKX REST API 클라이언트 - 히스토리 데이터 수집용"""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://www.okx.com" if not self.settings.OKX_SANDBOX else "https://www.okx.com"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """API 시그니처 생성"""
        if not all([self.settings.OKX_API_KEY, self.settings.OKX_SECRET_KEY]):
            return ""
            
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(
            bytes(self.settings.OKX_SECRET_KEY, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return mac.digest().hex()
    
    def _get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
        """API 헤더 생성"""
        timestamp = str(int(time.time() * 1000))
        
        headers = {
            'Content-Type': 'application/json',
            'OK-ACCESS-TIMESTAMP': timestamp,
        }
        
        # API 키가 있는 경우에만 인증 헤더 추가
        if self.settings.OKX_API_KEY:
            headers.update({
                'OK-ACCESS-KEY': self.settings.OKX_API_KEY,
                'OK-ACCESS-SIGN': self._generate_signature(timestamp, method, request_path, body),
                'OK-ACCESS-PASSPHRASE': self.settings.OKX_PASSPHRASE or "",
            })
        
        return headers
    
    def _convert_timeframe_to_okx(self, timeframe: str) -> str:
        """타임프레임을 OKX 형식으로 변환"""
        mapping = {
            "1m": "1m",
            "5m": "5m", 
            "15m": "15m",
            "1h": "1H",
            "4h": "4H", 
            "1d": "1D"
        }
        return mapping.get(timeframe, timeframe)
    
    async def get_candlesticks(
        self, 
        inst_id: str, 
        timeframe: str, 
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        캔들스틱 히스토리 데이터 조회
        
        Args:
            inst_id: 거래 상품 ID (e.g., "BTC-USDT-SWAP")
            timeframe: 시간 간격 (1m, 5m, 15m, 1h, 4h, 1d)
            after: 이 시간 이후 데이터 (timestamp ms)
            before: 이 시간 이전 데이터 (timestamp ms)
            limit: 조회할 데이터 개수 (최대 300)
        
        Returns:
            캔들스틱 데이터 리스트
        """
        
        okx_timeframe = self._convert_timeframe_to_okx(timeframe)
        
        # API 엔드포인트
        path = "/api/v5/market/candles"
        
        # 쿼리 파라미터
        params = {
            "instId": inst_id,
            "bar": okx_timeframe,
            "limit": min(limit, 300)  # OKX 최대 300개 제한
        }
        
        if after:
            params["after"] = str(after)
        if before:
            params["before"] = str(before)
        
        # URL 구성
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        request_path = f"{path}?{query_string}"
        url = f"{self.base_url}{request_path}"
        
        try:
            headers = self._get_headers("GET", request_path)
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("code") == "0":
                        candles = data.get("data", [])
                        
                        # 데이터 변환
                        result = []
                        for candle in candles:
                            if len(candle) >= 9:
                                result.append({
                                    "symbol": inst_id,
                                    "timeframe": timeframe,
                                    "timestamp": int(candle[0]),
                                    "open": float(candle[1]),
                                    "high": float(candle[2]),
                                    "low": float(candle[3]),
                                    "close": float(candle[4]),
                                    "volume": float(candle[5]),
                                    "volume_currency": float(candle[6]),
                                    "confirm": True,  # 히스토리 데이터는 항상 확정
                                    "source": "okx_rest_api"
                                })
                        
                        logger.info(
                            "Retrieved historical candles",
                            symbol=inst_id,
                            timeframe=timeframe,
                            count=len(result),
                            after=after,
                            before=before
                        )
                        
                        return result
                    
                    else:
                        logger.error(
                            "OKX API error",
                            code=data.get("code"),
                            message=data.get("msg"),
                            symbol=inst_id,
                            timeframe=timeframe
                        )
                        return []
                
                else:
                    logger.error(
                        "HTTP error",
                        status=response.status,
                        symbol=inst_id,
                        timeframe=timeframe
                    )
                    return []
                    
        except Exception as e:
            logger.error(
                "Failed to fetch candles",
                error=str(e),
                symbol=inst_id,
                timeframe=timeframe
            )
            return []
    
    async def get_candles_range(
        self,
        inst_id: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        특정 시간 범위의 캔들 데이터 조회
        
        Args:
            inst_id: 거래 상품 ID
            timeframe: 시간 간격
            start_time: 시작 시간
            end_time: 종료 시간
        
        Returns:
            캔들스틱 데이터 리스트
        """
        
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)
        
        all_candles = []
        current_after = start_ts
        
        logger.info(
            "Fetching candle range",
            symbol=inst_id,
            timeframe=timeframe,
            start=start_time.isoformat(),
            end=end_time.isoformat()
        )
        
        # OKX API는 시간 역순으로 반환하므로 before/after 로직을 사용
        while current_after < end_ts:
            candles = await self.get_candlesticks(
                inst_id=inst_id,
                timeframe=timeframe,
                after=str(current_after),
                before=str(end_ts),
                limit=300
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            # 다음 배치를 위한 타임스탬프 업데이트
            latest_timestamp = max(candle["timestamp"] for candle in candles)
            if latest_timestamp <= current_after:
                break  # 더 이상 새로운 데이터가 없음
            
            current_after = latest_timestamp + 1
            
            # API 레이트 리미트 방지를 위한 딜레이
            await asyncio.sleep(0.1)
        
        # 시간 순으로 정렬
        all_candles.sort(key=lambda x: x["timestamp"])
        
        logger.info(
            "Completed candle range fetch",
            symbol=inst_id,
            timeframe=timeframe,
            total_candles=len(all_candles)
        )
        
        return all_candles