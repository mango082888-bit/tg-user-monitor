import asyncio
import json
import re
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import Any, Deque, Dict, List, Set

from pyrogram import Client, filters, idle
from pyrogram.errors import RPCError
from pyrogram.handlers import MessageHandler

import config

DATA_LOCK = asyncio.Lock()
DATA_CACHE: Dict[str, Any] = {"users": {}}

bot_client: Client | None = None
user_client: Client | None = None

PROCESSED_ORDER: Dict[int, Deque[int]] = {}
PROCESSED_SEEN: Dict[int, Set[int]] = {}
MAX_PROCESSED_PER_CHAT = 1000
POLL_INTERVAL_SECONDS = 10

ADMINS_CACHE: List[int] = []


def _ensure_rules_file(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"users": {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_data(path: Path) -> Dict[str, Any]:
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
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _get_user_bucket(data: Dict[str, Any], owner_id: int) -> Dict[str, Any]:
    key = str(owner_id)
    if key not in data["users"]:
        data["users"][key] = {"notify_targets": [], "rules": []}
    # 兼容旧数据：单个 notify_target 转为列表
    bucket = data["users"][key]
    if "notify_target" in bucket and "notify_targets" not in bucket:
        old_target = bucket.pop("notify_target")
        bucket["notify_targets"] = [old_target] if old_target else []
    if "notify_targets" not in bucket:
        bucket["notify_targets"] = []
    return bucket


def _normalize_keywords(keywords: List[str]) -> List[str]:
    seen = set()
    result = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        lowered = kw.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(kw)
    return result


def _load_admins() -> List[int]:
    if not config.ADMINS_PATH.exists():
        return []
    try:
        data = json.loads(config.ADMINS_PATH.read_text(encoding="utf-8"))
        return data.get("admins", [])
    except Exception:
        return []


def _save_admins(admins: List[int]) -> None:
    config.ADMINS_PATH.write_text(
        json.dumps({"admins": admins}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _get_all_admins() -> List[int]:
    return list(set(config.SUPER_ADMIN_IDS + ADMINS_CACHE))


def _check_admin(user_id: int) -> bool:
    all_admins = _get_all_admins()
    if not all_admins:
        return True
    return user_id in all_admins


def _is_super_admin(user_id: int) -> bool:
    return user_id in config.SUPER_ADMIN_IDS


def _remember_message(chat_id: int, msg_id: int) -> bool:
    order = PROCESSED_ORDER.setdefault(chat_id, deque())
    seen = PROCESSED_SEEN.setdefault(chat_id, set())
    if msg_id in seen:
        return False
    order.append(msg_id)
    seen.add(msg_id)
    while len(order) > MAX_PROCESSED_PER_CHAT:
        oldest = order.popleft()
        seen.discard(oldest)
    return True


def _keyword_hit(content_lower: str, keyword: str) -> bool:
    if keyword == "*":
        return True
    lowered = keyword.lower()
    if "*" not in lowered:
        return lowered in content_lower
    pattern = re.escape(lowered).replace("\\*", ".*")
    try:
        return re.search(pattern, content_lower) is not None
    except re.error:
        return lowered.replace("*", "") in content_lower


async def cmd_watch(client: Client, message) -> None:
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 4:
        await message.reply_text("用法：/watch 群ID|* 用户ID|* 关键词|*\n* 表示匹配所有")
        return

    group_id = None
    if args[1] != "*":
        try:
            group_id = int(args[1])
        except ValueError:
            await message.reply_text("群ID 必须是数字或 *")
            return

    user_id = None
    if args[2] != "*":
        try:
            user_id = int(args[2])
        except ValueError:
            await message.reply_text("用户ID 必须是数字或 *")
            return

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
        for rule in bucket["rules"]:
            if rule["group_id"] == group_id and rule["user_id"] == user_id and rule["keywords"] == keywords:
                await message.reply_text("规则已存在，无需重复添加。")
                return
        bucket["rules"].append({"group_id": group_id, "user_id": user_id, "keywords": keywords})
        _save_data(config.RULES_PATH, DATA_CACHE)

    await message.reply_text("✅ 已添加监听规则。")


async def cmd_unwatch(client: Client, message) -> None:
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) != 2:
        await message.reply_text("用法：/unwatch 序号\n例如：/unwatch 1")
        return

    try:
        idx = int(args[1])
    except ValueError:
        await message.reply_text("序号必须是数字")
        return

    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        if idx < 1 or idx > len(bucket["rules"]):
            await message.reply_text(f"序号无效，当前共 {len(bucket['rules'])} 条规则")
            return
        removed = bucket["rules"].pop(idx - 1)
        _save_data(config.RULES_PATH, DATA_CACHE)

    gid = removed["group_id"] if removed["group_id"] is not None else "*"
    uid = removed["user_id"] if removed["user_id"] is not None else "*"
    kws = "、".join(removed["keywords"])
    await message.reply_text(f"✅ 已删除规则 {idx}：\n群={gid} 用户={uid} 关键词={kws}")


async def cmd_list(client: Client, message) -> None:
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    owner_id = message.from_user.id
    async with DATA_LOCK:
        bucket = _get_user_bucket(DATA_CACHE, owner_id)
        rules = list(bucket["rules"])
        notify_targets = bucket.get("notify_targets", [])

    if not rules:
        await message.reply_text("当前没有任何规则。")
        return

    lines = ["当前规则："]
    for idx, rule in enumerate(rules, start=1):
        kws = "、".join(rule["keywords"]) if rule["keywords"] != ["*"] else "*"
        gid = rule["group_id"] if rule["group_id"] is not None else "*"
        uid = rule["user_id"] if rule["user_id"] is not None else "*"
        lines.append(f"{idx}. 群={gid} 用户={uid} 关键词={kws}")
    notify_targets = bucket.get("notify_targets", [])
    if notify_targets:
        lines.append(f"通知目标：{', '.join(str(t) for t in notify_targets)}")
    else:
        lines.append("通知目标：未设置（默认发送给你）")
    await message.reply_text("\n".join(lines))


async def cmd_notify(client: Client, message) -> None:
    if not message.from_user or not _check_admin(message.from_user.id):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("用法：\n/notify add 目标ID - 添加通知目标\n/notify del 目标ID - 删除通知目标\n/notify list - 查看所有通知目标\n/notify clear - 清空所有通知目标")
        return

    action = args[1].lower()
    owner_id = message.from_user.id

    if action == "list":
        async with DATA_LOCK:
            bucket = _get_user_bucket(DATA_CACHE, owner_id)
            targets = bucket.get("notify_targets", [])
        if not targets:
            await message.reply_text("当前没有设置通知目标（默认发送给你）")
        else:
            lines = ["📌 当前通知目标："]
            for i, t in enumerate(targets, 1):
                lines.append(f"  {i}. {t}")
            await message.reply_text("\n".join(lines))
        return

    if action == "clear":
        async with DATA_LOCK:
            bucket = _get_user_bucket(DATA_CACHE, owner_id)
            bucket["notify_targets"] = []
            _save_data(config.RULES_PATH, DATA_CACHE)
        await message.reply_text("✅ 已清空所有通知目标。")
        return

    if action in ("add", "del") and len(args) < 3:
        await message.reply_text(f"用法：/notify {action} 目标ID")
        return

    if action == "add":
        try:
            target_id = int(args[2])
        except ValueError:
            await message.reply_text("目标ID 必须是数字。")
            return
        async with DATA_LOCK:
            bucket = _get_user_bucket(DATA_CACHE, owner_id)
            if target_id in bucket["notify_targets"]:
                await message.reply_text("该目标已存在。")
                return
            bucket["notify_targets"].append(target_id)
            _save_data(config.RULES_PATH, DATA_CACHE)
        await message.reply_text(f"✅ 已添加通知目标：{target_id}")

    elif action == "del":
        try:
            target_id = int(args[2])
        except ValueError:
            await message.reply_text("目标ID 必须是数字。")
            return
        async with DATA_LOCK:
            bucket = _get_user_bucket(DATA_CACHE, owner_id)
            if target_id not in bucket["notify_targets"]:
                await message.reply_text("该目标不存在。")
                return
            bucket["notify_targets"].remove(target_id)
            _save_data(config.RULES_PATH, DATA_CACHE)
        await message.reply_text(f"✅ 已删除通知目标：{target_id}")

    else:
        # 兼容旧用法：/notify 目标ID 直接添加
        try:
            target_id = int(args[1])
        except ValueError:
            await message.reply_text("未知操作，请使用 add/del/list/clear")
            return
        async with DATA_LOCK:
            bucket = _get_user_bucket(DATA_CACHE, owner_id)
            if target_id not in bucket["notify_targets"]:
                bucket["notify_targets"].append(target_id)
            _save_data(config.RULES_PATH, DATA_CACHE)
        await message.reply_text(f"✅ 已添加通知目标：{target_id}")


async def cmd_admin(client: Client, message) -> None:
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


async def cmd_help(client: Client, message) -> None:
    if not message.from_user or not _check_admin(message.from_user.id):
        return

    help_text = """📖 使用帮助

🔍 监听管理：
/watch 群ID|* 用户ID|* 关键词|*
  添加监听规则（* 表示匹配所有）
/unwatch 序号
  删除监听规则（序号从 /list 查看）
/list
  查看所有规则

📌 示例：
/watch * 123456 * - 监控用户在所有群的所有消息
/watch -100123 * 出售 - 监控某群所有人说"出售"
/watch -100123 123456 三折 - 精确监控

🔔 通知设置：
/notify add 目标ID - 添加通知目标
/notify del 目标ID - 删除通知目标
/notify list - 查看所有通知目标
/notify clear - 清空所有通知目标

👑 管理员（仅超管）：
/admin add 用户ID - 添加管理员
/admin del 用户ID - 删除管理员
/admin list - 查看管理员列表

💡 提示：
• 群ID 通常是负数，如 -1001234567
• 用户ID 可通过 @userinfobot 获取"""

    await message.reply_text(help_text)


async def process_message(message) -> None:
    if not message.from_user or not message.chat:
        return

    content = message.text or message.caption
    if not content:
        return

    group_id = message.chat.id
    sender_id = message.from_user.id
    msg_id = message.id

    if not _remember_message(group_id, msg_id):
        return

    content_lower = content.lower()

    async with DATA_LOCK:
        data_snapshot = json.loads(json.dumps(DATA_CACHE))

    matched: Dict[str, Dict[str, Any]] = {}
    for owner_id, bucket in data_snapshot.get("users", {}).items():
        for rule in bucket.get("rules", []):
            rule_group = rule.get("group_id")
            rule_user = rule.get("user_id")

            if rule_group is not None and rule_group != group_id:
                continue
            if rule_user is not None and rule_user != sender_id:
                continue

            keywords = rule.get("keywords", [])
            if keywords == ["*"]:
                hit = ["*"]
            else:
                hit = [kw for kw in keywords if _keyword_hit(content_lower, kw)]
                if not hit:
                    continue

            entry = matched.setdefault(owner_id, {"keywords": set(), "notify_targets": bucket.get("notify_targets", [])})
            entry["keywords"].update(hit)

    if not matched or bot_client is None:
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

    chat_username = message.chat.username
    if chat_username:
        group_link = f"https://t.me/{chat_username}"
        msg_link = f"https://t.me/{chat_username}/{msg_id}"
    else:
        chat_id_str = str(group_id).replace("-100", "")
        group_link = f"https://t.me/c/{chat_id_str}"
        msg_link = f"https://t.me/c/{chat_id_str}/{msg_id}"

    for owner_id, info in matched.items():
        keywords_raw = "、".join(sorted(info["keywords"]))
        keywords = "全部" if keywords_raw == "*" else keywords_raw
        notify_targets = info.get("notify_targets", [])
        if not notify_targets:
            notify_targets = [int(owner_id)]  # 默认发给自己
        
        text = (
            "🔔 消息提醒\n\n"
            f"👥 群：{group_name}\n"
            f"👤 用户：{display_name}\n"
            f"🆔 ID：{sender_id}\n"
            f"🔑 关键词：{keywords}\n"
            f"💬 消息：{content}\n"
            f"📍 直达：{msg_link}"
        )
        
        for notify_target in notify_targets:
            try:
                await bot_client.send_message(notify_target, text)
                print(f"[通知] 已发送通知到 {notify_target}")
            except RPCError as exc:
                print(f"[错误] 发送通知到 {notify_target} 失败: {exc}")


async def on_user_message(client: Client, message) -> None:
    await process_message(message)


async def poll_dialogs() -> None:
    global user_client
    if user_client is None:
        return

    async with DATA_LOCK:
        data_snapshot = json.loads(json.dumps(DATA_CACHE))

    chat_ids: Set[int] = set()
    for bucket in data_snapshot.get("users", {}).values():
        for rule in bucket.get("rules", []):
            gid = rule.get("group_id")
            if gid is not None:
                chat_ids.add(gid)

    if not chat_ids:
        return

    print(f"[轮询] 检查 {len(chat_ids)} 个群...")

    for chat_id in chat_ids:
        try:
            messages = [msg async for msg in user_client.get_chat_history(chat_id, limit=5)]
            for msg in reversed(messages):
                if msg:
                    await process_message(msg)
        except Exception:
            print(f"[警告] 群 {chat_id} 获取失败")

    print("[轮询] 检查完成")


async def polling_loop() -> None:
    while True:
        try:
            await poll_dialogs()
        except Exception as exc:
            print(f"[错误] 轮询循环异常: {exc}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    if config.API_ID == 0 or not config.API_HASH:
        raise SystemExit("缺少 TG_API_ID 或 TG_API_HASH 环境变量。")
    if not config.BOT_TOKEN:
        raise SystemExit("缺少 TG_BOT_TOKEN 环境变量。")
    if not config.USER_SESSION_STRING:
        raise SystemExit("缺少 TG_USER_SESSION_STRING 环境变量。")

    global DATA_CACHE, ADMINS_CACHE, bot_client, user_client
    DATA_CACHE = _load_data(config.RULES_PATH)
    ADMINS_CACHE = _load_admins()

    bot = Client(
        name="bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        workdir="./",
    )

    user = Client(
        name="user",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.USER_SESSION_STRING,
        workdir="./",
    )

    bot.add_handler(MessageHandler(cmd_watch, filters.command("watch")))
    bot.add_handler(MessageHandler(cmd_unwatch, filters.command("unwatch")))
    bot.add_handler(MessageHandler(cmd_list, filters.command("list")))
    bot.add_handler(MessageHandler(cmd_notify, filters.command("notify")))
    bot.add_handler(MessageHandler(cmd_admin, filters.command("admin")))
    bot.add_handler(MessageHandler(cmd_help, filters.command("help")))

    user.add_handler(MessageHandler(on_user_message, filters.incoming))

    bot_client = bot
    user_client = user

    await bot.start()
    await user.start()

    print("Bot 和 Userbot 已启动。")
    print(f"使用轮询模式监听消息（每{POLL_INTERVAL_SECONDS}秒检查一次）...")

    polling_task = asyncio.create_task(polling_loop())

    await idle()

    polling_task.cancel()
    with suppress(asyncio.CancelledError):
        await polling_task
    await bot.stop()
    await user.stop()


if __name__ == "__main__":
    asyncio.run(main())
