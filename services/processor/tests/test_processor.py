"""Processor Service Tests"""

import pytest
from unittest.mock import AsyncMock, patch


class TestProcessorConfig:
    """Processor configuration tests"""
    
    def test_processor_import(self):
        """Test that processor modules can be imported"""
        try:
            from app.core.config import get_settings
            settings = get_settings()
            assert settings is not None
        except ImportError as e:
            pytest.fail(f"Processor import failed: {e}")
    
    def test_database_config(self):
        """Test database configuration"""
        from app.core.config import get_settings
        
        settings = get_settings()
        assert settings.DB_HOST is not None
        assert settings.DB_PORT > 0
        assert settings.DB_NAME is not None
        assert settings.BATCH_SIZE > 0


class TestBatchProcessor:
    """Batch processor tests"""
    
    def test_processor_creation(self):
        """Test batch processor creation"""
        from app.processors.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        assert processor.settings is not None
        assert processor.is_running is False
    
    def test_timeframe_parsing(self):
        """Test timeframe parsing"""
        from app.processors.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        
        assert processor.parse_timeframe_seconds("1m") == 60
        assert processor.parse_timeframe_seconds("5m") == 300
        assert processor.parse_timeframe_seconds("1H") == 3600
        assert processor.parse_timeframe_seconds("1D") == 86400
        assert processor.parse_timeframe_seconds("invalid") == 60  # default
    
    @pytest.mark.asyncio
    async def test_processor_initialization(self):
        """Test processor initialization with mocked dependencies"""
        from app.processors.batch_processor import BatchProcessor
        
        processor = BatchProcessor()
        
        # Mock Redis and PostgreSQL
        with patch('redis.asyncio.Redis') as mock_redis, \
             patch('asyncpg.create_pool') as mock_pool:
            
            mock_redis_client = AsyncMock()
            mock_redis.return_value = mock_redis_client
            mock_redis_client.ping = AsyncMock()
            
            mock_db_pool = AsyncMock()
            mock_pool.return_value = mock_db_pool
            
            # Mock database schema verification
            with patch.object(processor, 'verify_database_schema', AsyncMock()):
                await processor.initialize()
                
                assert processor.redis_client is not None
                assert processor.db_pool is not None
                mock_redis_client.ping.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])