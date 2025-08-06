import pandas as pd
import os
from typing import List, Dict, Optional
import time

# ==============================================================================
# 配置区域
# ==============================================================================

# 读取和保存文件的路径
DATA_PATH = "historical_data"
OUTPUT_FILE = "backtest_opportunities.csv"

# 回测参数
ARBITRAGE_THRESHOLD = 0.001  # 0.1%的利润阈值，触发机会记录
FEE_RATE = 0.001             # 假设双边交易手续费为0.1%
FUTURE_LOOKAHEAD = 1         # 向前看1个时间单位(小时)来判断机会是否成功

# ==============================================================================
# 数据加载与预处理
# ==============================================================================

def load_and_prepare_data(data_path: str, pairs: List[str]) -> Dict[str, pd.DataFrame]:
    """加载所有CSV文件，并按交易对合并数据"""
    all_data = {}
    for pair in pairs:
        pair_files = [f for f in os.listdir(data_path) if f.startswith(pair.replace('/', '_')) and f.endswith('.csv')]
        if not pair_files:
            continue

        df_list = []
        for file in pair_files:
            source = file.split('_')[-2] # e.g., 'binance' or 'coingecko'
            filepath = os.path.join(data_path, file)
            df = pd.read_csv(filepath, index_col='timestamp', parse_dates=True)
            # 为列名添加来源后缀，以便区分
            df.rename(columns=lambda col: f"{col}_{source}", inplace=True)
            df_list.append(df)
        
        # 将来自不同来源的同一个交易对的数据合并到一个DataFrame中
        if df_list:
            combined_df = pd.concat(df_list, axis=1)
            # 用前一个有效值填充缺失数据
            combined_df.ffill(inplace=True)
            combined_df.dropna(inplace=True)
            all_data[pair] = combined_df
            print(f"✅ 已加载并合并 {pair} 的数据，共 {len(combined_df)} 条记录。")
    
    return all_data

# ==============================================================================
# 回测核心逻辑
# ==============================================================================

def run_backtest(all_data: Dict[str, pd.DataFrame]):
    """运行回测引擎"""
    opportunities = []

    for pair, df in all_data.items():
        print(f"\n--- 正在回测 {pair} ---")
        
        # 找出所有价格来源 (e.g., ['binance', 'coingecko'])
        sources = sorted(list(set([col.split('_')[1] for col in df.columns if 'close' in col])))
        if len(sources) < 2:
            print(f"  {pair} 只有一个数据源，无法进行套利回测。")
            continue

        # 遍历每一个时间点 (每一行)
        for timestamp, row in df.iterrows():
            prices = {}
            for source in sources:
                close_col = f'close_{source}'
                if close_col in row and pd.notna(row[close_col]):
                    prices[source] = row[close_col]
            
            if len(prices) < 2:
                continue

            # 寻找最佳买入和卖出价格
            best_buy_source = min(prices, key=prices.get)
            best_sell_source = max(prices, key=prices.get)
            
            buy_price = prices[best_buy_source]
            sell_price = prices[best_sell_source]

            # 计算利润率
            profit_pct = (sell_price / buy_price) - 1
            net_profit_pct = profit_pct - (2 * FEE_RATE) # 减去买入和卖出的手续费

            if net_profit_pct > ARBITRAGE_THRESHOLD:
                # 发现了一个历史机会！现在我们来“预测”未来
                future_timestamp = timestamp + pd.Timedelta(hours=FUTURE_LOOKAHEAD)
                
                outcome = {
                    "future_profit_pct": None,
                    "is_successful": 0 # 0代表失败或未知, 1代表成功
                }

                if future_timestamp in df.index:
                    future_row = df.loc[future_timestamp]
                    future_buy_price = future_row.get(f'close_{best_buy_source}')
                    future_sell_price = future_row.get(f'close_{best_sell_source}')

                    if pd.notna(future_buy_price) and pd.notna(future_sell_price):
                        future_profit_pct = (future_sell_price / future_buy_price) - 1
                        future_net_profit_pct = future_profit_pct - (2 * FEE_RATE)
                        outcome["future_profit_pct"] = future_net_profit_pct
                        # 如果未来的利润仍然存在，我们认为这个机会是“成功”的
                        if future_net_profit_pct > ARBITRAGE_THRESHOLD:
                            outcome["is_successful"] = 1
                
                opportunities.append({
                    "timestamp": timestamp,
                    "pair": pair,
                    "buy_source": best_buy_source,
                    "sell_source": best_sell_source,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "profit_pct": net_profit_pct,
                    "future_profit_pct": outcome["future_profit_pct"],
                    "is_successful": outcome["is_successful"]
                })
    
    print(f"\n🎉 回测完成！共发现 {len(opportunities)} 个潜在机会。")
    return pd.DataFrame(opportunities)

# ==============================================================================
# 主程序
# ==============================================================================

if __name__ == "__main__":
    start_time = time.time()

    # 找出所有独特的交易对
    unique_pairs = list(set(["_".join(f.split('_')[:2]).replace('_', '/') for f in os.listdir(DATA_PATH)]))
    
    # 1. 加载数据
    historical_data = load_and_prepare_data(DATA_PATH, unique_pairs)

    # 2. 运行回测
    if historical_data:
        opportunities_df = run_backtest(historical_data)

        # 3. 保存结果
        if not opportunities_df.empty:
            opportunities_df.to_csv(OUTPUT_FILE, index=False)
            print(f"✅ 所有机会已保存到: {OUTPUT_FILE}")
        else:
            print("回测中未发现符合条件的机会。")
    else:
        print("未能加载任何历史数据，请检查 `historical_data` 文件夹。")

    end_time = time.time()
    print(f"\n总耗时: {end_time - start_time:.2f} 秒")
