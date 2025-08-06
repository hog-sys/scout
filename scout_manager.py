# src/core/scout_manager.py

import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime
import importlib
from pathlib import Path

# 移除不再需要的导入: json, redis, dataclasses

logger = logging.getLogger(__name__)

# OpportunitySignal 类现在在 base_scout.py 中定义，这里不再需要

class ScoutManager:
    """Scout管理器"""

    def __init__(self, config):
        self.config = config
        self.scouts = {}
        self.active_scout_instances = {} # 存储活跃的scout实例
        self.running = False
        
        # 移除进程池和线程池，因为我们的IO密集型任务由asyncio处理
        # 移除Redis相关的初始化

        self.stats = {
            'scouts_started': 0,
            'opportunities_found': 0, # 这个统计将移动到消费者端
            'errors_count': 0,
            'last_scan_time': {}
        }

    async def initialize(self):
        """初始化管理器"""
        logger.info("初始化Scout管理器...")
        # 移除Redis连接逻辑
        await self._load_scout_modules()

    async def _load_scout_modules(self):
        """动态加载Scout模块"""
        # (此方法保持不变)
        scouts_dir = Path(__file__).parent.parent / 'scouts'
        for scout_file in scouts_dir.glob('*_scout.py'):
            if scout_file.name == '__init__.py':
                continue
            module_name = scout_file.stem
            try:
                module = importlib.import_module(f'src.scouts.{module_name}')
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        attr_name.endswith('Scout') and 
                        attr_name != 'BaseScout'):
                        scout_name = attr_name.replace('Scout', '').lower()
                        self.scouts[scout_name] = attr
                        logger.info(f"✅ 加载Scout模块: {scout_name}")
            except Exception as e:
                logger.error(f"❌ 加载Scout模块失败 {module_name}: {e}")

    async def start_scouts(self, scouts_config: Dict):
        """启动指定的Scouts"""
        self.running = True
        tasks = []

        for scout_name, config in scouts_config.items():
            if scout_name in self.scouts and config.get('enabled', True):
                scout_class = self.scouts[scout_name]
                scout_instance = scout_class(self.config.SCOUT_SETTINGS.get(scout_name, {}))
                
                await scout_instance.initialize()
                self.active_scout_instances[scout_name] = scout_instance

                workers = config.get('workers', 1)
                for i in range(workers):
                    task = asyncio.create_task(
                        self._run_scout_worker(scout_name, scout_instance, i)
                    )
                    tasks.append(task)
                
                self.stats['scouts_started'] += workers
                logger.info(f"✅ 启动 {scout_name} Scout ({workers} workers)")
        
        # (监控任务可以暂时保持或简化)
        monitor_task = asyncio.create_task(self._monitor_scouts())
        tasks.append(monitor_task)

    async def _run_scout_worker(self, scout_name: str, scout_instance, worker_id: int):
        """运行单个Scout工作循环"""
        worker_name = f"{scout_name}[{worker_id}]"
        logger.info(f"🏃 Scout {worker_name} 开始工作")

        while self.running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                # 1. 执行扫描，获取机会列表
                opportunities = await scout_instance.scan()
                
                scan_time = asyncio.get_event_loop().time() - start_time
                self.stats['last_scan_time'][worker_name] = scan_time
                
                # 2. 调用实例自己的发布方法
                if opportunities:
                    await scout_instance.publish_opportunities(opportunities)
                
                interval = self.config.SCOUT_SETTINGS.get(scout_name, {}).get('scan_interval', 60)
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"❌ Scout {worker_name} 错误: {e}", exc_info=True)
                self.stats['errors_count'] += 1
                await asyncio.sleep(30) # 错误后稍长休眠

    # _process_opportunity, _is_duplicate, _save_opportunity, _publish_opportunity
    # 这些方法从ScoutManager中移除，它们的职责将由新的消费者服务承担。

    async def _monitor_scouts(self):
        """监控Scout运行状态"""
        # (此方法可以暂时保持不变)
        while self.running:
            await asyncio.sleep(60)
            logger.info(f"📊 状态 - 活跃Scouts: {self.stats['scouts_started']}, 错误: {self.stats['errors_count']}")
            # 可以在这里添加更详细的健康检查

    async def stop(self):
        """停止所有Scouts"""
        logger.info("正在停止Scout管理器...")
        self.running = False
        
        # 优雅地清理所有scout实例
        for scout_instance in self.active_scout_instances.values():
            await scout_instance.cleanup()
        
        logger.info("✅ Scout管理器已停止")

    # get_recent_opportunities 和 save_state 方法也移除，
    # 因为状态和数据现在由消费者和数据库管理。

    