# 年度交接指南（Annual Handoff）

這份文件的目的：**讓下一任行政總醫師即使我（原開發者）已經離職，也能完整接手系統**。

App 本身（exe 使用 + 重新打包）已經是「雙擊即用」等級。真正需要人工轉移的是**綁在原開發者 Google / GitHub / LINE 帳號上的 4 個雲端資源**。

---

## 一、需要轉移的 4 個雲端資源

| # | 資源 | 目前擁有者 | 轉讓方式 |
|---|------|-----------|---------|
| 1 | GCP project + Service Account | 原開發者 Gmail | Google Cloud Console → IAM 加新 Owner |
| 2 | Google Sheet（病人資料表） | 原開發者 Gmail | 試算表 → 共用 → 變更擁有者 |
| 3 | GitHub repos（2 個） | `alexdodochen` | GitHub Settings → Transfer ownership |
| 4 | LINE Messaging API channel | 原開發者 LINE 帳號 | LINE Developers → Provider 加新 Admin |

---

## 二、交接前準備（原開發者做）

### Step 1：GCP project 轉讓

1. 登入 https://console.cloud.google.com/
2. 選擇專案 `sigma-sector-492215`（或當年使用的 project）
3. 左選單 → **IAM and Admin** → **IAM**
4. 點 **Grant Access** → 輸入新任 Gmail → 角色選 **Owner**
5. 新任確認收到後，原開發者移除自己（可延後幾天確認沒事再移）

### Step 2：建立新 Service Account、輪替 key

新任拿到 Owner 權限後：
1. GCP Console → **IAM and Admin** → **Service Accounts**
2. **Create Service Account** → 名稱 `admission-bot-YYYY`（當年度）
3. 角色選 **Editor**（或只給該 Sheet 的存取）
4. 建完後 → **Keys** → **Add Key** → **Create new key** → JSON → 下載
5. 用新 JSON 重新打包 exe（見 `BUILD.md`）
6. 舊 SA：IAM 頁面 → 禁用舊 key（Disable），**不要立即刪除**，等一週確認無問題再 Delete

### Step 3：Google Sheet 轉讓擁有者

1. 打開病人資料 Sheet
2. 右上 **共用（Share）**
3. 新任的 Gmail 已有編輯者權限 → 點旁邊下拉 → **設為擁有者（Make owner）**
4. 原開發者自動降為編輯者（可後續自己移除自己）

### Step 4：GitHub repos 轉讓

兩個 repo 都需要轉：

**Public app**: https://github.com/alexdodochen/public_daily_admission_app

1. Repo → **Settings** → 最底下 **Danger Zone** → **Transfer ownership**
2. 輸入新任 GitHub 使用者名稱 + repo 名稱確認
3. 新任登入 GitHub 接受邀請

**Private workflow/memory**: https://github.com/alexdodochen/daily-admission-list

同樣步驟。**注意**：這個 repo 含開發者 memory 和工作流程紀錄，轉讓前請先自行備份或清理個人註記。

### Step 5：LINE channel 轉讓

LINE Messaging API channel 沒有純「轉讓」功能，做法：

**做法 A（保留現有 channel、Bot 不換）**：
1. https://developers.line.biz/console/ 登入
2. 進入對應 Provider（例如「成醫心內」）
3. **Admins** 分頁 → **Add admin** → 輸入新任 LINE 帳號
4. 原開發者確認新任能進入後，移除自己

**做法 B（新任自建新 channel）**：
1. 新任自己建 Provider + Channel
2. 拿新的 Channel Access Token → 填進 exe 設定頁
3. 重新邀請 Bot 進群組
4. 舊 channel 停用

做法 A 較無痛（group ID 不變，排程不用改），但需要原開發者還能登入 LINE。**建議優先用 A，同時走 B 做 fallback**。

### Step 6：更新 exe 發給新任

```bash
cp <新的-SA>.json app/bundled/service_account.json
pyinstaller packaging.spec --noconfirm
```

把 `dist/admission-app/` 資料夾壓縮寄給新任。

---

## 三、新任接手後的驗證清單

確認以下每項都能自己做：

- [ ] 登入 https://console.cloud.google.com/ → 看得到 project，自己是 Owner
- [ ] 打開 Google Sheet → 檔案資訊顯示「擁有者：我」
- [ ] 登入 https://github.com/ → 看得到兩個 repo 在自己帳號下
- [ ] 登入 https://developers.line.biz/console/ → 看得到 channel，自己是 Admin
- [ ] 雙擊 `admission-app.exe` → 設定頁 3 格填完 → 能跑完一次完整流程（Step 1-6）
- [ ] 打開 `BUILD.md` → 能自己 `pyinstaller packaging.spec` 產生新 exe
- [ ] App 右上「檢查更新」按鈕能連上 GitHub

---

## 四、年度例行維護（新任接手後）

每年（或每次 cardiology fellowship 人員輪替）：

1. 若有新任行政總再接替 → 重跑本文件 Step 1-6
2. 若只是自己繼續用 → 一年輪替一次 SA key（Step 2 後半）
   - 禁用舊 key → 建新 key → 重 build exe → 發給自己

---

## 五、常見問題

**Q：原開發者已經離職聯絡不到，怎麼辦？**

- GCP：若原開發者還是 Owner 且沒回應 → 只能找 Google 申訴（很麻煩）→ **預防做法：交接前就要把新任升 Owner**
- Sheet：原開發者若是擁有者且失聯 → **檔案就無法轉移**，只能匯出資料、建新 Sheet、重跑 app 重新 key data。**預防做法：新任上任當天就把 Sheet 擁有者改掉**
- GitHub：repo 還看得到就可以 fork；若私有 repo 失聯就只剩 local clone 有的內容
- LINE：Admin 沒轉過去就沒辦法用原 channel → 新任自建新 channel

**Q：可以不轉 GCP，改成新任自建 project 嗎？**

可以但更麻煩：
- 新任自建 GCP project（免費）
- 建新 SA
- **原 Sheet 必須加新 SA 為編輯者**（所以 Sheet 那邊不轉也可以，共編即可）
- 重 build exe 帶新 SA
- 舊 SA 在原開發者的 GCP 停用

這條路適合「原開發者 GCP 有其他用途不想整個轉讓」的情境。

**Q：為什麼要轉 GitHub repo？我不寫 code**

- 若從此不再修改程式碼 → **不轉也可以**，繼續用現有 exe
- 但若未來要修 bug / 加功能 → 沒 repo 擁有權就沒辦法 push 更新
- 建議至少 fork 一份到新任自己帳號下做備份

---

## 六、設計原則

這份文件和 Phase 8 打包的設計原則是：

- **使用者（行政總醫師）**：零技術門檻，雙擊 exe + 填 3 格設定
- **維護者（有一點程式基礎的人）**：照 `BUILD.md` 能重新打包 exe
- **擁有者（現在的你）**：照本文件能把所有權轉出去，不卡在任何一個人身上

**關鍵：系統要能在任何一個人離開時繼續運作。**
