# Telegram 用户监听机器人

基于 Pyrogram 的群消息监控工具，支持关键词过滤、用户追踪、实时通知。

## 功能

- ✅ 双模式监听：实时推送 + 轮询检查
- ✅ 灵活规则：群ID、用户ID、关键词组合
- ✅ 群链接支持：直接用 t.me/xxx 添加监控
- ✅ 即时通知：触发后推送到指定群/用户
- ✅ 权限管理：超级管理员 + 动态管理员

## 安装

```bash
curl -sL https://raw.githubusercontent.com/mango082888-bit/tg-user-monitor/main/install.sh -o install.sh
bash install.sh
```

## 使用

```bash
# 监控某群某用户的所有消息
/watch https://t.me/RFCHOSTOfficial 69204830 *

# 监控某群所有人说"三折"或"出售"
/watch https://t.me/dmithost * 三折 出售

# 查看规则
/list

# 删除规则
/unwatch 1

# 设置通知目标
/notify -1001234567890
```

## 配置说明

安装时会询问：

1. **TG_API_ID** - 从 https://my.telegram.org 获取
2. **TG_API_HASH** - 从 https://my.telegram.org 获取
3. **TG_BOT_TOKEN** - 从 @BotFather 获取
4. **TG_USER_SESSION_STRING** - Pyrogram Session String
5. **ADMIN_IDS** - 管理员用户ID，多个用逗号分隔

## 常用命令

```bash
# 查看状态
systemctl status tg-user-monitor

# 查看日志
journalctl -u tg-user-monitor -f

# 重启服务
systemctl restart tg-user-monitor
```

## License

MIT
