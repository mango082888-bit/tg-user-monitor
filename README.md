# Telegram 用户监听机器人

基于 **Pyrogram Userbot + Bot** 的监听与通知项目：
- Userbot 监听所有群消息
- Bot 负责规则配置与发送通知

## 功能
- `/watch 群ID 用户ID 关键词1 关键词2` 添加监听规则
- `/unwatch 群ID 用户ID` 删除规则
- `/list` 查看所有规则
- `/notify 目标ID` 设置通知目标（不设置则默认通知给你自己）

触发通知包含：群名、用户名、用户ID、关键词、消息内容。

## 运行前准备
1. 在 https://my.telegram.org 申请 `api_id` 与 `api_hash`。
2. 获取 Userbot 的会话字符串（Session String）。

生成 Session String 示例：
```bash
python - <<'PY'
from pyrogram import Client

api_id = int(input("API_ID: "))
api_hash = input("API_HASH: ")

with Client("user", api_id=api_id, api_hash=api_hash) as app:
    print(app.export_session_string())
PY
```

## 本地运行
```bash
pip install -r requirements.txt

export TG_API_ID=123456
export TG_API_HASH=your_api_hash
export TG_BOT_TOKEN=123456:bot_token
export TG_USER_SESSION_STRING=your_user_session_string

python main.py
```

## Docker 运行
```bash
docker compose up -d --build
```

## 规则存储
- 默认存储在 `./rules.json`
- 可通过环境变量 `RULES_PATH` 自定义
- 支持多用户独立配置

## 注意事项
- 需要确保 Userbot 已加入目标群
- Bot 需要能够向通知目标发送消息
