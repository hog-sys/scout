# config/settings.py

import os
from typing import Dict, Any
from pathlib import Path

class Settings:
    """系统配置"""
    
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent.parent
        
        # --- 核心服务连接 ---
        # 最终修复：直接硬编码在Docker网络中正确的服务地址，
        # 移除环境变量读取，以排除所有配置加载问题。
        self.RABBITMQ_URL = "amqp://user:password@rabbitmq:5672/"
        self.DATABASE_URL = "postgresql+asyncpg://user:password@timescaledb:5432/crypto_scout"
        
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.WEB_PORT = int(os.getenv("WEB_PORT", 8000))
        
        # (其余部分保持不变)
        self.SCOUT_SETTINGS = {
            "market": {"scan_interval": 30},
            "defi": {"scan_interval": 300},
            "contract": {"scan_interval": 120},
            "chain": {"scan_interval": 180},
        }
        self.WEB3_PROVIDERS = {
            "ethereum": "https://eth.llamarpc.com",
            "bsc": "https://bsc-dataseed.binance.org",
        }
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_DIR = self.BASE_DIR / "logs"
        self.LOG_DIR.mkdir(exist_ok=True)
        self.DATA_DIR = self.BASE_DIR / "data"
        self.DATA_DIR.mkdir(exist_ok=True)

settings = Settings()
