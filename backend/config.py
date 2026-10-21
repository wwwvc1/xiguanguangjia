"""兼容 shim —— 真正的配置在 core/config.py

保留这个文件是为了让既有的 30+ 处 `from config import settings` 不用改。
新代码请直接 `from core.config import settings`。
"""
from core.config import BACKEND_DIR, ENV_FILE, Settings, settings

__all__ = ["Settings", "settings", "BACKEND_DIR", "ENV_FILE"]
