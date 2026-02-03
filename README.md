# 🤖 Telegram 用户监听机器人

基于 Pyrogram 的 Telegram 群消息监控工具，支持关键词过滤、用户追踪、实时通知。

## ✨ 功能特点

- 📡 **双模式监听**：实时推送 + 轮询检查，不漏消息
- 🔍 **灵活规则**：支持群ID、用户ID、关键词组合过滤
- 🔗 **群链接支持**：直接用 `t.me/xxx` 添加监控，自动获取群ID
- 🔔 **即时通知**：触发规则后立即推送到指定群/用户
- 👑 **权限管理**：超级管理员 + 动态管理员

## 🚀 一键安装

```bash
curl -sL https://raw.githubusercontent.com/mango082888-bit/tg-user-monitor/main/install.sh -o install.sh
bash install.sh
```

安装时需要输入：
- `TG_API_ID` - 从 https://my.telegram.org 获取
- `TG_API_HASH` - 从 https://my.telegram.org 获取
- `TG_BOT_TOKEN` - 从 @BotFather 获取
- `TG_USER_SESSION_STRING` - Pyrogram Session String
- `ADMIN_IDS` - 管理员用户ID，多个用逗号分隔

## 📋 Bot 命令

| 命令 | 说明 |
|------|------|
| `/watch 群链接 用户ID 关键词` | 添加监控规则 |
| `/unwatch 序号` | 删除规则 |
| `/list` | 查看所有规则 |
| `/notify 目标ID` | 设置通知目标 |
| `/help` | 帮助信息 |

## 📌 使用示例

```
# 监控某群某用户的所有消息
/watch https://t.me/RFCHOSTOfficial 69204830 *

# 监控某群所有人说"三折"或"出售"
/watch https://t.me/dmithost * 三折 出售

# 监控某用户在所有群的消息（依赖实时推送）
/watch * 69204830 *
```

## 🔧 常用命令

```bash
# 查看状态
systemctl status tg-user-monitor

# 查看日志
journalctl -u tg-user-monitor -f

# 重启服务
systemctl restart tg-user-monitor
```

## 📝 获取 Session String

```python
from pyrogram import Client

api_id = 你的API_ID
api_hash = "你的API_HASH"

with Client("my_account", api_id, api_hash) as app:
    print(app.export_session_string())
```

## 📄 License

MIT
