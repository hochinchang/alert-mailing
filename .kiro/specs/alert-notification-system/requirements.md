# 需求文件

## 簡介

告警通知系統（Alert Notification System）負責定期從 DiskStatus、SystemStatus、FileStatus 三個資料庫的 CheckList 表讀取最新快照，依據預先設定的條件規則評估每筆資料，當資料符合告警條件時，自動透過 E-mail 通知指定的相關人員。本系統旨在提升問題的即時可見性，減少人工監控的負擔。

## 詞彙表

- **Alert_System**：告警通知系統，本文件所描述的主體系統。
- **Alert_Rule**：用於判斷監控資料是否需要觸發告警的條件規則，由管理員設定。
- **Alert_Event**：當監控資料符合 Alert_Rule 時所產生的告警事件。
- **Notification**：因 Alert_Event 而發送的 E-mail 通知。
- **Recipient**：接收 Notification 的指定人員，與 Alert_Rule 關聯。
- **Email_Service**：負責實際發送 E-mail 的外部服務或元件。
- **Evaluator**：負責將監控資料與 Alert_Rule 進行比對評估的元件。
- **Notifier**：負責組裝並透過 Email_Service 發送 Notification 的元件。
- **DiskStatus**：監控各伺服器磁碟使用率的資料庫，包含 CheckList 與 Status 兩張表。
- **SystemStatus**：監控各伺服器系統負載與記憶體使用率的資料庫，包含 CheckList、Status、SystemIPList 三張表。
- **FileStatus**：監控各類型雷達與 DS 設備檔案狀態的資料庫，包含多組 CheckList 與 Status 表。
- **CheckList 表**：各資料庫中存放最新一筆狀態快照的表，採 upsert 方式維護，以 IP（及 FileSystem 或 FileName 等）為主鍵。
- **Status 表**：各資料庫中存放歷史紀錄的表。
- **Used**：DiskStatus 中磁碟使用率欄位，單位為百分比（%）。
- **Load_1 / Load_5 / Load_15**：SystemStatus 中系統 1 分鐘、5 分鐘、15 分鐘平均負載欄位。
- **MemoryUSE**：SystemStatus 中記憶體使用率欄位，單位為百分比（%）。
- **FileTime**：FileStatus 中記錄檔案最後更新時間的欄位（Unix timestamp 或 float 格式）。
- **DiffTime**：FileStatus 中預先計算的檔案延遲欄位（資料庫儲存值），本系統不直接使用此欄位作為告警依據。
- **FileLag**：系統在評估時即時計算的值，定義為「當前時間 - FileTime」，單位為分鐘，代表檔案距今的延遲時間。
- **FileType**：FileStatus 中用於區分雷達（radar）、DS、HF 雷達等設備類型的欄位。
- **Threshold**：告警閾值，Alert_Rule 中定義的數值上限，超過此值即觸發告警。
- **Target_Host**：執行 Alert_System 的遠端主機，作業系統為 Rocky Linux 9。
- **MySQL_Connector**：Alert_System 連接 MySQL 資料庫所使用的驅動程式（如 `PyMySQL` 或 `mysql-connector-python`）。

---

## 需求

### 需求 1：從資料庫讀取監控資料

**使用者故事：** 身為系統管理員，我希望系統能定期從各資料庫的 CheckList 表讀取最新快照，以便及時偵測需要告警的事件。

#### 驗收標準

1. THE Alert_System SHALL 依照設定的排程週期，從以下資料來源讀取最新快照：
   - DiskStatus.CheckList（欄位：IP、ServerTime、FileSystem、Used）
   - SystemStatus.CheckList（欄位：IP、ServerTime、Load_1、Load_5、LOAD_15、MemoryUSE）
   - FileStatus.radarFileCheck（欄位：IP、FileName、FileType、FileTime、DiffTime）
   - FileStatus.DSFileCheck（欄位：IP、FileName、FileType、FileTime、DiffTime）
   - FileStatus.HFradarFileCheck（欄位：IP、FileName、FileType、FileTime、DiffTime）
2. WHEN 任一資料庫連線失敗，THE Alert_System SHALL 記錄錯誤日誌並於下一個排程週期重試，且不影響其他資料庫的讀取作業。
3. WHEN 任一 CheckList 表回傳空結果，THE Alert_System SHALL 結束該資料來源的本次處理且不產生任何 Alert_Event。
4. THE Alert_System SHALL 以 CheckList 表的最新快照作為評估依據，不重複讀取 Status 歷史表。

---

### 需求 2：評估監控資料是否符合告警條件

**使用者故事：** 身為系統管理員，我希望系統能根據預先設定的規則自動判斷監控資料是否需要告警，以便減少人工篩選的工作。

#### 驗收標準

1. WHEN Alert_System 讀取到監控資料，THE Evaluator SHALL 將每筆資料與所有啟用中的 Alert_Rule 進行比對。
2. WHEN 監控資料符合至少一條 Alert_Rule，THE Evaluator SHALL 產生對應的 Alert_Event，並記錄觸發的欄位名稱、實際數值與 Threshold。
3. WHEN 監控資料不符合任何 Alert_Rule，THE Evaluator SHALL 不產生 Alert_Event。
4. THE Alert_Rule SHALL 支援以下條件類型，對應實際監控欄位：
   - **磁碟使用率告警**：WHEN DiskStatus.CheckList 中某 IP 的 Used 超過 Threshold，THE Evaluator SHALL 產生 Alert_Event，包含 IP、FileSystem、Used 數值。
   - **系統負載告警**：WHEN SystemStatus.CheckList 中某 IP 的 Load_1、Load_5 或 LOAD_15 超過 Threshold，THE Evaluator SHALL 產生 Alert_Event，包含 IP、對應負載欄位名稱與數值。
   - **記憶體使用率告警**：WHEN SystemStatus.CheckList 中某 IP 的 MemoryUSE 超過 Threshold，THE Evaluator SHALL 產生 Alert_Event，包含 IP 與 MemoryUSE 數值。
   - **檔案延遲告警**：WHEN FileStatus 任一 CheckList 表中某筆記錄的 FileLag（即當前時間 - FileTime）超過 Threshold，THE Evaluator SHALL 產生 Alert_Event，包含 IP、FileName、FileType、FileTime 與計算出的 FileLag 數值。
5. IF Alert_Rule 設定格式無效，THEN THE Evaluator SHALL 記錄錯誤日誌並跳過該條規則，繼續處理其餘規則。

---

### 需求 3：發送 E-mail 告警通知

**使用者故事：** 身為相關人員，我希望在系統偵測到告警事件時能立即收到 E-mail 通知，以便快速採取對應行動。

#### 驗收標準

1. WHEN Alert_Event 產生，THE Notifier SHALL 向與該 Alert_Rule 關聯的所有 Recipient 發送 Notification。
2. THE Notification SHALL 包含以下資訊：Alert_Event 發生時間、觸發的 Alert_Rule 名稱、來源 IP、監控資料類型（磁碟／系統負載／記憶體／檔案延遲）、觸發欄位名稱、實際數值與 Threshold。
3. WHEN Email_Service 發送成功，THE Notifier SHALL 記錄發送成功的日誌，包含 Recipient 地址與 Alert_Event 識別碼。
4. IF Email_Service 發送失敗，THEN THE Notifier SHALL 依照設定的重試次數進行重試，並在所有重試均失敗後記錄錯誤日誌。
5. THE Alert_System SHALL 確保同一 Alert_Event 對同一 Recipient 僅發送一次 Notification，避免重複通知。

---

### 需求 4：管理告警規則

**使用者故事：** 身為系統管理員，我希望能新增、修改及停用告警規則，以便靈活調整告警條件而無需修改程式碼。

#### 驗收標準

1. THE Alert_System SHALL 支援透過設定檔或管理介面新增 Alert_Rule。
2. WHEN Alert_Rule 被停用，THE Evaluator SHALL 在下一次排程週期起不再使用該規則進行比對。
3. THE Alert_Rule SHALL 包含以下必要欄位：規則名稱、監控資料類型、目標欄位、Threshold 數值、以及至少一位 Recipient。
4. IF 新增的 Alert_Rule 缺少必要欄位，THEN THE Alert_System SHALL 拒絕該規則並回傳描述性錯誤訊息。

---

### 需求 6：部署與執行環境

**使用者故事：** 身為系統管理員，我希望能將程式碼透過 git 部署到遠端主機並穩定執行，以便在不修改本機環境的情況下維運告警系統。

#### 驗收標準

1. THE Alert_System SHALL 在 Rocky Linux 9 的 Target_Host 上執行，不依賴本機開發環境。
2. THE Alert_System SHALL 使用 MySQL 作為資料庫，透過 MySQL_Connector 連接 DiskStatus、SystemStatus、FileStatus 三個資料庫。
3. THE Alert_System SHALL 透過 git 進行程式碼部署，Target_Host 上執行 `git pull` 即可取得最新版本。
4. THE Alert_System SHALL 提供 `requirements.txt`，列出所有 Python 套件依賴，以便在 Target_Host 上透過 `pip install -r requirements.txt` 完成環境安裝。
5. THE Alert_System 的資料庫連線設定（主機位址、帳號、密碼）SHALL 透過設定檔或環境變數管理，不得硬編碼於程式碼中。
6. THE Alert_System SHALL 提供部署說明文件（README），包含在 Rocky Linux 9 上的安裝步驟、設定方式與啟動指令。

---

### 需求 5：系統可觀測性

**使用者故事：** 身為系統管理員，我希望能追蹤系統的運作狀況與告警歷史，以便進行問題排查與稽核。

#### 驗收標準

1. THE Alert_System SHALL 記錄每次排程執行的開始時間、結束時間、各資料來源讀取的資料筆數、以及產生的 Alert_Event 數量。
2. THE Alert_System SHALL 保存所有 Alert_Event 的歷史紀錄，包含觸發時間、來源 IP、監控資料類型、觸發欄位、實際數值、對應的 Alert_Rule、以及通知狀態。
3. WHEN Alert_System 啟動，THE Alert_System SHALL 記錄目前載入的 Alert_Rule 數量與 Recipient 總數。
