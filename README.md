# 每日入院名單 — 本地版 App

讓每位使用者在**自己的電腦**跑這個工作流程，用**自己的 LLM 帳號**（Claude / Gemini / ChatGPT 任選）當大腦。所有資料、API key、Google 憑證都存在本機 `app/data/config.json`，不上傳任何地方。

> 這是 repo 主工作流的**互動式封裝**。背後仍然使用 `gspread` 對使用者自己的 Google Sheet 寫入，和 Playwright 驅動 EMR / WEBCVIS。

## 1. 安裝

```bash
# 建議用乾淨的 venv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 如果要用 Step 3 EMR 擷取 / Step 5 導管排程，再裝 Playwright browser
playwright install chromium
```

## 2. 準備自己的帳號

| 項目 | 怎麼拿 |
| --- | --- |
| **LLM API key**（擇一） | Claude：https://console.anthropic.com/ / ChatGPT：https://platform.openai.com/api-keys / Gemini：https://aistudio.google.com/app/apikey（有免費 tier） |
| **Google Service Account JSON** | [Google Cloud Console → IAM → 服務帳戶 → 建立金鑰（JSON）](https://console.cloud.google.com/iam-admin/serviceaccounts) |
| **Spreadsheet ID** | 你的 Google Sheet 網址 `docs.google.com/spreadsheets/d/<這段>/edit` |

> 把服務帳號 email 加入該試算表的「編輯者」權限。

## 3. 啟動

```bash
python -m app.run
```

瀏覽器會自動開到 `http://127.0.0.1:8766/`。第一次會進**設定頁**，填完按「儲存」→「測試連線」→ 兩個都 ✓ 就可以回首頁開始用。

## 4. 六步驟工作流

| 步驟 | 做什麼 |
| --- | --- |
| ① **匯入名單** | 拖曳住院名單截圖 → LLM 辨識成 A-L 欄表格 → 檢視/修正病歷號 → 寫入 Sheet |
| ② **抽籤排序** | 讀主資料 + 抽籤表 → 設定每位醫師籤數 → Round-robin → 寫 N-S |
| ③ **EMR 摘要** | 自己登入 EMR 後貼 session URL → Playwright 帶 session 抓 SOAP → LLM 產 4 段摘要 |
| ④ **入院序整合** | 讀醫師子表格 F/G → 合併回 N-W（保留 V/W 手動標記） |
| ⑤ 導管排程 | 尚未 port，仍需跑 repo 裡的 `cathlab_keyin_*.py` |
| ⑥ LINE 推播 | 尚未 port，仍由 Render LINE bot 觸發 |

## 5. 檔案結構

```
app/
  main.py           # FastAPI 路由
  run.py            # 啟動器
  config.py         # 設定 I/O（JSON 存 app/data/）
  llm/
    __init__.py     # get_llm() 工廠 + 三家 provider metadata
    base.py         # LLMClient 抽象 + extract_json
    anthropic_provider.py / openai_provider.py / gemini_provider.py
  services/
    sheet_service.py    # 用使用者的服務帳號 + Sheet ID
    ocr_service.py      # Step 1
    lottery_service.py  # Step 2
    emr_service.py      # Step 3
    ordering_service.py # Step 4
  templates/        # Jinja2 HTML
  static/           # CSS + 前端 JS（無框架）
  data/             # config.json（gitignore）
```

## 6. 常見問題

**Q: 我不想用 Claude，只想用免費的 Gemini**
在設定頁選「Gemini (Google)」→ 貼 AIza 開頭的 API key。程式碼自動切換。

**Q: EMR 網址每家醫院不一樣怎麼辦**
`app/services/emr_service.py` 的 `fetch_raw_html()` 是預設用 NCKUH EMR pattern。別的機構請自己改 `page.fill(...)` 的 selector；我們只抽取 `div.small` 內容。

**Q: 可以多人共用一個 Google Sheet 嗎？**
可以。每個人的服務帳號各自加到試算表就行，操作互不干擾（FastAPI 是單人用，不做併發鎖）。

**Q: 我的 API key 會被傳到哪裡？**
只在本機 `app/data/config.json`（純文字 JSON）。要保護請檔案加密或放在 OS keychain，這版沒做。
