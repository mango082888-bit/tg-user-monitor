import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

from pyrogram import Client, filters, idle
from pyrogram.handlers import MessageHandler
from pyrogram.errors import RPCError

import config

# 全局锁，保证并发读写规则文件安全
DATA_LOCK = asyncio.Lock()

# 规则数据缓存
DATA_CACHE: Dict[str, Any] = {
    "users": {}
}

# Bot 客户端对象（在 main 中初始化）
bot_client: Client | None = None


def _ensure_rules_file(path: Path) -> None:
    """确保规则文件存在。"""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"users": {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_data(path: Path) -> Dict[str, Any]:
    """加载规则数据。"""
    _ensure_rules_file(path)
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {"users": {}}
    try:
        data = json.loads(raw)
        if "users" not in data or not isinstance(data["users"], dict):
            return {"users": {}}
        return data
    except json.JSONDecodeError:
        return {"users": {}}


def _save_data(path: Path, data: Dict[str, Any]) -> None:
    """原子写入规则数据。"""
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _get_user_bucket(data: Dict[str, Any], owner_id: int) -> Dict[str, Any]:
    """获取某个配置者的规则桶。"""
    key = str(owner_id)
    if key not in data["users"]:
        data["users"][key] = {
            "notify_target": None,
            "rules": []
        }
    return data["users"][key]


def _normalize_keywords(keywords: List[str]) -> List[str]:
    """清理关键词，去重并保持顺序。"""
    seen = set()
    result = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        if kw.lower() in seen:
            continue
        seen.add(kw.lower())
        result.append(kw)
    return result


# 动态管理员缓存
ADMINS_CACHE: List[int] = []


def _load_admins() -> List[int]:
    """加载动态管理员列表。"""
    if not config.ADMINS_PATH.exists():
        return []
    try:
        data = json.loads(config.ADMINS_PATH.read_text(encoding="utf-8"))
        return data.get("admins", [])
    except:
        return []


def _save_admins(admins: List[int]) -> None:
    """保存动态管理员列表。"""
    config.ADMINS_PATH.write_text(
        json.dumps({"admins": admins}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _get_all_admins() -> List[int]:
    """获取所有管理员（超级管理员 + 动态管理员）。"""
    return list(set(config.SUPER_ADMIN_IDS + ADMINS_CACHE))


def _check_admin(user_id: int) -> bool:
    """检查用户是否是管理员。"""
    all_admins = _get_all_admins()
    if not all_admins:
        return True  # 未配置则允许所有人
    return user_id in all_admins


def _is_super_admin(user_id: int) -> bool:
    """检查是否是超级管理员。"""
    return user_id in config.SUPER_ADMIN_IDS


async def cmd_watch(client: Client, message):
    """/watch 群ID|* 用户ID|* 关键词|*"""
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 4:
        await message.reply_text("用法：/watch 群ID|* 用户ID|* 关键词|*\n* 表示匹配所有")
        return

    # 解析群ID（支持 * 通配符）
    group_id = None
    if args[1] != "*":
        try:
            group_id = int(args[1])
        except ValueError:
            await message.reply_text("群ID 必须是数字或 *")
            return
    
    # 解析用户ID（支持 * 通配符）
    user_id = None
    if args[2] != "*":
        try:
            user_id = int(args[2])
        except ValueError:
            await message.reply_text("用户ID 必须是数字或 *")
            return

    # 解析关键词（支持 * 通配符）
    if args[3] == "*":
        keywords = ["*"]
    else:
        keywords = _normalize_keywords(args[3:])
        if not keywords:
            await message.reply_text("请提供至少一个关键词或 *")
            return

    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        # 去重规则
        for rule in bucket["rules"]:
            if rule["group_id"] == group_id and rule["user_id"] == user_id and rule["keywords"] == keywords:
                await message.reply_text("规则已存在，无需重复添加。")
                return
        bucket["rules"].append({
            "group_id": group_id,
            "user_id": user_id,
            "keywords": keywords
        })
        _save_data(config.RULES_PATH, DATA_CACHE)

    await message.reply_text("已添加监听规则。")


async def cmd_unwatch(client: Client, message):
    """/unwatch 群ID|* 用户ID|*"""
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 3:
        await message.reply_text("用法：/unwatch 群ID|* 用户ID|*")
        return

    # 解析群ID
    group_id = None
    if args[1] != "*":
        try:
            group_id = int(args[1])
        except ValueError:
            await message.reply_text("群ID 必须是数字或 *")
            return
    
    # 解析用户ID
    user_id = None
    if args[2] != "*":
        try:
            user_id = int(args[2])
        except ValueError:
            await message.reply_text("用户ID 必须是数字或 *")
            return

    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        before = len(bucket["rules"])
        bucket["rules"] = [r for r in bucket["rules"] if not (
            (group_id is None or r["group_id"] == group_id) and 
            (user_id is None or r["user_id"] == user_id)
        )]
        after = len(bucket["rules"])
        _save_data(config.RULES_PATH, DATA_CACHE)

    if before == after:
        await message.reply_text("未找到匹配规则。")
    else:
        await message.reply_text("已删除规则。")


async def cmd_list(client: Client, message):
    """/list"""
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        rules = list(bucket["rules"])
        notify_target = bucket.get("notify_target")

    if not rules:
        await message.reply_text("当前没有任何规则。")
        return

    lines = ["当前规则："]
    for idx, rule in enumerate(rules, start=1):
        kws = "、".join(rule["keywords"]) if rule["keywords"] != ["*"] else "*"
        gid = rule['group_id'] if rule['group_id'] is not None else "*"
        uid = rule['user_id'] if rule['user_id'] is not None else "*"
        lines.append(f"{idx}. 群={gid} 用户={uid} 关键词={kws}")
    if notify_target:
        lines.append(f"通知目标：{notify_target}")
    else:
        lines.append("通知目标：未设置（默认发送给你）")
    await message.reply_text("\n".join(lines))


async def cmd_notify(client: Client, message):
    """/notify 目标ID"""
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text("用法：/notify 目标ID")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("目标ID 必须是数字。")
        return

    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        bucket["notify_target"] = target_id
        _save_data(config.RULES_PATH, DATA_CACHE)

    await message.reply_text("通知目标已更新。")


async def cmd_admin(client: Client, message):
    """/admin add|del|list [用户ID]"""
    if not message.from_user or not _is_super_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("用法：/admin add|del|list [用户ID]")
        return
    
    action = args[1].lower()
    global ADMINS_CACHE
    
    if action == "list":
        super_admins = config.SUPER_ADMIN_IDS
        dynamic_admins = ADMINS_CACHE
        lines = ["👑 超级管理员："]
        lines.extend([f"  • {uid}" for uid in super_admins] or ["  （无）"])
        lines.append("👤 普通管理员：")
        lines.extend([f"  • {uid}" for uid in dynamic_admins] or ["  （无）"])
        await message.reply_text("\n".join(lines))
        return
    
    if len(args) < 3:
        await message.reply_text("请提供用户ID")
        return
    
    try:
        target_id = int(args[2])
    except ValueError:
        await message.reply_text("用户ID 必须是数字")
        return
    
    if action == "add":
        if target_id in config.SUPER_ADMIN_IDS:
            await message.reply_text("该用户已是超级管理员")
            return
        if target_id in ADMINS_CACHE:
            await message.reply_text("该用户已是管理员")
            return
        ADMINS_CACHE.append(target_id)
        _save_admins(ADMINS_CACHE)
        await message.reply_text(f"✅ 已添加管理员：{target_id}")
    
    elif action == "del":
        if target_id in config.SUPER_ADMIN_IDS:
            await message.reply_text("无法删除超级管理员")
            return
        if target_id not in ADMINS_CACHE:
            await message.reply_text("该用户不是管理员")
            return
        ADMINS_CACHE.remove(target_id)
        _save_admins(ADMINS_CACHE)
        await message.reply_text(f"✅ 已删除管理员：{target_id}")
    
    else:
        await message.reply_text("未知操作，请使用 add/del/list")


async def cmd_help(client: Client, message):
    """/help"""
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    
    help_text = """📖 使用帮助

🔍 监听管理：
/watch 群ID|* 用户ID|* 关键词|*
  添加监听规则（* 表示匹配所有）
/unwatch 群ID|* 用户ID|*
  删除监听规则
/list
  查看所有规则

📌 示例：
/watch * 123456 * - 监控用户在所有群的所有消息
/watch -100123 * 出售 - 监控某群所有人说"出售"
/watch -100123 123456 三折 - 精确监控

🔔 通知设置：
/notify 目标ID
  设置通知目标（群/用户ID）

👑 管理员（仅超管）：
/admin add 用户ID - 添加管理员
/admin del 用户ID - 删除管理员
/admin list - 查看管理员列表

💡 提示：
• 群ID 通常是负数，如 -1001234567
• 用户ID 可通过 @userinfobot 获取"""
    
    await message.reply_text(help_text)


async def handle_group_message(client: Client, message):
    """Userbot 监听群消息并触发通知。"""
    # 调试日志
    print(f"[DEBUG] 收到消息: chat={message.chat.id if message.chat else None}")
    
    if not message.from_user or not message.chat:
        return

    content = message.text or message.caption
    if not content:
        return
    
    print(f"[DEBUG] 群={message.chat.id} 用户={message.from_user.id} 内容={content[:50]}")

    group_id = message.chat.id
    sender_id = message.from_user.id
    content_lower = content.lower()

    # 提前复制数据，避免持锁发送消息
    async with DATA_LOCK:
        data_snapshot = json.loads(json.dumps(DATA_CACHE))

    matched: Dict[str, Dict[str, Any]] = {}
    for owner_id, bucket in data_snapshot.get("users", {}).items():
        for rule in bucket.get("rules", []):
            rule_group = rule.get("group_id")
            rule_user = rule.get("user_id")
            
            # 检查群ID匹配（None表示通配符*）
            if rule_group is not None and rule_group != group_id:
                continue
            # 检查用户ID匹配（None表示通配符*）
            if rule_user is not None and rule_user != sender_id:
                continue
            
            keywords = rule.get("keywords", [])
            # 检查关键词匹配（*表示匹配所有）
            if keywords == ["*"]:
                hit = ["*"]
            else:
                hit = [kw for kw in keywords if kw.lower() in content_lower]
                if not hit:
                    continue
            
            entry = matched.setdefault(owner_id, {
                "keywords": set(),
                "notify_target": bucket.get("notify_target")
            })
            entry["keywords"].update(hit)

    if not matched:
        return

    group_name = message.chat.title or message.chat.username or str(group_id)
    username = message.from_user.username
    display_name = (message.from_user.first_name or "")
    if message.from_user.last_name:
        display_name = f"{display_name} {message.from_user.last_name}".strip()
    if username:
        display_name = f"{display_name} (@{username})".strip()
    if not display_name:
        display_name = str(sender_id)

    if bot_client is None:
        return

    for owner_id, info in matched.items():
        keywords = "、".join(sorted(info["keywords"]))
        notify_target = info.get("notify_target") or int(owner_id)
        text = (
            f"群名：{group_name}\n"
            f"用户名：{display_name}\n"
            f"用户ID：{sender_id}\n"
            f"关键词：{keywords}\n"
            f"消息内容：{content}"
        )
        try:
            await bot_client.send_message(notify_target, text)
        except RPCError:
            # 发送失败时不抛异常，避免阻塞后续消息
            continue


async def main() -> None:
    if config.API_ID == 0 or not config.API_HASH:
        raise SystemExit("缺少 TG_API_ID 或 TG_API_HASH 环境变量。")
    if not config.BOT_TOKEN:
        raise SystemExit("缺少 TG_BOT_TOKEN 环境变量。")
    if not config.USER_SESSION_STRING:
        raise SystemExit("缺少 TG_USER_SESSION_STRING 环境变量。")

    global DATA_CACHE, ADMINS_CACHE
    DATA_CACHE = _load_data(config.RULES_PATH)
    ADMINS_CACHE = _load_admins()

    bot = Client(
        name="bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        workdir="./"
    )

    user = Client(
        name="user",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.USER_SESSION_STRING,
        workdir="./"
    )

    # 绑定命令处理
    bot.add_handler(MessageHandler(cmd_watch, filters.command("watch")))
    bot.add_handler(MessageHandler(cmd_unwatch, filters.command("unwatch")))
    bot.add_handler(MessageHandler(cmd_list, filters.command("list")))
    bot.add_handler(MessageHandler(cmd_notify, filters.command("notify")))
    bot.add_handler(MessageHandler(cmd_admin, filters.command("admin")))
    bot.add_handler(MessageHandler(cmd_help, filters.command("help")))

    # 监听群消息
    user.add_handler(MessageHandler(handle_group_message, filters.group))

    global bot_client
    bot_client = bot

    await bot.start()
    await user.start()

    # 启动时同步所有群，让 Pyrogram 缓存群信息
    print("正在同步群列表...")
    try:
        async for dialog in user.get_dialogs():
            pass  # 遍历一遍让 Pyrogram 缓存
        print("群列表同步完成")
    except Exception as e:
        print(f"同步群列表失败: {e}")

    print("Bot 和 Userbot 已启动。按 Ctrl+C 退出。")
    await idle()

    await bot.stop()
    await user.stop()


if __name__ == "__main__":
    asyncio.run(main())
