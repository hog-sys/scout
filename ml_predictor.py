"""
机器学习预测器
"""
import asyncio
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import joblib
import logging
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

class MLPredictor:
    """机器学习预测器"""
    
    def __init__(self, config):
        self.config = config
        self.models = {}
        self.scalers = {}
        self.model_path = Path(config.ML_MODEL_PATH)
        self.model_path.mkdir(exist_ok=True)
        
        # 特征工程参数
        self.feature_window = 20  # 使用过去20个数据点
        self.prediction_horizon = 5  # 预测未来5分钟
        
        # 模型参数
        self.model_params = {
            'opportunity_classifier': {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 5
            },
            'price_predictor': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5
            }
        }
        
    async def initialize(self):
        """初始化预测器"""
        logger.info("初始化ML预测器...")
        
        # 加载已有模型
        await self._load_models()
        
        # 启动定期重训练
        asyncio.create_task(self._periodic_retrain())
    
    async def _load_models(self):
        """加载已保存的模型"""
        try:
            # 机会分类器
            opp_model_path = self.model_path / 'opportunity_classifier.pkl'
            if opp_model_path.exists():
                self.models['opportunity_classifier'] = joblib.load(opp_model_path)
                self.scalers['opportunity_classifier'] = joblib.load(
                    self.model_path / 'opportunity_scaler.pkl'
                )
                logger.info("✅ 加载机会分类器模型")
            
            # 价格预测器
            price_model_path = self.model_path / 'price_predictor.pkl'
            if price_model_path.exists():
                self.models['price_predictor'] = joblib.load(price_model_path)
                self.scalers['price_predictor'] = joblib.load(
                    self.model_path / 'price_scaler.pkl'
                )
                logger.info("✅ 加载价格预测器模型")
                
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
    
    async def predict_opportunity_quality(self, opportunity: Dict) -> Dict[str, float]:
        """预测机会质量"""
        try:
            if 'opportunity_classifier' not in self.models:
                return {'quality_score': opportunity.get('confidence', 0.5)}
            
            # 提取特征
            features = self._extract_opportunity_features(opportunity)
            
            if features is None:
                return {'quality_score': opportunity.get('confidence', 0.5)}
            
            # 标准化
            features_scaled = self.scalers['opportunity_classifier'].transform([features])
            
            # 预测
            prediction = self.models['opportunity_classifier'].predict_proba(features_scaled)
            quality_score = prediction[0][1]  # 获取正类概率
            
            # 获取特征重要性
            feature_importance = self._get_feature_importance(
                self.models['opportunity_classifier'],
                self._get_opportunity_feature_names()
            )
            
            return {
                'quality_score': float(quality_score),
                'original_confidence': opportunity.get('confidence', 0),
                'ml_confidence': float(quality_score),
                'feature_importance': feature_importance
            }
            
        except Exception as e:
            logger.error(f"预测机会质量失败: {e}")
            return {'quality_score': opportunity.get('confidence', 0.5)}
    
    async def predict_price_movement(self, symbol: str, price_history: List[Dict]) -> Dict[str, Any]:
        """预测价格走势"""
        try:
            if 'price_predictor' not in self.models or len(price_history) < self.feature_window:
                return {'prediction': 'unknown', 'confidence': 0}
            
            # 提取特征
            features = self._extract_price_features(price_history)
            
            if features is None:
                return {'prediction': 'unknown', 'confidence': 0}
            
            # 标准化
            features_scaled = self.scalers['price_predictor'].transform([features])
            
            # 预测
            predicted_return = self.models['price_predictor'].predict(features_scaled)[0]
            
            # 解释预测
            if predicted_return > 0.5:
                direction = 'up'
            elif predicted_return < -0.5:
                direction = 'down'
            else:
                direction = 'sideways'
            
            confidence = min(abs(predicted_return) / 2, 1.0)  # 归一化置信度
            
            return {
                'symbol': symbol,
                'prediction': direction,
                'predicted_return': float(predicted_return),
                'confidence': float(confidence),
                'horizon_minutes': self.prediction_horizon
            }
            
        except Exception as e:
            logger.error(f"预测价格走势失败: {e}")
            return {'prediction': 'unknown', 'confidence': 0}
    
    def _extract_opportunity_features(self, opportunity: Dict) -> Optional[List[float]]:
        """提取机会特征"""
        try:
            features = []
            
            # 基础特征
            features.append(opportunity.get('confidence', 0))
            
            # 信号类型编码
            signal_types = ['arbitrage', 'volume_spike', 'price_movement', 'orderbook_imbalance']
            signal_type = opportunity.get('signal_type', '')
            for st in signal_types:
                features.append(1.0 if signal_type == st else 0.0)
            
            # 数据特征
            data = opportunity.get('data', {})
            
            # 套利特征
            if signal_type == 'arbitrage':
                features.append(data.get('profit_pct', 0))
                features.append(data.get('volume_24h', 0) / 1000000)  # 归一化
            else:
                features.extend([0, 0])
            
            # 成交量特征
            if signal_type == 'volume_spike':
                features.append(data.get('volume_ratio', 1))
                features.append(data.get('price_change_1h', 0))
            else:
                features.extend([1, 0])
            
            # 价格移动特征
            if signal_type == 'price_movement':
                features.append(abs(data.get('change_pct', 0)))
                features.append(1 if data.get('direction') == 'up' else -1)
            else:
                features.extend([0, 0])
            
            # 时间特征
            timestamp = datetime.fromisoformat(opportunity.get('timestamp', datetime.now().isoformat()))
            features.append(timestamp.hour / 24)  # 归一化小时
            features.append(timestamp.weekday() / 7)  # 归一化星期
            
            return features
            
        except Exception as e:
            logger.error(f"提取机会特征失败: {e}")
            return None
    
    def _extract_price_features(self, price_history: List[Dict]) -> Optional[List[float]]:
        """提取价格特征"""
        try:
            prices = [p['price'] for p in price_history[-self.feature_window:]]
            
            if len(prices) < self.feature_window:
                return None
            
            features = []
            
            # 价格变化率
            returns = np.diff(prices) / prices[:-1]
            features.extend([
                np.mean(returns),
                np.std(returns),
                np.min(returns),
                np.max(returns)
            ])
            
            # 技术指标
            sma_5 = np.mean(prices[-5:])
            sma_20 = np.mean(prices)
            features.append((prices[-1] - sma_5) / sma_5)
            features.append((prices[-1] - sma_20) / sma_20)
            
            # 动量
            momentum_5 = (prices[-1] - prices[-6]) / prices[-6]
            features.append(momentum_5)
            
            # 波动率
            volatility = np.std(prices) / np.mean(prices)
            features.append(volatility)
            
            # 价格位置（归一化）
            price_min = np.min(prices)
            price_max = np.max(prices)
            if price_max > price_min:
                price_position = (prices[-1] - price_min) / (price_max - price_min)
            else:
                price_position = 0.5
            features.append(price_position)
            
            return features
            
        except Exception as e:
            logger.error(f"提取价格特征失败: {e}")
            return None
    
    def _get_opportunity_feature_names(self) -> List[str]:
        """获取机会特征名称"""
        return [
            'confidence',
            'is_arbitrage', 'is_volume_spike', 'is_price_movement', 'is_orderbook_imbalance',
            'profit_pct', 'volume_millions',
            'volume_ratio', 'price_change_1h',
            'abs_change_pct', 'direction',
            'hour_normalized', 'weekday_normalized'
        ]
    
    def _get_feature_importance(self, model, feature_names: List[str]) -> Dict[str, float]:
        """获取特征重要性"""
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            return dict(zip(feature_names, importances))
        return {}
    
    async def _periodic_retrain(self):
        """定期重训练模型"""
        while True:
            try:
                # 等待配置的时间间隔
                await asyncio.sleep(self.config.ML_RETRAIN_INTERVAL)
                
                logger.info("开始重训练ML模型...")
                
                # 获取训练数据
                training_data = await self._get_training_data()
                
                if training_data:
                    # 训练机会分类器
                    await self._train_opportunity_classifier(training_data)
                    
                    # 训练价格预测器
                    await self._train_price_predictor(training_data)
                    
                    logger.info("✅ ML模型重训练完成")
                    
            except Exception as e:
                logger.error(f"模型重训练失败: {e}")
    
    async def _get_training_data(self) -> Optional[pd.DataFrame]:
        """获取训练数据"""
        # 这里应该从数据库或文件中读取历史数据
        # 暂时返回None
        return None
    
    async def _train_opportunity_classifier(self, data: pd.DataFrame):
        """训练机会分类器"""
        try:
            # 准备特征和标签
            features = []
            labels = []
            
            # 这里需要实际的训练逻辑
            
            if len(features) < 100:
                logger.warning("训练数据不足，跳过训练")
                return
            
            # 划分训练集和测试集
            X_train, X_test, y_train, y_test = train_test_split(
                features, labels, test_size=0.2, random_state=42
            )
            
            # 标准化
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            # 训练模型
            model = RandomForestClassifier(**self.model_params['opportunity_classifier'])
            model.fit(X_train_scaled, y_train)
            
            # 评估
            score = model.score(X_test_scaled, y_test)
            logger.info(f"机会分类器准确率: {score:.2f}")
            
            # 保存模型
            joblib.dump(model, self.model_path / 'opportunity_classifier.pkl')
            joblib.dump(scaler, self.model_path / 'opportunity_scaler.pkl')
            
            self.models['opportunity_classifier'] = model
            self.scalers['opportunity_classifier'] = scaler
            
        except Exception as e:
            logger.error(f"训练机会分类器失败: {e}")
    
    async def _train_price_predictor(self, data: pd.DataFrame):
        """训练价格预测器"""
        # 类似的训练逻辑
        pass