import asyncio
import sys
import os
from pathlib import Path
import logging
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.scout_manager import ScoutManager
from src.core.performance_optimizer import PerformanceOptimizer
from src.telegram.bot import TelegramBot
from src.analysis.realtime_analyzer import RealtimeAnalyzer
from src.web.dashboard_server import DashboardServer
from config.high_performance import HighPerformanceConfig

# 配置彩色日志（Windows）
import colorama
colorama.init()

class CryptoScoutPro:
    
    def __init__(self):
        self.config = HighPerformanceConfig()
        self.setup_logging()
        self.optimizer = PerformanceOptimizer()
        
        # 利用多核CPU
        self.cpu_count = mp.cpu_count()
        self.process_pool = ProcessPoolExecutor(max_workers=self.cpu_count - 1)
        self.thread_pool = ThreadPoolExecutor(max_workers=self.cpu_count * 2)
        
        self.logger.info(f"系统初始化 - CPU核心: {self.cpu_count}")
        
    def setup_logging(self):
        """配置日志系统"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # 控制台日志（彩色）
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        
        # 文件日志
        file_handler = logging.FileHandler(
            f'logs/crypto_scout_{datetime.now().strftime("%Y%m%d")}.log'
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        
        self.logger = logging.getLogger('CryptoScout')
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        self.logger.setLevel(logging.INFO)
    
    async def start(self):
        """启动所有服务"""
        self.logger.info("=" * 60)
        self.logger.info("   Crypto Alpha Scout - 高性能版")
        self.logger.info("=" * 60)
        
        # 系统优化
        await self.optimizer.optimize_windows_performance()
        
        # 启动Redis（如果安装了）
        await self.start_redis()
        
        # 初始化数据库
        await self.init_database()
        
        # 启动核心服务
        tasks = [
            self.start_scout_manager(),
            self.start_telegram_bot(),
            self.start_analyzer(),
            self.start_web_dashboard(),
            self.start_monitoring()
        ]
        
        # 并发启动所有服务
        await asyncio.gather(*tasks)
        
        self.logger.info("✅ 所有服务启动完成！")
        self.logger.info(f"📊 Web控制台: http://localhost:{self.config.WEB_PORT}")
        self.logger.info(f"📈 性能监控: http://localhost:{self.config.METRICS_PORT}")
        
    async def start_scout_manager(self):
        """启动Scout管理器"""
        self.scout_manager = ScoutManager(
            config=self.config,
            process_pool=self.process_pool,
            thread_pool=self.thread_pool
        )
        
        # 启动所有Scout
        scouts_config = {
            'market': {
                'class': 'MarketScout',
                'workers': 4,  # 多进程
                'priority': 'high'
            },
            'defi': {
                'class': 'DeFiScout',
                'workers': 2,
                'priority': 'medium'
            },
            'contract': {
                'class': 'ContractScout',
                'workers': 2,
                'priority': 'medium'
            },
            'chain': {
                'class': 'ChainScout',
                'workers': 3,
                'priority': 'high'
            }
        }
        
        await self.scout_manager.start_scouts(scouts_config)
        
    async def start_redis(self):
        """启动本地Redis服务"""
        import subprocess
        
        try:
            # 检查Redis是否已运行
            import redis
            r = redis.Redis()
            r.ping()
            self.logger.info("✅ Redis已在运行")
        except:
            self.logger.info("启动Redis服务...")
            # 启动Redis服务器
            redis_path = r"C:\Program Files\Redis\redis-server.exe"
            if os.path.exists(redis_path):
                subprocess.Popen([redis_path], 
                               creationflags=subprocess.CREATE_NO_WINDOW)
                await asyncio.sleep(2)
                self.logger.info("✅ Redis启动成功")
            else:
                self.logger.warning("⚠️ 未找到Redis，使用内存缓存")
    
    async def init_database(self):
        """初始化数据库"""
        try:
            # 确保数据目录存在
            data_dir = Path('data')
            data_dir.mkdir(exist_ok=True)
            
            # 初始化SQLite数据库
            import sqlite3
            db_path = data_dir / 'crypto_scout.db'
            conn = sqlite3.connect(str(db_path))
            
            # 创建必要的表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    scout_name TEXT,
                    signal_type TEXT,
                    symbol TEXT,
                    confidence REAL,
                    data TEXT,
                    timestamp TEXT,
                    expires_at TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    opportunities_found INTEGER,
                    errors_count INTEGER,
                    memory_usage REAL,
                    cpu_usage REAL
                )
            ''')
            
            conn.commit()
            conn.close()
            
            self.logger.info("✅ 数据库初始化完成")
            
        except Exception as e:
            self.logger.error(f"数据库初始化失败: {e}")
            self.logger.warning("⚠️ 数据库初始化失败，将使用内存模式")
    
    async def start_telegram_bot(self):
        """启动Telegram机器人"""
        try:
            if not self.config.TELEGRAM_BOT_TOKEN:
                self.logger.warning("⚠️ 未设置Telegram机器人TOKEN，跳过启动。")
                return
            self.telegram_bot = TelegramBot(token=self.config.TELEGRAM_BOT_TOKEN, scout_manager=self.scout_manager)
            await self.telegram_bot.initialize()
            self.logger.info("✅ Telegram机器人启动成功")
        except Exception as e:
            self.logger.error(f"启动Telegram机器人失败: {e}")
    
    async def start_analyzer(self):
        """启动实时分析器"""
        try:
            self.realtime_analyzer = RealtimeAnalyzer(self.config)
            await self.realtime_analyzer.initialize()
            self.logger.info("✅ 实时分析器启动成功")
        except Exception as e:
            self.logger.error(f"启动实时分析器失败: {e}")
    
    async def start_web_dashboard(self):
        """启动Web控制台"""
        try:
            self.dashboard_server = DashboardServer(
                config=self.config,
                scout_manager=self.scout_manager
            )
            await self.dashboard_server.start()
            self.logger.info("✅ Web控制台启动成功")
        except Exception as e:
            self.logger.error(f"启动Web控制台失败: {e}")
            self.logger.warning("⚠️ Web控制台启动失败，继续运行其他服务")
    
    async def start_monitoring(self):
        """启动系统监控"""
        try:
            # 启动性能监控任务
            asyncio.create_task(self._monitor_performance())
            self.logger.info("✅ 系统监控已启动")
        except Exception as e:
            self.logger.error(f"启动系统监控失败: {e}")
    
    async def _monitor_performance(self):
        """监控系统性能"""
        while True:
            try:
                # 获取系统信息
                system_info = self.optimizer.get_system_info()
                
                # 检查关键指标
                memory_usage = (system_info['memory_total'] - system_info['memory_available']) / system_info['memory_total'] * 100
                disk_usage = system_info['disk_usage']
                
                # 记录性能指标
                self.logger.info(f"📊 系统性能 - CPU: {system_info['cpu_freq']:.0f}MHz, "
                               f"内存: {memory_usage:.1f}%, 磁盘: {disk_usage:.1f}%")
                
                # 检查警告条件
                if memory_usage > 80:
                    self.logger.warning("⚠️ 内存使用率过高")
                if disk_usage > 90:
                    self.logger.warning("⚠️ 磁盘使用率过高")
                
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                self.logger.error(f"性能监控错误: {e}")
                await asyncio.sleep(30)
    
    async def run_forever(self):
        """主运行循环"""
        await self.start()
        
        # 设置Ctrl+C处理
        import signal
        
        def signal_handler(sig, frame):
            self.logger.info("\n正在优雅关闭...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # 保持运行
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
    
    async def shutdown(self):
        """优雅关闭"""
        self.logger.info("关闭进程池...")
        self.process_pool.shutdown(wait=True)
        self.thread_pool.shutdown(wait=True)
        
        self.logger.info("保存状态...")
        await self.scout_manager.save_state()
        
        self.logger.info("✅ 程序已安全退出")
        sys.exit(0)

# Windows特定优化
if sys.platform == 'win32':
    # 使用更快的事件循环
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 多进程支持
    mp.set_start_method('spawn', force=True)

def main():
    """程序入口"""
    app = CryptoScoutPro()
    asyncio.run(app.run_forever())

if __name__ == "__main__":
    main()