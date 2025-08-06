# src/core/database.py
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy import (
    Table, MetaData, Column, Text, Float, DateTime, JSON, text
)
# 导入 asyncpg 的特定异常
from asyncpg.exceptions import ConnectionDoesNotExistError, CannotConnectNowError

from config.settings import settings

logger = logging.getLogger(__name__)

# 创建一个异步数据库引擎
try:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20
    )
    logger.info("✅ 数据库引擎创建成功")
except Exception as e:
    logger.critical(f"❌ 创建数据库引擎失败: {e}")
    engine = None

# MetaData 对象用于存放所有表结构信息
metadata = MetaData()

# 定义 'opportunities' 表
opportunities_table = Table(
    'opportunities',
    metadata,
    # 修复：将主键改为 (id, timestamp) 的复合主键
    # 优化：根据数据库建议，将 String 改为 Text
    Column('id', Text, primary_key=True),
    Column('scout_name', Text, index=True),
    Column('signal_type', Text, index=True),
    Column('symbol', Text, index=True),
    Column('confidence', Float),
    Column('data', JSON),
    Column('timestamp', DateTime(timezone=True), primary_key=True),
    Column('expires_at', DateTime(timezone=True), nullable=True)
)

async def create_tables():
    """连接到数据库并创建所有定义的表，增加了重试逻辑"""
    if not engine:
        logger.error("数据库引擎未初始化，无法创建表。")
        return

    max_retries = 12
    retry_delay = 10

    for attempt in range(max_retries):
        try:
            async with engine.connect() as conn:
                logger.info("数据库连接测试成功，开始设置表...")
                await conn.run_sync(metadata.create_all)
                logger.info("✅ 数据库表创建完成（如果不存在的话）。")

                is_hypertable = await conn.scalar(
                    text("SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'opportunities'")
                )
                if not is_hypertable:
                    await conn.execute(
                        text("SELECT create_hypertable('opportunities', 'timestamp');")
                    )
                    logger.info("✅ 'opportunities' 表已成功转换为TimescaleDB超表。")
                else:
                    logger.info("ℹ️ 'opportunities' 表已经是超表。")
            
            logger.info("✅ 数据库连接成功并完成表设置。")
            return

        except (OperationalError, ConnectionDoesNotExistError, CannotConnectNowError, ConnectionResetError) as e:
            if attempt + 1 < max_retries:
                 logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries})，可能正在启动中。将在 {retry_delay} 秒后重试...")
                 await asyncio.sleep(retry_delay)
            else:
                logger.critical(f"在 {max_retries} 次尝试后，仍无法连接到数据库。错误: {e}")
                raise
        except Exception as e:
            logger.critical(f"创建表时发生未知错误: {e}")
            raise

    raise ConnectionError("在所有重试后，仍无法连接到数据库。请检查Docker容器是否正常运行。")


