"""
合约Scout - 监控智能合约活动
"""
import asyncio
from typing import List, Dict, Any
from datetime import datetime
from web3 import Web3
import json
import logging
from .base_scout import BaseScout
from ..core.scout_manager import OpportunitySignal

logger = logging.getLogger(__name__)

class ContractScout(BaseScout):
    """智能合约活动扫描器"""
    
    async def _initialize(self):
        """初始化合约Scout"""
        self.chains = self.config.get('chains', ['ethereum', 'bsc'])
        self.min_value_usd = self.config.get('min_value_usd', 10000)
        self.mempool_scan = self.config.get('mempool_scan', False)
        
        # 已知的重要合约地址
        self.known_contracts = {
            'ethereum': {
                'uniswap_v3_router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
                'uniswap_v2_router': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'opensea': '0x00000000006c3852cbEf3e08E8dF289169EdE581',
                'blur': '0x000000000000Ad05Ccc4F10045630fb830B95127'
            }
        }
        
        # 监控的事件签名
        self.event_signatures = {
            'Transfer': '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
            'Swap': '0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822',
            'Mint': '0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f'
        }
    
    async def scan(self) -> List[OpportunitySignal]:
        """扫描合约活动"""
        opportunities = []
        
        tasks = [
            self._scan_new_contracts(),
            self._scan_large_transactions(),
            self._scan_contract_interactions(),
        ]
        
        if self.mempool_scan:
            tasks.append(self._scan_mempool())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                opportunities.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"合约扫描错误: {result}")
                
        return []
    
    async def _scan_new_contracts(self) -> List[OpportunitySignal]:
        """扫描新部署的合约"""
        opportunities = []
        
        for chain, w3 in self.w3_connections.items():
            try:
                # 获取最新区块
                latest_block = w3.eth.block_number
                
                # 获取最近几个区块的交易
                for block_num in range(latest_block - 2, latest_block + 1):
                    block = w3.eth.get_block(block_num, full_transactions=True)
                    
                    for tx in block.transactions:
                        # 合约创建交易的to地址为None
                        if tx.to is None and tx.value > w3.to_wei(0.1, 'ether'):
                            receipt = w3.eth.get_transaction_receipt(tx.hash)
                            
                            if receipt.contractAddress:
                                # 分析合约
                                contract_info = await self._analyze_contract(
                                    w3, receipt.contractAddress, tx
                                )
                                
                                if contract_info['is_interesting']:
                                    opportunity = self.create_opportunity(
                                        signal_type='new_contract',
                                        symbol=f"Contract@{chain}",
                                        confidence=0.7,
                                        data={
                                            'chain': chain,
                                            'address': receipt.contractAddress,
                                            'deployer': tx['from'],
                                            'initial_eth': float(w3.from_wei(tx.value, 'ether')),
                                            'gas_used': receipt.gasUsed,
                                            'block': block_num,
                                            'analysis': contract_info
                                        }
                                    )
                                    opportunities.append(opportunity)
                                    
                                    logger.info(f"📝 新合约部署: {receipt.contractAddress[:10]}... "
                                               f"初始资金: {w3.from_wei(tx.value, 'ether')} ETH")
                                               
            except Exception as e:
                logger.error(f"扫描 {chain} 新合约失败: {e}")
                
        return opportunities
    
    async def _analyze_contract(self, w3: Web3, address: str, tx: Dict) -> Dict:
        """分析合约是否值得关注"""
        analysis = {
            'is_interesting': False,
            'reasons': [],
            'risk_score': 0
        }
        
        try:
            # 获取合约代码
            code = w3.eth.get_code(address)
            code_size = len(code)
            
            # 检查代码大小
            if code_size > 1000:  # 有实质性代码
                analysis['reasons'].append('substantial_code')
                analysis['is_interesting'] = True
                
            # 检查是否有大额初始资金
            if tx.value > w3.to_wei(1, 'ether'):
                analysis['reasons'].append('high_initial_funding')
                analysis['is_interesting'] = True
                
            # 检查部署者历史（这里简化处理）
            deployer_balance = w3.eth.get_balance(tx['from'])
            if deployer_balance > w3.to_wei(10, 'ether'):
                analysis['reasons'].append('wealthy_deployer')
                
        except Exception as e:
            logger.debug(f"分析合约失败: {e}")
            
        return analysis
    
    async def _scan_large_transactions(self) -> List[OpportunitySignal]:
        """扫描大额交易"""
        opportunities = []
        
        for chain, w3 in self.w3_connections.items():
            try:
                latest_block = w3.eth.block_number
                block = w3.eth.get_block(latest_block, full_transactions=True)
                
                for tx in block.transactions:
                    # 检查ETH转账金额
                    eth_value = w3.from_wei(tx.value, 'ether')
                    
                    if eth_value >= 100:  # 100 ETH以上
                        # 检查是否涉及已知合约
                        to_address = tx.to
                        contract_name = None
                        
                        if to_address:
                            for name, addr in self.known_contracts.get(chain, {}).items():
                                if to_address.lower() == addr.lower():
                                    contract_name = name
                                    break
                        
                        opportunity = self.create_opportunity(
                            signal_type='large_transaction',
                            symbol=f"ETH@{chain}",
                            confidence=0.8,
                            data={
                                'chain': chain,
                                'tx_hash': tx.hash.hex(),
                                'from': tx['from'],
                                'to': to_address,
                                'value_eth': float(eth_value),
                                'value_usd': float(eth_value) * 2000,  # 简化：假设ETH=$2000
                                'gas_price': w3.from_wei(tx.gasPrice, 'gwei'),
                                'contract_name': contract_name,
                                'block': latest_block
                            }
                        )
                        opportunities.append(opportunity)
                        
                        logger.info(f"🐋 大额交易: {eth_value:.2f} ETH "
                                   f"{'到 ' + contract_name if contract_name else ''}")
                                   
            except Exception as e:
                logger.error(f"扫描 {chain} 大额交易失败: {e}")
                
        return opportunities
    
    async def _scan_contract_interactions(self) -> List[OpportunitySignal]:
        """扫描重要合约交互"""
        opportunities = []
        
        # 监控特定合约的事件
        for chain, w3 in self.w3_connections.items():
            try:
                latest_block = w3.eth.block_number
                
                # 获取Uniswap等重要合约的事件
                for contract_name, contract_address in self.known_contracts.get(chain, {}).items():
                    if 'uniswap' in contract_name:
                        # 获取Swap事件
                        filter_params = {
                            'fromBlock': latest_block - 10,
                            'toBlock': latest_block,
                            'address': contract_address,
                            'topics': [self.event_signatures.get('Swap')]
                        }
                        
                        try:
                            logs = w3.eth.get_logs(filter_params)
                            
                            for log in logs[-5:]:  # 只处理最近5个
                                # 解析事件（这里简化处理）
                                opportunity = self.create_opportunity(
                                    signal_type='dex_swap',
                                    symbol=f"Swap@{chain}",
                                    confidence=0.6,
                                    data={
                                        'chain': chain,
                                        'contract': contract_name,
                                        'tx_hash': log.transactionHash.hex(),
                                        'block': log.blockNumber,
                                        'log_index': log.logIndex
                                    }
                                )
                                opportunities.append(opportunity)
                                
                        except Exception as e:
                            logger.debug(f"获取 {contract_name} 事件失败: {e}")
                            
            except Exception as e:
                logger.error(f"扫描 {chain} 合约交互失败: {e}")
                
        return opportunities
    
    async def _scan_mempool(self) -> List[OpportunitySignal]:
        """扫描内存池（需要特殊节点支持）"""
        opportunities = []
        
        # 注意：标准RPC通常不支持pending交易
        # 需要使用支持的节点如Alchemy、Infura的特殊端点
        
        logger.info("内存池扫描需要特殊节点支持")
        
        return opportunities