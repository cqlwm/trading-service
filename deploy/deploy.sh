#!/usr/bin/env bash
# Trading Service 简易部署脚本
#
# 用法：
#   sudo bash deploy/deploy.sh         # 安装/更新并启动服务
#   bash deploy/deploy.sh --uninstall  # 卸载（保留代码和数据）
#
# 幂等：可重复执行，已存在的步骤会跳过。
# 仅支持 Linux + systemd（Debian/Ubuntu 系，需 root）。

set -euo pipefail

# ---------------- 可配置项（按需修改） ----------------
APP_NAME="trading-service"
APP_USER="trading"                       # 运行服务的系统用户

# 代码目录：默认为脚本所在目录的上一级（即仓库根），
# 因为 deploy.sh 位于 <repo>/deploy/ 下。
# 如需指定其他位置，可在此覆盖或通过环境变量 APP_DIR 传入。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(dirname "$SCRIPT_DIR")}"

# binance-service 是本地路径依赖（pyproject.toml 中声明为 path 依赖），
# 默认假设与本项目同级；如不在同级请通过环境变量 BINANCE_SERVICE_DIR 传入。
BINANCE_SERVICE_DIR="${BINANCE_SERVICE_DIR:-$(dirname "$APP_DIR")/binance-service}"

SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
ENV_DIR="/etc/${APP_NAME}"
ENV_FILE="${ENV_DIR}/env"
DATA_DIR="${DATA_DIR:-/var/lib/${APP_NAME}}"
# -----------------------------------------------------

log()  { echo -e "\033[32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[33m[warn]\033[0m $*" >&2; }
die()  { echo -e "\033[31m[error]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "请用 root 或 sudo 执行：sudo bash deploy/deploy.sh"
command -v systemctl >/dev/null || die "未检测到 systemd，本脚本仅支持 systemd 系统"

log "代码目录: $APP_DIR"
log "binance-service 目录: $BINANCE_SERVICE_DIR"
log "数据目录: $DATA_DIR"
echo

UNINSTALL=0
[[ "${1:-}" == "--uninstall" ]] && UNINSTALL=1

# -----------------------------------------------------
# 卸载
# -----------------------------------------------------
if [[ $UNINSTALL -eq 1 ]]; then
    log "停止并禁用服务..."
    systemctl disable --now "${APP_NAME}.service" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    log "卸载完成。代码目录 $APP_DIR 与数据目录 $DATA_DIR 已保留，如需删除请手动 rm -rf。"
    exit 0
fi

# -----------------------------------------------------
# 1. 安装系统依赖（TA-Lib C 库 + uv）
# -----------------------------------------------------
install_talib() {
    if ldconfig -p | grep -q "libta_lib"; then
        log "TA-Lib C 库已安装，跳过"
        return
    fi
    log "编译安装 TA-Lib C 库（约 1 分钟）..."
    local tmp; tmp=$(mktemp -d)
    cd "$tmp"
    wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
    tar xzf ta-lib-0.4.0-src.tar.gz
    cd ta-lib
    ./configure --prefix=/usr >/dev/null
    make -j"$(nproc)" >/dev/null
    make install >/dev/null
    ldconfig
    cd - >/dev/null
    rm -rf "$tmp"
    log "TA-Lib C 库安装完成"
}

install_uv() {
    if [[ -x /usr/local/bin/uv ]]; then
        log "uv 已安装，跳过"
        return
    fi
    log "安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
    # uv 默认装到 ~/.local/bin，链接到全局路径方便 APP_USER 使用
    ln -sf /root/.local/bin/uv /usr/local/bin/uv
    log "uv 安装完成"
}

if ! command -v apt-get >/dev/null; then
    warn "未检测到 apt-get，跳过系统包安装。请确保已装：build-essential wget curl git sqlite3"
else
    log "安装编译工具..."
    apt-get update -qq
    apt-get install -y -qq build-essential python3-dev wget curl git ca-certificates sqlite3 >/dev/null
fi
install_talib
install_uv

# -----------------------------------------------------
# 2. 创建系统用户与数据目录
# -----------------------------------------------------
if ! id -u "$APP_USER" &>/dev/null; then
    log "创建系统用户 $APP_USER"
    # 系统用户无登录权限，home 指向数据目录（uv 缓存等会写到 ~/.local）
    useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

log "创建数据目录 $DATA_DIR"
mkdir -p "$DATA_DIR/posts"
chown -R "$APP_USER":"$APP_USER" "$DATA_DIR"

# -----------------------------------------------------
# 3. 安装 Python 依赖
# -----------------------------------------------------
if [[ ! -d "$APP_DIR/.git" ]]; then
    die "代码目录 $APP_DIR 不存在或非 git 仓库，请先 git clone 到此路径。"
fi
if [[ ! -d "$BINANCE_SERVICE_DIR/.git" ]]; then
    warn "本地依赖 $BINANCE_SERVICE_DIR 不存在。pyproject.toml 声明了 binance-service 为 path 依赖，缺失会导致 uv sync 失败。"
fi

log "同步 Python 依赖（uv 会自动安装 Python 3.14）..."
sudo -u "$APP_USER" --set-home bash -lc "cd '$APP_DIR' && uv sync --frozen"

# 验证原生依赖
if ! sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -c "import talib" 2>/dev/null; then
    die "import talib 失败：TA-Lib C 库未正确安装或未 ldconfig"
fi
log "依赖检查通过"

# -----------------------------------------------------
# 4. 生成环境配置（仅首次创建，避免覆盖已填写的密钥）
# -----------------------------------------------------
mkdir -p "$ENV_DIR"
chmod 0750 "$ENV_DIR"
chown root:"$APP_USER" "$ENV_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    log "生成默认环境配置 $ENV_FILE（请按需编辑填入密钥）"
    cat > "$ENV_FILE" <<EOF
# Trading Service 环境配置（被 systemd EnvironmentFile 加载）
# 编辑后执行：sudo systemctl restart $APP_NAME

TRADING_HOST=0.0.0.0
TRADING_PORT=8001
TRADING_DEBUG=false

# 与 news-service 共享的 SQLite，两边路径必须一致
TRADING_DB_PATH=$DATA_DIR/news.db
TRADING_POSTS_DIR=$DATA_DIR/posts

TRADING_NEWS_SERVICE_BASE_URL=http://127.0.0.1:8000
TRADING_NEWS_SERVICE_TIMEOUT=30

# 按需填写密钥：
# TRADING_LLM_API_KEY=sk-xxx
# TRADING_LLM_MODEL=gpt-4o-mini
EOF
    chmod 0640 "$ENV_FILE"
    chown root:"$APP_USER" "$ENV_FILE"
    warn "已生成 $ENV_FILE，请编辑填入密钥后重启服务：sudo systemctl restart $APP_NAME"
else
    log "环境配置已存在，跳过（不覆盖）"
fi

# -----------------------------------------------------
# 5. 写入 systemd 服务文件
# -----------------------------------------------------
log "写入 systemd 服务文件"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Trading Service
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/python main.py

# 崩溃后 10 秒自动重启
Restart=always
RestartSec=10

# 优雅关闭：给 uvicorn lifespan 30 秒（关闭调度器 + 浏览器）
KillSignal=SIGTERM
TimeoutStopSec=30

StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

# -----------------------------------------------------
# 6. 启动
# -----------------------------------------------------
log "启用并启动服务..."
systemctl daemon-reload
systemctl enable "$APP_NAME" >/dev/null
systemctl restart "$APP_NAME"

sleep 2
if systemctl is-active --quiet "$APP_NAME"; then
    log "✅ 服务已启动并设为开机自启"
    log "状态：sudo systemctl status $APP_NAME"
    log "日志：sudo journalctl -u $APP_NAME -f"
    log "健康：curl http://127.0.0.1:8001/health"
else
    warn "服务可能未正常启动，查看日志：sudo journalctl -u $APP_NAME -n 50 --no-pager"
    exit 1
fi
