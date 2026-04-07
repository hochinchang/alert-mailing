# 任務清單：告警通知系統（Alert Notification System）

## 任務

- [x] 1. 專案初始化與設定
  - [x] 1.1 建立專案目錄結構（src/、tests/、config/）
  - [x] 1.2 建立 `requirements.txt`，加入依賴套件（APScheduler、PyYAML、Hypothesis、PyMySQL）
  - [x] 1.3 建立 `config/rules.yaml` 設定檔範本，包含各類型規則範例、databases、email、scheduler 設定區塊
  - [x] 1.4 建立 `.env.example`，列出 DB_HOST、DB_USER、DB_PASSWORD、SMTP_PASSWORD 等環境變數
  - [x] 1.5 建立 `.gitignore`，排除 `.env`、`__pycache__/`、`*.pyc`、`logs/`

- [x] 2. 資料模型定義
  - [x] 2.1 實作 `AlertRule` dataclass，包含 name、source、field、threshold、recipients、enabled 欄位
  - [x] 2.2 實作 `DiskRecord`、`SystemRecord`、`FileRecord` dataclass
  - [x] 2.3 實作 `AlertEvent` dataclass，包含 event_id、triggered_at、rule_name、source_ip、data_type、field_name、actual_value、threshold、extra、recipients 欄位
  - [x] 2.4 實作 `FetchResult` dataclass，包含三類資料列表與 fetch_time

- [x] 3. RuleLoader（規則載入器）
  - [x] 3.1 實作 `RuleLoader.load()`，從 YAML 設定檔讀取並回傳 `list[AlertRule]`
  - [x] 3.2 實作 `RuleLoader.validate()`，驗證必要欄位（name、source、field、threshold、recipients），缺少時回傳 None 並記錄 WARNING 日誌
  - [x] 3.3 撰寫單元測試：驗證正常載入、缺少欄位被拒絕、無效 YAML 格式處理
  - [x] 3.4 撰寫屬性測試（屬性 10）：對任意缺少必要欄位的規則字典，validate() 應回傳 None
    - Hypothesis 策略：隨機從必要欄位集合中移除一或多個欄位

- [ ] 4. DataFetcher（資料讀取器）
  - [x] 4.1 實作 `DataFetcher.__init__()`，接受各資料庫連線設定，使用 PyMySQL 建立連線
  - [x] 4.2 實作 `fetch_disk_status()`，查詢 DiskStatus.CheckList，回傳 `list[DiskRecord]`
  - [x] 4.3 實作 `fetch_system_status()`，查詢 SystemStatus.CheckList，回傳 `list[SystemRecord]`
  - [x] 4.4 實作 `fetch_file_status()`，查詢 FileStatus 三張 CheckList 表，回傳 `list[FileRecord]`（含 source_table 欄位）
  - [x] 4.5 實作 `fetch_all()`，整合三個方法，各自獨立 try/except，失敗時記錄 ERROR 日誌並回傳空列表
  - [x] 4.6 撰寫單元測試：以 mock PyMySQL cursor 驗證 SQL 查詢目標為 CheckList 表、空結果回傳空列表
  - [x] 4.7 撰寫屬性測試（屬性 1）：隨機讓某個資料來源拋出例外，驗證其他來源結果不受影響
  - [ ] 4.8 撰寫屬性測試（屬性 2）：任意資料來源回傳空列表時，對應的 FetchResult 欄位應為空列表

- [x] 5. Evaluator（評估器）
  - [x] 5.1 實作 `Evaluator.__init__()`，接受 `RuleLoader` 實例
  - [x] 5.2 實作磁碟使用率評估邏輯：DiskRecord.used > rule.threshold 時產生 AlertEvent
  - [x] 5.3 實作系統負載評估邏輯：Load_1/Load_5/LOAD_15 > rule.threshold 時產生 AlertEvent
  - [x] 5.4 實作記憶體使用率評估邏輯：SystemRecord.memory_use > rule.threshold 時產生 AlertEvent
  - [x] 5.5 實作檔案延遲評估邏輯：計算 FileLag = (fetch_time - file_time) / 60，FileLag > rule.threshold 時產生 AlertEvent；file_time 無效時記錄 WARNING 並跳過；FileLag 為負值時視為 0
  - [x] 5.6 實作 `Evaluator.evaluate()`，整合所有評估邏輯，跳過 enabled=False 的規則
  - [x] 5.7 實作 event_id 生成：sha256(rule_name + ":" + ip + ":" + field_name + ":" + schedule_cycle_timestamp)
  - [x] 5.8 撰寫單元測試：各類型告警的具體範例、FileLag 邊界值（None、負值）
  - [x] 5.9 撰寫屬性測試（屬性 3）：對任意資料數值與閾值，評估結果應與 actual_value > threshold 的布林值一致
  - [x] 5.10 撰寫屬性測試（屬性 4）：混入無效規則後，有效規則的評估結果應與純有效規則時相同
  - [x] 5.11 撰寫屬性測試（屬性 9）：停用規則不應產生 AlertEvent，即使資料超過閾值

- [x] 6. DedupeStore（去重狀態儲存）
  - [x] 6.1 實作 `DedupeStore` 介面（抽象基底類別）：`is_sent(event_id, recipient) -> bool`、`mark_sent(event_id, recipient) -> None`
  - [x] 6.2 實作 `MySQLDedupeStore`，使用 PyMySQL 將已發送紀錄寫入 AlertSystem.alert_dedupe 表（欄位：event_id、recipient、sent_at）
  - [x] 6.3 實作 `MySQLDedupeStore.init_table()`，若 alert_dedupe 表不存在則自動建立
  - [x] 6.4 實作 `InMemoryDedupeStore`，供測試使用
  - [x] 6.5 撰寫單元測試：mark_sent 後 is_sent 應回傳 True；未 mark 的應回傳 False

- [x] 7. EmailService（郵件服務）
  - [x] 7.1 實作 `EmailService.send(to, subject, body) -> bool`，使用 smtplib 透過 SMTP 發送郵件
  - [x] 7.2 實作郵件內文格式化，包含 Alert_Event 所有必要欄位
  - [x] 7.3 撰寫單元測試：驗證郵件主旨與內文包含所有必要資訊

- [x] 8. Notifier（通知器）
  - [x] 8.1 實作 `Notifier.__init__()`，接受 `EmailService` 與 `DedupeStore` 實例
  - [x] 8.2 實作 `Notifier.notify()`：對每個 AlertEvent 的每位 Recipient，先查詢 DedupeStore，未發送則呼叫 EmailService.send()
  - [x] 8.3 實作重試邏輯：依設定的 retry_count 進行重試，全部失敗後記錄 ERROR 日誌；失敗時不更新 DedupeStore
  - [x] 8.4 發送成功後呼叫 DedupeStore.mark_sent() 並記錄 INFO 日誌
  - [x] 8.5 撰寫屬性測試（屬性 5）：對任意 AlertEvent 與收件人列表，EmailService.send 的呼叫次數應等於收件人數量
  - [x] 8.6 撰寫屬性測試（屬性 6）：對任意 AlertEvent，組裝的郵件內文應包含所有必要欄位
  - [x] 8.7 撰寫屬性測試（屬性 7）：EmailService 持續失敗時，呼叫總次數應為 retry_count + 1
  - [x] 8.8 撰寫屬性測試（屬性 8）：多次呼叫 notify() 時，同一（event_id, recipient）組合的實際發送次數應恰好為 1

- [x] 9. EventLogger（事件歷史紀錄）
  - [x] 9.1 實作 `EventLogger.init_table()`，若 AlertSystem.alert_events 表不存在則自動建立（欄位：event_id、triggered_at、rule_name、source_ip、data_type、field_name、actual_value、threshold、extra_json、notify_status）
  - [x] 9.2 實作 `EventLogger.save(event: AlertEvent) -> None`，將 AlertEvent 寫入 MySQL alert_events 表
  - [x] 9.3 實作 `EventLogger.get(event_id: str) -> AlertEvent | None`，依 event_id 查詢歷史紀錄
  - [x] 9.4 撰寫屬性測試（屬性 11）：對任意 AlertEvent，save 後 get 應回傳欄位一致的紀錄

- [x] 10. Scheduler 與 Pipeline 整合
  - [x] 10.1 實作 `Pipeline.run()`，依序執行 DataFetcher → Evaluator → Notifier → EventLogger，並記錄排程執行日誌（開始時間、結束時間、各來源筆數、事件數量）
  - [x] 10.2 實作 `Scheduler`，使用 APScheduler 依設定週期呼叫 `Pipeline.run()`
  - [x] 10.3 實作啟動時日誌：記錄載入的 Alert_Rule 數量與 Recipient 總數
  - [x] 10.4 撰寫整合測試：模擬完整管線執行一個週期，驗證端對端流程（使用 mock DB 與 mock EmailService）

- [x] 11. 主程式進入點
  - [x] 11.1 實作 `main.py`，讀取設定檔、初始化所有元件、啟動 Scheduler
  - [x] 11.2 處理 SIGTERM/SIGINT 信號，優雅關閉 Scheduler

- [x] 12. 部署至 Rocky 9 主機
  - [x] 12.1 建立 `deploy/setup.sh`，在 Rocky 9 上安裝 Python 3、pip、git，並建立虛擬環境
  - [x] 12.2 建立 `deploy/install.sh`，從 git clone 專案、安裝 `requirements.txt` 依賴、複製 `.env.example` 為 `.env` 並提示填入實際值
  - [x] 12.3 建立 `deploy/alert-notification.service`（systemd unit file），設定開機自動啟動與 Restart=on-failure
  - [x] 12.4 建立 `README.md`，說明部署步驟：git clone → setup.sh → 填寫 .env → systemctl enable/start
