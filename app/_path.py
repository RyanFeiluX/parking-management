import sys
import os
import json
from pathlib import Path

def get_data_dir():
    """获取应用资源目录（静态文件、模板等）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_user_data_dir():
    """获取用户数据目录（数据库、配置文件等，卸载后保留）"""
    if getattr(sys, 'frozen', False):
        return Path(os.environ.get('APPDATA', Path.home())) / '停车费管理系统'
    return Path(__file__).resolve().parent.parent / 'data'

def ensure_user_data_dir():
    """确保用户数据目录存在"""
    path = get_user_data_dir()
    os.makedirs(path, exist_ok=True)
    return path

def get_db_path():
    """获取默认数据库路径"""
    return get_user_data_dir() / 'parking.db'

def get_config_path():
    """获取配置文件路径"""
    return get_user_data_dir() / 'config.json'

def load_config():
    """加载配置文件"""
    config_path = get_config_path()
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_config(config):
    """保存配置文件"""
    config_path = get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
