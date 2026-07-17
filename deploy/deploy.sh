#!/usr/bin/env bash
# Trading Service 极简部署脚本
# 用法：sudo bash deploy/deploy.sh
# 依赖：服务器已装 uv（curl -LsSf https://astral.sh/uv/install.sh | sh）

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="trading-service"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# 用执行 sudo 的用户运行服务（保留其 uv 缓存，避免新建用户）
RUN_USER="${SUDO_USER:-$USER}"

# systemd 的 PATH 很精简，必须用 uv 的绝对路径
USER_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
UV_PATH=""
for p in "$(command -v uv 2>/dev/null)" "$USER_HOME/.local/bin/uv" "/usr/local/bin/uv"; do
    [[ -n "$p" && -x "$p" ]] && { UV_PATH="$p"; break; }
done
[[ -n "$UV_PATH" ]] || { echo "未找到 uv，请先安装：curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Trading Service
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=$UV_PATH run uvicorn trading_service.app:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$APP_NAME"

echo "✅ 已启动并设为开机自启"
echo "状态：sudo systemctl status $APP_NAME"
echo "日志：sudo journalctl -u $APP_NAME -f"
