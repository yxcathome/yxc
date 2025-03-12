from typing import Dict, Any
import json

class Settings:
    def __init__(self):
        self.default_settings = {
            'database': {
                'type': 'postgresql',
                'host': 'localhost',
                'port': 5432,
                'name': 'trading_bot',
                'username': '',
                'password': ''
            },
            'redis': {
                'host': 'localhost',
                'port': 6379
            },
            'exchanges': {
                'binance': {
                    'enabled': False,
                    'api_key': '',
                    'secret_key': '',
                    'testnet': False
                },
                'okx': {
                    'enabled': False,
                    'api_key': '',
                    'secret_key': '',
                    'testnet': False
                }
            },
            'notification': {
                'smtp': {
                    'server': '',
                    'email': '',
                    'password': ''
                },
                'telegram': {
                    'token': '',
                    'chat_id': ''
                }
            },
            'risk': {
                'max_loss_per_trade': 0.02,
                'max_daily_loss': 0.05,
                'max_leverage': 5,
                'max_single_position': 0.2,
                'drawdown_alert': 0.1,
                'volatility_alert': 0.03
            },
            'logging': {
                'level': 'INFO',
                'retention': 30,
                'console': True
            }
        }
        self.settings = self.default_settings.copy()
        
    async def load(self):
        """从数据库加载设置"""
        try:
            from models.database import Database
            db = Database()
            async with db.pg_pool.acquire() as conn:
                records = await conn.fetch("""
                    SELECT key, value
                    FROM settings
                """)
                
                for record in records:
                    self._update_nested_dict(
                        self.settings,
                        record['key'].split('.'),
                        json.loads(record['value'])
                    )
                    
        except Exception as e:
            raise Exception(f"加载设置失败: {e}")
            
    async def save(self):
        """保存设置到数据库"""
        try:
            from models.database import Database
            db = Database()
            async with db.pg_pool.acquire() as conn:
                # 清空现有设置
                await conn.execute("DELETE FROM settings")
                
                # 保存新设置
                for key, value in self._flatten_dict(self.settings).items():
                    await conn.execute("""
                        INSERT INTO settings (key, value)
                        VALUES ($1, $2)
                    """, key, json.dumps(value))
                    
        except Exception as e:
            raise Exception(f"保存设置失败: {e}")
            
    def update(self, new_settings: Dict):
        """更新设置"""
        self._merge_dicts(self.settings, new_settings)
        
    def reset(self):
        """重置为默认设置"""
        self.settings = self.default_settings.copy()
        
    def _merge_dicts(self, dict1: Dict, dict2: Dict):
        """递归合并字典"""
        for key, value in dict2.items():
            if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
                self._merge_dicts(dict1[key], value)
            else:
                dict1[key] = value
                
    def _update_nested_dict(self, d: Dict, keys: list, value: Any):
        """更新嵌套字典的值"""
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
        
    def _flatten_dict(self, d: Dict, parent_key: str = '') -> Dict:
        """将嵌套字典展平为点分隔的键"""
        items = []
        for key, value in d.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self._flatten_dict(value, new_key).items())
            else:
                items.append((new_key, value))
        return dict(items)
        
    def get(self, key: str, default: Any = None) -> Any:
        """获取设置值"""
        try:
            keys = key.split('.')
            value = self.settings
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
            
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'exchanges': self.settings['exchanges'],
            'notification': self.settings['notification'],
            'system': {
                'database': self.settings['database'],
                'logging': self.settings['logging']
            }
        }