# src/core/messaging.py
import asyncio
import json
import logging
from typing import Dict, Any

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from aio_pika.pool import Pool

logger = logging.getLogger(__name__)

class Publisher:
    """处理到RabbitMQ的消息发布"""

    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self.connection_pool: Pool = Pool(self.get_connection, max_size=5)
        self.channel_pool: Pool = Pool(self.get_channel, max_size=20)
        logger.info("消息发布器已初始化")

    async def get_connection(self) -> AbstractRobustConnection:
        """获取一个RabbitMQ连接"""
        return await aio_pika.connect_robust(self.amqp_url)

    async def get_channel(self) -> aio_pika.Channel:
        """从连接池中获取一个通道"""
        async with self.connection_pool.acquire() as connection:
            return await connection.channel()

    async def publish(self, queue_name: str, message_body: Dict[str, Any]):
        """
        发布一条消息到指定的队列。

        :param queue_name: 目标队列的名称。
        :param message_body: 要发送的消息体 (一个字典)。
        """
        async with self.channel_pool.acquire() as channel:
            try:
                # 声明一个持久化的队列，确保RabbitMQ重启后队列依然存在
                queue = await channel.declare_queue(
                    queue_name,
                    durable=True
                )

                # 将字典转换为JSON字符串
                body = json.dumps(message_body, default=str).encode()

                # 创建一个持久化的消息
                message = aio_pika.Message(
                    body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                )

                # 发送消息
                await channel.default_exchange.publish(
                    message,
                    routing_key=queue.name
                )
                # logger.debug(f"成功发送消息到队列 '{queue_name}'")

            except Exception as e:
                logger.error(f"发送消息到队列 '{queue_name}' 失败: {e}", exc_info=True)

    async def close(self):
        """关闭所有连接和通道"""
        await self.channel_pool.close()
        await self.connection_pool.close()
        logger.info("消息发布器连接已关闭")

