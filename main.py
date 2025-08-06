import sys
import os
import asyncio
import logging
from dotenv import load_dotenv

# --- 将项目根目录添加到Python的模块搜索路径中 ---
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 在所有其他导入之前加载环境变量
load_dotenv()

# 导入核心模块
from src.core import ScoutManager, PerformanceOptimizer
from src.telegram import TelegramBot
from src.web import DashboardServer
from src.analysis import MLPredictor # <-- 新增：导入ML预测器

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 配置对象
class Config:
    def __init__(self):
        self.REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.REDIS_POOL_SIZE = 10
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        self.WEB_PORT = int(os.getenv("PORT", 8080))
        self.ML_MODEL_PATH = "ml_models" # <-- 新增：模型路径
        
        self.SCOUT_SETTINGS = {
            "market": {"scan_interval": 30},
        }
        self.ENABLED_SCOUTS = {
            "market": {"enabled": True, "workers": 1},
        }

async def main():
    """主函数，启动所有服务"""
    logger = logging.getLogger("Main")
    
    config = Config()
    if not config.TELEGRAM_TOKEN:
        logger.error("错误：TELEGRAM_TOKEN环境变量未设置！")
        return

    # --- 唤醒机器学习模块 ---
    logger.info("正在初始化机器学习预测器...")
    ml_predictor = MLPredictor(config)
    await ml_predictor.initialize()
    logger.info("✅ 机器学习预测器已加载！")

    optimizer = PerformanceOptimizer()
    await optimizer.optimize_performance()

    # 将 ml_predictor 传递给 ScoutManager
    scout_manager = ScoutManager(config, ml_predictor=ml_predictor)
    await scout_manager.initialize()

    telegram_bot = TelegramBot(
        token=config.TELEGRAM_TOKEN, 
        scout_manager=scout_manager,
        redis_client=scout_manager.redis
    )
    
    dashboard_server = DashboardServer(config, scout_manager)

    try:
        logger.info("🚀 开始启动所有服务...")
        await asyncio.gather(
            scout_manager.start_scouts(config.ENABLED_SCOUTS),
            telegram_bot.initialize(),
            # dashboard_server.start() # 在main.py中不再需要启动web服务
        )
    except Exception as e:
        logger.critical(f"主程序发生严重错误: {e}", exc_info=True)
    finally:
        logger.info("正在关闭所有服务...")
        await scout_manager.stop()
        if telegram_bot.app:
            await telegram_bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("程序被手动中断。")
