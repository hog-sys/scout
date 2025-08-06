# src/web/dashboard_server.py

import asyncio
import logging
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pathlib import Path
import json
from datetime import datetime, timedelta

# 新增数据库相关导入
from sqlalchemy import select, desc, text
from src.core.database import engine, opportunities_table

logger = logging.getLogger(__name__)

class DashboardServer:
    """Web控制台服务器，数据源为数据库"""

    def __init__(self, config):
        self.config = config
        # 移除 scout_manager
        self.app = FastAPI(title="Crypto Alpha Scout Dashboard")
        self.active_connections: list[WebSocket] = []
        self._register_routes()

    def _register_routes(self):
        """注册API路由"""

        @self.app.get("/", response_class=HTMLResponse)
        async def get_dashboard():
            # (此方法保持不变)
            html_path = Path(__file__).parent.parent / "templates/dashboard.html"
            if html_path.exists():
                return HTMLResponse(content=html_path.read_text(encoding='utf-8'))
            return HTMLResponse(content="<h1>Dashboard not found</h1>")

        @self.app.get("/api/status")
        async def get_status():
            """获取系统状态，从数据库查询"""
            async with engine.connect() as conn:
                total_opps_query = text("SELECT COUNT(id) FROM opportunities;")
                total_opps = await conn.scalar(total_opps_query) or 0
                
                one_hour_ago = datetime.now() - timedelta(hours=1)
                opps_last_hour_query = select(opportunities_table.c.id).where(opportunities_table.c.timestamp > one_hour_ago)
                opps_last_hour_result = await conn.execute(opps_last_hour_query)
                opps_last_hour = len(opps_last_hour_result.fetchall())

            return {
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "total_opportunities": total_opps,
                "opportunities_last_hour": opps_last_hour,
            }

        @self.app.get("/api/opportunities")
        async def get_opportunities(limit: int = 20):
            """获取最近的机会，从数据库查询"""
            query = select(opportunities_table).order_by(desc(opportunities_table.c.timestamp)).limit(limit)
            async with engine.connect() as conn:
                results = await conn.execute(query)
                opportunities = [dict(row) for row in results.mappings().all()]
            return {"opportunities": opportunities}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket连接，轮询数据库推送更新"""
            await websocket.accept()
            self.active_connections.append(websocket)
            try:
                while True:
                    # 获取最新状态和机会
                    status_data = await get_status()
                    opp_data = await get_opportunities(limit=1)
                    
                    # 组合数据并发送
                    payload = {
                        "type": "update",
                        "metrics": status_data,
                        "newOpportunity": opp_data['opportunities'][0] if opp_data['opportunities'] else None
                    }
                    
                    await websocket.send_text(json.dumps(payload, default=str))
                    await asyncio.sleep(5) # 每5秒更新一次
            except WebSocketDisconnect:
                self.active_connections.remove(websocket)
            except Exception as e:
                logger.error(f"WebSocket错误: {e}")
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)

    async def start(self):
        """启动Web服务器"""
        import uvicorn
        config = uvicorn.Config(self.app, host="0.0.0.0", port=self.config.WEB_PORT, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

