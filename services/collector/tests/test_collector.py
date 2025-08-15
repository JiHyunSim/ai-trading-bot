"""Collector Service Tests"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCollectorConfig:
    """Collector configuration tests"""
    
    def test_collector_import(self):
        """Test that collector modules can be imported"""
        try:
            from app.core.config import get_settings
            settings = get_settings()
            assert settings is not None
        except ImportError as e:
            pytest.fail(f"Collector import failed: {e}")
    
    def test_websocket_config(self):
        """Test WebSocket configuration"""
        from app.core.config import get_settings
        
        settings = get_settings()
        assert settings.WS_URL is not None
        assert settings.WS_SANDBOX_URL is not None
        assert "ws" in settings.websocket_url.lower()


class TestOKXClient:
    """OKX WebSocket Client tests"""
    
    def test_client_creation(self):
        """Test OKX client creation"""
        from app.websocket.okx_client import OKXDataCollector
        
        collector = OKXDataCollector("BTC-USDT")
        assert collector.symbol == "BTC-USDT"
        assert collector.is_running is False
        assert collector.is_connected is False
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test OKX client initialization"""
        from app.websocket.okx_client import OKXDataCollector
        
        collector = OKXDataCollector("BTC-USDT")
        
        # Mock Redis client
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_client = AsyncMock()
            mock_redis.return_value = mock_client
            mock_client.ping = AsyncMock()
            
            await collector.initialize()
            
            assert collector.redis_client is not None
            mock_client.ping.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])