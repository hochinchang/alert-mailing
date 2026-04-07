#!/usr/bin/env bash
# deploy/setup.sh
# 在 Rocky Linux 9 上安裝 Python 3、pip、git，並建立虛擬環境
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/alert-notification-system}"
VENV_DIR="${APP_DIR}/venv"

echo "==> 更新系統套件..."
sudo dnf update -y

echo "==> 安裝 Python 3、pip、git..."
sudo dnf install -y python3 python3-pip git

echo "==> 確認版本..."
python3 --version
pip3 --version
git --version

echo "==> 建立應用程式目錄：${APP_DIR}"
sudo mkdir -p "${APP_DIR}"
sudo chown "$(whoami)":"$(whoami)" "${APP_DIR}"

echo "==> 建立 Python 虛擬環境：${VENV_DIR}"
python3 -m venv "${VENV_DIR}"

echo "==> 升級 pip..."
"${VENV_DIR}/bin/pip" install --upgrade pip

echo ""
echo "✓ 環境安裝完成。"
echo "  應用程式目錄：${APP_DIR}"
echo "  虛擬環境路徑：${VENV_DIR}"
echo ""
echo "下一步：執行 deploy/install.sh 部署專案。"
