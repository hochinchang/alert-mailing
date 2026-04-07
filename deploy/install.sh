#!/usr/bin/env bash
# deploy/install.sh
# 從 git clone 專案、安裝依賴、設定環境變數檔案
set -euo pipefail

REPO_URL="${REPO_URL:-}"
APP_DIR="${APP_DIR:-/opt/alert-notification-system}"
VENV_DIR="${APP_DIR}/venv"

# ---------------------------------------------------------------------------
# 取得或更新程式碼
# ---------------------------------------------------------------------------
if [ -d "${APP_DIR}/.git" ]; then
    echo "==> 更新現有專案..."
    git -C "${APP_DIR}" pull
else
    if [ -z "${REPO_URL}" ]; then
        echo "錯誤：請設定 REPO_URL 環境變數，例如："
        echo "  REPO_URL=https://github.com/your-org/alert-notification-system.git bash deploy/install.sh"
        exit 1
    fi
    echo "==> Clone 專案至 ${APP_DIR}..."
    git clone "${REPO_URL}" "${APP_DIR}"
fi

# ---------------------------------------------------------------------------
# 安裝 Python 依賴
# ---------------------------------------------------------------------------
echo "==> 安裝 Python 依賴套件..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

# ---------------------------------------------------------------------------
# 設定 .env
# ---------------------------------------------------------------------------
if [ ! -f "${APP_DIR}/.env" ]; then
    echo "==> 複製 .env.example 為 .env..."
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    echo ""
    echo "⚠️  請編輯 ${APP_DIR}/.env，填入以下實際值："
    echo "   DB_HOST       - 資料庫主機位址"
    echo "   DB_PORT       - 資料庫連接埠（預設 3306）"
    echo "   DB_USER       - 資料庫帳號"
    echo "   DB_PASSWORD   - 資料庫密碼"
    echo "   SMTP_PASSWORD - SMTP 郵件密碼"
    echo ""
    echo "   編輯指令：nano ${APP_DIR}/.env"
else
    echo "==> .env 已存在，略過複製。"
fi

# ---------------------------------------------------------------------------
# 複製 systemd service（若尚未安裝）
# ---------------------------------------------------------------------------
SERVICE_FILE="/etc/systemd/system/alert-notification.service"
if [ ! -f "${SERVICE_FILE}" ]; then
    echo "==> 安裝 systemd service..."
    sudo cp "${APP_DIR}/deploy/alert-notification.service" "${SERVICE_FILE}"
    sudo sed -i "s|/opt/alert-notification-system|${APP_DIR}|g" "${SERVICE_FILE}"
    sudo systemctl daemon-reload
    echo "   已安裝 ${SERVICE_FILE}"
fi

echo ""
echo "✓ 安裝完成。"
echo ""
echo "下一步："
echo "  1. 填寫 ${APP_DIR}/.env"
echo "  2. sudo systemctl enable alert-notification"
echo "  3. sudo systemctl start alert-notification"
echo "  4. sudo systemctl status alert-notification"
