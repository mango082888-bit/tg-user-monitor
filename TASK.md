# 任务：重写 Telegram 用户监听机器人

## 问题
当前代码使用 Pyrogram 的实时消息监听，但某些群（如 `-1001980054543`）的消息收不到。
Pyrogram 的 `get_dialogs()` 和 `iter_dialogs()` 有 bug，会抛出 `'NoneType' object has no attribute 'id'`。

## 需求
重写 `main.py`，实现：

1. **双模式监听**：
   - 保留 Pyrogram 的实时消息监听（MessageHandler）
   - 新增轮询模式：每 10 秒检查规则中指定的群的最新消息

2. **轮询逻辑**：
   - 从 `rules.json` 中提取所有 `group_id`（非 None 的）
   - 对每个群调用 `get_chat_history(chat_id, limit=5)` 获取最新消息
   - 用 `message.id` 去重，避免重复通知
   - 去重缓存保存在内存中，每个群最多保存 1000 条消息 ID

3. **不要使用**：
   - `get_dialogs()` - 有 bug
   - `iter_dialogs()` - 有 bug

4. **保留现有功能**：
   - Bot 命令：/watch, /unwatch, /list, /notify, /admin, /help
   - 规则匹配：群ID、用户ID、关键词（支持 * 通配符）
   - 通知格式：群名、群链接、用户、消息、直达链接

## 现有文件
- `config.py` - 配置（API_ID, API_HASH, BOT_TOKEN, USER_SESSION_STRING, ADMIN_IDS）
- `rules.json` - 规则存储
- `.env` - 环境变量

## 测试
完成后，用这个群测试轮询：`-1001980054543`（dmithost 群）
