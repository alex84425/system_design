---
name: spec-interpretation
description: 用來解析使用者提供的規格，特別是帶有括號註解的別名（例如「(巢狀 block)」），確保在建模 UI schema 或 payload 時完全遵循。
---

# Spec Interpretation Skill（規格解析 Skill）

只要使用者提供自然語言規格（Markdown、條列、表格等），就先使用本 skill。目標是在寫程式前，把文字敘述轉成明確的模型與測試假設。

## 一、先解析結構

1. **尋找階層線索**：有序/無序清單、縮排、標題、編號通常代表父子關係。
2. **逐字複製 alias**：使用者寫的欄位名稱（含空白/大小寫）就是 JSON Schema `alias` / UI 標籤，除非另有說明。
3. **轉成快速 schema 摘要**：在動手寫程式前，先用 JSON / dict 片段重述階層，例如：
   ```json
   {
     "Regulatory Item": {
       "WF7": false,
       "WF7 Settings": {
         "WF7 Expected Value": "V",
         "WF7 Countries List": []
       }
     }
   }
   ```
   與使用者分享或自行檢查這個快照，可避免誤放巢狀區塊。

## 二、括號註記規則

規格中的括號（任何 `()` 包住的註解）**都視為權威別名或同義提示**，必須無條件遵守：

| 註記寫法 | 必須採用的解讀 |
| --- | --- |
| `(巢狀 block)`、`(nested)` | 表示這個項目是 **object / 巢狀子 Model**。所有屬性都要留在父 object 底下，不能提升到頁面層級。|

### 2.1 如何辨識「純註解」而非 alias

- 出現 `default`、`預設`、`說明`、`提示`、`註解` 等語意的括號（例：`(default 選擇這個)`）通常只是備註，**不要** 把內容塞進 enum/alias；只需在文件或 UI 說明中保留。
- 若括號描述的是行為或提醒（而非另一個正式名稱），一律視為註解。
- 無法確定時，先問使用者：「這個括號是正式名稱還是備註？」再決定是否放入 schema。

未來若出現新的註記（例如 `Label (foo)`、`Label (bar)`），就視為「Label 也叫 foo/bar」，並在程式、schema、測試中維持同樣對應。

## 三、動手前的確認清單

- **把條列轉成樹狀圖**：只要清單內提到「某區塊 + 子項目」，在模型草圖裡就照實做成巢狀物件。
- **先釐清假設**：如果樹中的任何節點不確定，先請使用者給 payload 範例或再問一次。
- **alias 保持一致**：寫測試或文件時，引用同一組 alias 字串，確保一旦需求改動就會立即被發現。
- **紀錄註記對應**：遇到新的括號同義詞就補進表格或文件，方便後續維護。
- **確認四大描述/分類欄位**：
  1. `/construct` description（回傳物的 `{"schema": {"description"}}`）
  2. `/build` description（回傳物的 `{"action": {"description"}}`）
  3. Overview description（`vcosmos-cloud-entry-config-file.json` 裡的 `noneDaemonDescription` / `daemonDescription`）
  4. Overview category（同檔案的 `category`，允許值：`Environment Preparing`、`Environment Recovery`、`Test Execution & Tools`，或缺省讓系統歸入 others）

  若使用者規格未提及上述任一欄位，必須主動追問，避免漏填。
- **UI 屬性不可擅加**：像 `disabled`、`mandatory`、`showHeading`、`toolTip`、`collapse` 等 `json_schema_extra` 設定，除非規格或現有 skill 明確要求，否則不要自行加入；想新增時需先向使用者確認。

依照此流程，就能自動滿足像「(巢狀 block)」之類的速記，避免規格與實作 schema 之間出現落差。
