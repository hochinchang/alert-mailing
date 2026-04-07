# Alert Notification System

定期從 DiskStatus、SystemStatus、FileStatus 資料庫讀取監控快照，依規則評估後自動發送 E-mail 告警通知的後端服務。

## 系統需求

- Rocky Linux 9
- Python 3.9+
- MySQL（DiskStatus、SystemStatus、FileStatus、AlertSystem 資料庫）
- SMTP 郵件伺服器

## 部署步驟

### 1. 在目標主機上安裝環境

```bash
# clone 專案（首次）
git clone https://github.com/your-org/alert-notification-system.git /opt/alert-notification-system
cd /opt/alert-notification-system

# 安裝系統依賴並建立虛擬環境
bash deploy/setup.sh
```

### 2. 部署專案與安裝 Python 依賴

```bash
# 設定 REPO_URL 後執行（首次 clone）
REPO_URL=https://github.com/your-org/alert-notification-system.git bash deploy/install.sh

# 若已 clone，直接執行即可（會自動 git pull）
bash deploy/install.sh
```

### 3. 填寫環境變數

```bash
nano /opt/alert-notification-system/.env
```

填入以下實際值：

```dotenv
DB_HOST=your_db_host
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
SMTP_PASSWORD=your_smtp_password
```

### 4. 設定告警規則

編輯 `config/rules.yaml`，依需求新增或修改告警規則：

```yaml
rules:
  - name: "磁碟使用率過高"
    source: disk
    field: Used
    threshold: 90.0
    recipients:
      - admin@example.com
    enabled: true
```

### 5. 建立服務帳號（建議）

```bash
sudo useradd --system --no-create-home --shell /sbin/nologin alertsvc
sudo chown -R alertsvc:alertsvc /opt/alert-notification-system
```

### 6. 啟用並啟動 systemd 服務

```bash
# 安裝 service 檔案（install.sh 已自動執行，手動安裝如下）
sudo cp deploy/alert-notification.service /etc/systemd/system/
sudo systemctl daemon-reload

# 設定開機自動啟動
sudo systemctl enable alert-notification

# 啟動服務
sudo systemctl start alert-notification

# 確認狀態
sudo systemctl status alert-notification
```

## 日常維運

### 查看日誌

```bash
# 即時日誌
sudo journalctl -u alert-notification -f

# 最近 100 行
sudo journalctl -u alert-notification -n 100
```

### 更新程式碼

```bash
cd /opt/alert-notification-system
git pull
sudo systemctl restart alert-notification
```

### 停止 / 重啟服務

```bash
sudo systemctl stop alert-notification
sudo systemctl restart alert-notification
```

## 設定檔說明

| 檔案 | 說明 |
|------|------|
| `config/rules.yaml` | 告警規則、資料庫連線、SMTP、排程設定 |
| `.env` | 敏感資訊（密碼等），不納入版本控制 |

### 告警規則欄位

| 欄位 | 說明 | 必填 |
|------|------|------|
| `name` | 規則名稱（唯一） | ✓ |
| `source` | 資料來源：`disk` / `system` / `file` | ✓ |
| `field` | 目標欄位：`Used` / `Load_1` / `Load_5` / `LOAD_15` / `MemoryUSE` / `FileLag` | ✓ |
| `threshold` | 告警閾值（超過即觸發） | ✓ |
| `recipients` | 收件人 E-mail 列表（至少一位） | ✓ |
| `enabled` | 是否啟用（預設 `true`） | |

## 目錄結構

```
alert-notification-system/
├── src/               # 核心模組
├── tests/             # 測試
├── config/
│   └── rules.yaml     # 告警規則設定
├── deploy/
│   ├── setup.sh       # 環境安裝腳本
│   ├── install.sh     # 專案部署腳本
│   └── alert-notification.service  # systemd unit file
├── main.py            # 程式進入點
├── requirements.txt
└── .env.example       # 環境變數範本
```