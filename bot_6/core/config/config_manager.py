from typing import Dict, Optional, Any
import os
import yaml
import json
from datetime import datetime
import asyncio
from pathlib import Path
from utils.logger import setup_logger

class ConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.logger = setup_logger("config_manager")
        
        # 配置缓存
        self._config_cache = {}
        self._last_modified = {}
        self._watch_tasks = {}
        
        # 配置文件映射
        self.CONFIG_FILES = {
            'global': 'global.yaml',
            'exchanges': 'exchanges.yaml',
            'strategies': 'strategies.yaml',
            'risk': 'risk.yaml',
            'database': 'database.yaml',
            'api': 'api.yaml'
        }
        
        # 默认配置
        self.DEFAULT_CONFIG = {
            'global': {
                'environment': 'development',
                'log_level': 'INFO',
                'timezone': 'UTC',
                'max_workers': 4
            },
            'risk': {
                'max_positions': 4,
                'max_drawdown': 0.1,
                'daily_loss_limit': 0.05,
                'position_size_limit': 0.3
            }
        }
        
    async def initialize(self):
        """初始化配置管理器"""
        try:
            # 创建配置目录
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # 初始化配置文件
            for config_type, filename in self.CONFIG_FILES.items():
                config_path = self.config_dir / filename
                if not config_path.exists():
                    await self._create_default_config(config_type, config_path)
                    
            # 加载所有配置
            for config_type in self.CONFIG_FILES:
                await self.load_config(config_type)
                
            # 启动配置文件监控
            asyncio.create_task(self._watch_config_changes())
            
            self.logger.info("配置管理器初始化完成")
            return True
            
        except Exception as e:
            self.logger.error(f"配置管理器初始化失败: {e}")
            return False
            
    async def load_config(self, config_type: str) -> Optional[Dict]:
        """加载指定类型的配置"""
        try:
            if config_type not in self.CONFIG_FILES:
                raise ValueError(f"未知的配置类型: {config_type}")
                
            config_path = self.config_dir / self.CONFIG_FILES[config_type]
            if not config_path.exists():
                self.logger.warning(f"配置文件不存在: {config_path}")
                return None
                
            # 检查是否需要重新加载
            last_modified = config_path.stat().st_mtime
            if (config_type in self._config_cache and 
                self._last_modified.get(config_type) == last_modified):
                return self._config_cache[config_type]
                
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix == '.yaml':
                    config = yaml.safe_load(f)
                elif config_path.suffix == '.json':
                    config = json.load(f)
                else:
                    raise ValueError(f"不支持的配置文件格式: {config_path.suffix}")
                    
            # 更新缓存
            self._config_cache[config_type] = config
            self._last_modified[config_type] = last_modified
            
            return config
            
        except Exception as e:
            self.logger.error(f"加载配置失败 ({config_type}): {e}")
            return None
            
    async def save_config(self, config_type: str, config_data: Dict) -> bool:
        """保存配置"""
        try:
            if config_type not in self.CONFIG_FILES:
                raise ValueError(f"未知的配置类型: {config_type}")
                
            config_path = self.config_dir / self.CONFIG_FILES[config_type]
            
            # 创建备份
            if config_path.exists():
                backup_path = config_path.with_suffix(f".bak.{int(datetime.utcnow().timestamp())}")
                config_path.rename(backup_path)
                
            # 保存新配置
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix == '.yaml':
                    yaml.dump(config_data, f, default_flow_style=False)
                elif config_path.suffix == '.json':
                    json.dump(config_data, f, indent=2)
                    
            # 更新缓存
            self._config_cache[config_type] = config_data
            self._last_modified[config_type] = config_path.stat().st_mtime
            
            self.logger.info(f"配置已保存: {config_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存配置失败 ({config_type}): {e}")
            return False
            
    async def get_config(self, config_type: str, key: Optional[str] = None) -> Any:
        """获取配置值"""
        try:
            config = await self.load_config(config_type)
            if config is None:
                return None
                
            if key is None:
                return config
                
            # 支持嵌套键访问 (eg: "database.host")
            keys = key.split('.')
            value = config
            for k in keys:
                if not isinstance(value, dict) or k not in value:
                    return None
                value = value[k]
                
            return value
            
        except Exception as e:
            self.logger.error(f"获取配置失败 ({config_type}.{key}): {e}")
            return None
            
    async def update_config(self, config_type: str, key: str, value: Any) -> bool:
        """更新配置值"""
        try:
            config = await self.load_config(config_type)
            if config is None:
                config = {}
                
            # 处理嵌套键
            keys = key.split('.')
            current = config
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
                
            current[keys[-1]] = value
            
            return await self.save_config(config_type, config)
            
        except Exception as e:
            self.logger.error(f"更新配置失败 ({config_type}.{key}): {e}")
            return False
            
    async def _create_default_config(self, config_type: str, config_path: Path):
        """创建默认配置文件"""
        try:
            default_config = self.DEFAULT_CONFIG.get(config_type, {})
            
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix == '.yaml':
                    yaml.dump(default_config, f, default_flow_style=False)
                elif config_path.suffix == '.json':
                    json.dump(default_config, f, indent=2)
                    
            self.logger.info(f"创建默认配置文件: {config_path}")
            
        except Exception as e:
            self.logger.error(f"创建默认配置文件失败 ({config_type}): {e}")
            
    async def _watch_config_changes(self):
        """监控配置文件变化"""
        while True:
            try:
                for config_type, filename in self.CONFIG_FILES.items():
                    config_path = self.config_dir / filename
                    if not config_path.exists():
                        continue
                        
                    last_modified = config_path.stat().st_mtime
                    if (config_type in self._last_modified and 
                        self._last_modified[config_type] != last_modified):
                        # 配置文件已更改，重新加载
                        self.logger.info(f"检测到配置变化: {config_type}")
                        await self.load_config(config_type)
                        
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except Exception as e:
                self.logger.error(f"监控配置变化失败: {e}")
                await asyncio.sleep(30)  # 发生错误时增加检查间隔