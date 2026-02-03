#!/bin/bash
# Telegram 用户监听机器人 一键安装脚本
# GitHub: https://github.com/mango082888-bit/tg-user-monitor

set -e

echo "🤖 Telegram 用户监听机器人 安装脚本"
echo "=================================="

# 检查 root
if [ "$EUID" -ne 0 ]; then
  echo "❌ 请使用 root 用户运行"
  exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
apt update -qq
apt install -y python3 python3-pip git -qq

# 克隆项目
INSTALL_DIR="/opt/tg-user-monitor"
if [ -d "$INSTALL_DIR" ]; then
  echo "📁 目录已存在，更新代码..."
  cd "$INSTALL_DIR"
  git pull
else
  echo "📥 克隆项目..."
  git clone https://github.com/mango082888-bit/tg-user-monitor.git "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi

# 安装 Python 依赖
echo "🐍 安装 Python 依赖..."
pip3 install pyrogram tgcrypto --break-system-packages -q

# 配置环境变量
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "⚙️ 配置环境变量"
  echo "---------------"
  
  read -p "TG_API_ID: " API_ID
  read -p "TG_API_HASH: " API_HASH
  read -p "TG_BOT_TOKEN: " BOT_TOKEN
  read -p "TG_USER_SESSION_STRING: " SESSION
  read -p "ADMIN_IDS (管理员ID，多个用逗号分隔): " ADMIN_IDS

  cat > "$ENV_FILE" << EOF
TG_API_ID=$API_ID
TG_API_HASH=$API_HASH
TG_BOT_TOKEN=$BOT_TOKEN
TG_USER_SESSION_STRING=$SESSION
ADMIN_IDS=$ADMIN_IDS
EOF
  echo "✅ 环境变量已保存到 $ENV_FILE"
else
  echo "✅ 环境变量文件已存在"
fi

# 创建 systemd 服务
echo "🔧 创建 systemd 服务..."
cat > /etc/systemd/system/tg-user-monitor.service << EOF
[Unit]
Description=Telegram User Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
systemctl daemon-reload
systemctl enable tg-user-monitor
systemctl restart tg-user-monitor

echo ""
echo "✅ 安装完成！"
echo ""
echo "📋 常用命令："
echo "  查看状态: systemctl status tg-user-monitor"
echo "  查看日志: journalctl -u tg-user-monitor -f"
echo "  重启服务: systemctl restart tg-user-monitor"
echo ""
echo "🤖 Bot 命令："
echo "  /watch 群链接 用户ID 关键词"
echo "  /list 查看规则"
echo "  /help 帮助"
