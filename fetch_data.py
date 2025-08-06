import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
import time
import os
from typing import List, Dict, Optional

# ==============================================================================
# 配置区域
# ==============================================================================

# --- 请在这里填入您的所有API密钥 ---

# 币安 (Binance) - 拉取公开K线数据通常不需要密钥
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# KuCoin - 拉取公开K线数据通常不需要密钥
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY", "")
KUCOIN_SECRET_KEY = os.getenv("KUCOIN_SECRET_KEY", "")

# CoinGecko - 免费API通常不需要密钥，但填入后可提高频率限制
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "CG-AxHkx6MjdpTP23XUPx78y2fD")

# Polygon (PolygonScan) - 用于拉取链上数据
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "m82LedhXvSDQ0nrfUB8UHMVdIVZSyZbv")

# AlphaVantage
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "S9LCG1AG28EMDVNX")


# --- 数据拉取设置 ---
# 全局日期范围，适用于没有限制的数据源 (如 Binance)
START_DATE = "2022-01-01"
END_DATE = datetime.now().strftime("%Y-%m-%d") # 结束日期为今天

# --- 更新：将交易对列表扩展到10个 ---
TARGET_PAIRS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "DOGE/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "MATIC/USDT"
]
TIMEFRAME = "1h"  # 1分钟: '1m', 1小时: '1h', 1天: '1d'

# 数据保存路径
SAVE_PATH = "historical_data"

# API请求设置
REQUEST_TIMEOUT = 20  # 秒
RATE_LIMIT_DELAY = 1.2  # 秒, CoinGecko免费API限制较高，增加延迟

# ==============================================================================
# 数据拉取器基类
# ==============================================================================

class BaseDataFetcher:
    """所有数据拉取器的基类"""
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch(self, symbol: str, start_date: str, end_date: str, timeframe: str) -> Optional[pd.DataFrame]:
        """拉取数据的主方法"""
        raise NotImplementedError

    def _structure_dataframe_ohlcv(self, data: List[List]) -> pd.DataFrame:
        """将 [时间戳, 开, 高, 低, 收, 量, ...] 格式的数据构建为标准DataFrame"""
        processed_data = [row[:6] for row in data]
        
        df = pd.DataFrame(processed_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df.astype(float)
        return df

# ==============================================================================
# 币安 (Binance) 数据拉取器
# ==============================================================================

class BinanceFetcher(BaseDataFetcher):
    """从币安拉取历史K线数据"""
    BASE_URL = "https://api.binance.com/api/v3/klines"

    async def fetch(self, symbol: str, start_date: str, end_date: str, timeframe: str) -> Optional[pd.DataFrame]:
        symbol_formatted = symbol.replace("/", "")
        start_ts = int(datetime.fromisoformat(start_date).timestamp() * 1000)
        end_ts = int(datetime.fromisoformat(end_date).timestamp() * 1000)
        
        all_data = []
        current_ts = start_ts

        print(f"开始从币安拉取 {symbol} 的数据...")
        while current_ts < end_ts:
            params = {
                "symbol": symbol_formatted,
                "interval": timeframe,
                "startTime": current_ts,
                "limit": 1000
            }
            try:
                async with self.session.get(self.BASE_URL, params=params, timeout=REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data:
                            break
                        all_data.extend(data)
                        current_ts = data[-1][0] + 1
                        print(f"  已拉取到 {pd.to_datetime(current_ts, unit='ms')}...")
                        await asyncio.sleep(0.2) # 币安限制较低
                    else:
                        print(f"  币安API错误: {response.status} - {await response.text()}")
                        break
            except Exception as e:
                print(f"  发生未知错误: {e}")
                break
        
        if all_data:
            return self._structure_dataframe_ohlcv(all_data)
        return None

# ==============================================================================
# CoinGecko 数据拉取器 (新增)
# ==============================================================================
class CoinGeckoFetcher(BaseDataFetcher):
    """从 CoinGecko 拉取历史K线数据"""
    BASE_URL = "https://api.coingecko.com/api/v3/coins/{id}/market_chart/range"

    # --- 更新：为新的交易对添加ID映射 ---
    SYMBOL_TO_ID = {
        "BTC/USDT": "bitcoin",
        "ETH/USDT": "ethereum",
        "BNB/USDT": "binancecoin",
        "SOL/USDT": "solana",
        "XRP/USDT": "ripple",
        "DOGE/USDT": "dogecoin",
        "ADA/USDT": "cardano",
        "AVAX/USDT": "avalanche-2",
        "LINK/USDT": "chainlink",
        "MATIC/USDT": "matic-network",
    }

    async def fetch(self, symbol: str, start_date: str, end_date: str, timeframe: str) -> Optional[pd.DataFrame]:
        coin_id = self.SYMBOL_TO_ID.get(symbol)
        if not coin_id:
            print(f"CoinGecko 不支持 {symbol} 或未在 SYMBOL_TO_ID 中定义")
            return None

        # --- 内部日期修正：只为CoinGecko计算最近一年的日期 ---
        cg_end_date = datetime.now()
        cg_start_date = cg_end_date - timedelta(days=360)
        start_ts = int(cg_start_date.timestamp())
        end_ts = int(cg_end_date.timestamp())

        print(f"开始从 CoinGecko 拉取 {symbol} ({coin_id}) 的数据 (最近360天)...")
        url = self.BASE_URL.format(id=coin_id)
        params = {
            "vs_currency": "usd",
            "from": start_ts,
            "to": end_ts
        }
        try:
            async with self.session.get(url, params=params, timeout=REQUEST_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get('prices'):
                        return None
                    
                    df = pd.DataFrame(data['prices'], columns=['timestamp', 'price'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    ohlc = df['price'].resample('1h').ohlc()
                    volume = pd.DataFrame(data['total_volumes'], columns=['timestamp', 'volume'])
                    volume['timestamp'] = pd.to_datetime(volume['timestamp'], unit='ms')
                    volume.set_index('timestamp', inplace=True)
                    volume = volume['volume'].resample('1h').sum()

                    final_df = ohlc.join(volume).dropna()
                    print(f"  CoinGecko 数据处理完成，共 {len(final_df)} 条记录")
                    return final_df
                else:
                    print(f"  CoinGecko API 错误: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            print(f"  从 CoinGecko 拉取时发生错误: {e}")
            return None

# ==============================================================================
# Polygon 链上数据拉取器 (框架)
# ==============================================================================
class PolygonFetcher(BaseDataFetcher):
    """从 PolygonScan 拉取链上数据 (这是一个示例框架)"""
    BASE_URL = "https://api.polygonscan.com/api"

    async def fetch_transactions(self, address: str):
        print(f"\n--- Polygon 链上数据拉取功能说明 ---")
        print("Polygon API 用于获取链上数据，如账户交易、代币转账等，而不是K线。")
        print("实现这个功能会更复杂，需要解析交易数据。")
        print("我们已经为您预留好了位置，未来可以扩展此功能。")
        return None

# ==============================================================================
# 主程序
# ==============================================================================

async def main():
    """主函数，协调所有数据拉取任务"""
    if not os.path.exists(SAVE_PATH):
        os.makedirs(SAVE_PATH)

    async with aiohttp.ClientSession() as session:
        fetchers = {
            "binance": BinanceFetcher(session),
            "coingecko": CoinGeckoFetcher(session),
        }

        for pair in TARGET_PAIRS:
            for source_name, fetcher in fetchers.items():
                print(f"\n--- 使用 {source_name.upper()} 拉取 {pair} ---")
                # 所有 fetcher 都接收全局的 START_DATE 和 END_DATE
                # 但 CoinGeckoFetcher 会在内部进行修正
                df = await fetcher.fetch(pair, START_DATE, END_DATE, TIMEFRAME)
                
                if df is not None and not df.empty:
                    filename = f"{pair.replace('/', '_')}_{source_name}_{TIMEFRAME}.csv"
                    filepath = os.path.join(SAVE_PATH, filename)
                    df.to_csv(filepath)
                    print(f"✅ 数据成功保存到: {filepath}")
                else:
                    print(f"❌ 未能从 {source_name.upper()} 获取 {pair} 的数据")
        
        polygon_fetcher = PolygonFetcher(session)
        await polygon_fetcher.fetch_transactions("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")


if __name__ == "__main__":
    start_time = time.time()
    asyncio.run(main())
    end_time = time.time()
    print(f"\n🎉 所有任务完成，总耗时: {end_time - start_time:.2f} 秒")
