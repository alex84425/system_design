| 特性     | Proxy（代理）                                | Gateway（網關）                                   |
| -------- | -------------------------------------------- | ------------------------------------------------- |
| 主要功能 | 轉發請求、隱藏後端伺服器身份。               | 路由、協議轉換、身分驗證、流量控制。              |
| 處理層級 | 通常在網路層/傳輸層（L3/L4）或應用層（L7）。 | 專注於應用層（L7）的業務邏輯。                    |
| 透明度   | 對客戶端通常是透明的（像是中繼站）。         | 客戶端必須知道網關的存在（作為唯一的 API 入口）。 |
| 典型例子 | Nginx、HAProxy、Squid。                      | Kong、Tyk、AWS API Gateway、Azure APIM。          |

## 關鍵組件與最佳實踐

- **路由與代理（Routing & Proxying）**：扮演反向代理的角色，利用第七層（Layer-7）路由將客戶端請求導向正確的微服務。

- **安全與認證（Security & Authentication）**：集中處理身分驗證（如 JWT 驗證）、SSL 憑證卸載（Termination），以及透過流量限制（Rate Limiting/Throttling）來保護後端服務。

- **效能與效率（Performance & Efficiency）**：保持網關輕量化以避免延遲。利用異步通訊機制；若針對全球用戶，可配合 GeoDNS 部署區域性網關。

- **請求聚合（Request Aggregation）**：將多個後端請求合併為單一客戶端請求，減少連線往返次數。

- **彈性與韌性（Resiliency）**：實作斷路器模式（Circuit Breaker），防止連線失敗產生連鎖效應導致系統崩潰。

- **設計模式（Design Patterns）**：
    - 小型系統：採用中心化邊緣網關（Centralized Edge Gateway）。
    - 高流量系統：採用雙層架構（Two-tier Approach）。
    - 高度分散式系統：採用微網關（Microgateways）。
