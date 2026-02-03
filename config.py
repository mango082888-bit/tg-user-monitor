import os
from pathlib import Path

# Telegram API 配置
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
USER_SESSION_STRING = os.getenv("TG_USER_SESSION_STRING", "")

# 规则文件路径
RULES_PATH = Path(os.getenv("RULES_PATH", "./rules.json"))

# 日志等级
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 超级管理员（环境变量配置，不可被删除）
SUPER_ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# 动态管理员文件路径
ADMINS_PATH = Path(os.getenv("ADMINS_PATH", "./admins.json"))
