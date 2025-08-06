"""
DeFi Scout - 监控DeFi协议机会
"""
import asyncio
from typing import List, Dict, Any
from datetime import datetime
import json
import logging
from web3 import Web3
from decimal import Decimal
from .base_scout import BaseScout
from ..core.scout_manager import OpportunitySignal

logger = logging.getLogger(__name__)

class DeFiScout(BaseScout):
    """DeFi机会扫描器"""
    
    async def _initialize(self):
        """初始化DeFi Scout"""
        self.protocols = self.config.get('protocols', ['uniswap_v3', 'aave', 'compound'])
        self.min_tvl = self.config.get('min_tvl', 100000)  # $100k
        self.min_apy = self.config.get('min_apy', 5.0)  # 5%
        
        # Web3连接
        self.w3_connections = {}
        
        # The Graph端点
        self.subgraph_endpoints = {
            'uniswap_v3': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3',
            'uniswap_v2': 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2',
            'aave': 'https://api.thegraph.com/subgraphs/name/aave/protocol-v3',
            'compound': 'https://api.thegraph.com/subgraphs/name/graphprotocol/compound-v2',
            'sushiswap': 'https://api.thegraph.com/subgraphs/name/sushiswap/exchange'
        }
        
        # 初始化Web3连接
        await self._init_web3_connections()
    
    async def _init_web3_connections(self):
        """初始化Web3连接"""
        rpc_endpoints = {
            'ethereum': 'https://eth.llamarpc.com',
            'bsc': 'https://bsc-dataseed.binance.org',
            'polygon': 'https://polygon-rpc.com',
            'arbitrum': 'https://arb1.arbitrum.io/rpc'
        }
        
        for chain, rpc in rpc_endpoints.items():
            try:
                w3 = Web3(Web3.HTTPProvider(rpc))
                if w3.is_connected():
                    self.w3_connections[chain] = w3
                    logger.info(f"✅ 连接到 {chain} 网络")
            except Exception as e:
                logger.error(f"连接 {chain} 失败: {e}")
    
    async def scan(self) -> List[OpportunitySignal]:
        """扫描DeFi机会"""
        opportunities = []
        
        tasks = [
            self._scan_high_yield_pools(),
            self._scan_new_pools(),
            self._scan_lending_rates(),
            self._scan_liquidation_opportunities(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                opportunities.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"DeFi扫描错误: {result}")
                
        return []
    
    async def _scan_high_yield_pools(self) -> List[OpportunitySignal]:
        """扫描高收益流动性池"""
        opportunities = []
        
        # Uniswap V3查询
        query = """
        {
            pools(
                first: 100,
                orderBy: totalValueLockedUSD,
                orderDirection: desc,
                where: { totalValueLockedUSD_gt: "%s" }
            ) {
                id
                token0 { symbol, name, decimals }
                token1 { symbol, name, decimals }
                feeTier
                liquidity
                totalValueLockedUSD
                volumeUSD
                feesUSD
                poolDayData(first: 7, orderBy: date, orderDirection: desc) {
                    date
                    volumeUSD
                    feesUSD
                    tvlUSD
                }
            }
        }
        """ % self.min_tvl
        
        try:
            async with self.session.post(
                self.subgraph_endpoints['uniswap_v3'],
                json={'query': query}
            ) as response:
                data = await response.json()
                
                if 'data' in data and 'pools' in data['data']:
                    for pool in data['data']['pools']:
                        # 计算7日APY
                        if len(pool['poolDayData']) >= 7:
                            total_fees_7d = sum(float(day['feesUSD']) for day in pool['poolDayData'])
                            avg_tvl_7d = sum(float(day['tvlUSD']) for day in pool['poolDayData']) / 7
                            
                            if avg_tvl_7d > 0:
                                apy_7d = (total_fees_7d / avg_tvl_7d) * 52.14  # 年化
                                
                                if apy_7d >= self.min_apy:
                                    opportunity = self.create_opportunity(
                                        signal_type='high_yield_pool',
                                        symbol=f"{pool['token0']['symbol']}/{pool['token1']['symbol']}",
                                        confidence=min(apy_7d / 50, 0.9),
                                        data={
                                            'protocol': 'Uniswap V3',
                                            'pool_address': pool['id'],
                                            'token0': pool['token0']['symbol'],
                                            'token1': pool['token1']['symbol'],
                                            'fee_tier': int(pool['feeTier']) / 10000,
                                            'tvl_usd': float(pool['totalValueLockedUSD']),
                                            'volume_24h': float(pool['volumeUSD']),
                                            'apy_7d': apy_7d,
                                            'fees_24h': float(pool['feesUSD'])
                                        }
                                    )
                                    opportunities.append(opportunity)
                                    
                                    logger.info(f"💎 高收益池: {pool['token0']['symbol']}/{pool['token1']['symbol']} "
                                               f"APY: {apy_7d:.2f}%")
                                    
        except Exception as e:
            logger.error(f"查询Uniswap失败: {e}")
            
        return opportunities
    
    async def _scan_new_pools(self) -> List[OpportunitySignal]:
        """扫描新创建的池子"""
        opportunities = []
        
        # 查询最近24小时创建的池子
        timestamp_24h_ago = int((datetime.now() - timedelta(days=1)).timestamp())
        
        query = """
        {
            pools(
                first: 50,
                orderBy: createdAtTimestamp,
                orderDirection: desc,
                where: { createdAtTimestamp_gt: "%s" }
            ) {
                id
                token0 { symbol, name }
                token1 { symbol, name }
                feeTier
                liquidity
                totalValueLockedUSD
                createdAtTimestamp
                poolHourData(first: 1, orderBy: periodStartUnix, orderDirection: desc) {
                    volumeUSD
                    feesUSD
                }
            }
        }
        """ % timestamp_24h_ago
        
        try:
            for protocol in ['uniswap_v3', 'sushiswap']:
                if protocol not in self.subgraph_endpoints:
                    continue
                    
                async with self.session.post(
                    self.subgraph_endpoints[protocol],
                    json={'query': query}
                ) as response:
                    data = await response.json()
                    
                    if 'data' in data and 'pools' in data['data']:
                        for pool in data['data']['pools']:
                            tvl = float(pool.get('totalValueLockedUSD', 0))
                            
                            if tvl >= self.min_tvl:
                                opportunity = self.create_opportunity(
                                    signal_type='new_pool',
                                    symbol=f"{pool['token0']['symbol']}/{pool['token1']['symbol']}",
                                    confidence=0.7,  # 新池子风险较高
                                    data={
                                        'protocol': protocol.replace('_', ' ').title(),
                                        'pool_address': pool['id'],
                                        'token0': pool['token0']['symbol'],
                                        'token1': pool['token1']['symbol'],
                                        'tvl_usd': tvl,
                                        'age_hours': (datetime.now().timestamp() - int(pool['createdAtTimestamp'])) / 3600,
                                        'volume_1h': float(pool['poolHourData'][0]['volumeUSD']) if pool.get('poolHourData') else 0
                                    }
                                )
                                opportunities.append(opportunity)
                                
                                logger.info(f"🆕 新池子: {pool['token0']['symbol']}/{pool['token1']['symbol']} "
                                           f"TVL: ${tvl:,.0f}")
                                
        except Exception as e:
            logger.error(f"扫描新池子失败: {e}")
            
        return opportunities
    
    async def _scan_lending_rates(self) -> List[OpportunitySignal]:
        """扫描借贷利率机会"""
        opportunities = []
        
        # Aave V3查询
        query = """
        {
            reserves(first: 50, orderBy: totalLiquidity, orderDirection: desc) {
                id
                symbol
                name
                decimals
                liquidityRate
                variableBorrowRate
                stableBorrowRate
                totalLiquidity
                totalVariableDebt
                totalStableDebt
                utilizationRate
                aToken { id }
            }
        }
        """
        
        try:
            async with self.session.post(
                self.subgraph_endpoints['aave'],
                json={'query': query}
            ) as response:
                data = await response.json()
                
                if 'data' in data and 'reserves' in data['data']:
                    for reserve in data['data']['reserves']:
                        # 转换利率（Ray单位到百分比）
                        supply_apy = float(reserve['liquidityRate']) / 1e25
                        borrow_apy = float(reserve['variableBorrowRate']) / 1e25
                        utilization = float(reserve['utilizationRate']) * 100
                        
                        # 寻找高收益或利率差机会
                        if supply_apy >= self.min_apy or (borrow_apy - supply_apy) > 5:
                            opportunity = self.create_opportunity(
                                signal_type='lending_opportunity',
                                symbol=reserve['symbol'],
                                confidence=min(supply_apy / 20, 0.85),
                                data={
                                    'protocol': 'Aave V3',
                                    'asset': reserve['symbol'],
                                    'supply_apy': supply_apy,
                                    'borrow_apy': borrow_apy,
                                    'utilization_rate': utilization,
                                    'total_liquidity': float(reserve['totalLiquidity']) / (10 ** int(reserve['decimals'])),
                                    'rate_spread': borrow_apy - supply_apy
                                }
                            )
                            opportunities.append(opportunity)
                            
                            logger.info(f"💰 借贷机会: {reserve['symbol']} "
                                       f"存款APY: {supply_apy:.2f}% "
                                       f"借款APY: {borrow_apy:.2f}%")
                                       
        except Exception as e:
            logger.error(f"查询Aave失败: {e}")
            
        return opportunities
    
    async def _scan_liquidation_opportunities(self) -> List[OpportunitySignal]:
        """扫描清算机会"""
        opportunities = []
        
        # 这里可以集成清算机器人API或自己计算
        # 示例：查询Aave中接近清算的头寸
        
        query = """
        {
            users(
                first: 100,
                where: { healthFactor_lt: "1.2", totalCollateralUSD_gt: "10000" }
            ) {
                id
                healthFactor
                totalCollateralUSD
                totalDebtUSD
                positions {
                    asset { symbol }
                    collateral
                    debt
                }
            }
        }
        """
        
        # 注意：实际查询需要更复杂的逻辑
        # 这里仅作示例
        
        return opportunities