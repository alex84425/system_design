# Chat Room Protocol 比較

## Polling（輪詢）

**原理**：client 定期（e.g. 每 N 秒）主動發 HTTP request 問 server 有無新訊息。

| | 說明 |
|---|---|
| **優點** | 實作簡單；相容所有瀏覽器與環境 |
| **缺點** | 大量無效請求（沒訊息也一直問）；延遲高（取決於輪詢間隔）；server 資源浪費 |

---

## Long Polling（長輪詢）

**原理**：client 發出 HTTP request 後，server 不立刻回應，而是 hold 住連線直到有新訊息或 timeout 才回覆；client 收到後立刻再發一次。

| | 說明 |
|---|---|
| **優點** | 比 polling 即時；不需要 WebSocket 支援；防火牆相容性佳 |
| **缺點** | 仍需反覆重建連線（半雙工）；server 需維持大量懸掛連線；訊息量大時效率差；傳送端無法用同一機制推送（sender/receiver 可能在不同 server） |

---

## WebSocket

**原理**：建立一條持久的全雙工（full-duplex）TCP 連線，server/client 雙向都可主動推送訊息。

| | 說明 |
|---|---|
| **優點** | 真正全雙工，延遲最低；連線建立後 overhead 極小；適合即時聊天、線上遊戲等高頻場景 |
| **缺點** | 實作與維運較複雜（連線管理、重連機制）；需要有狀態的 server（或搭配訊息佇列做水平擴展）；少數老舊防火牆/proxy 可能不支援 |

---

## 小結（chat system 推薦）

- **傳訊（送 & 收）**：WebSocket — 低延遲、全雙工
- **非即時功能**（登入、取歷史訊息、個人設定）：一般 HTTP / REST 即可

---

## 1 Billion Users 規模挑戰

### 數量估算

| 指標 | 估算 |
|---|---|
| DAU | ~500M（50% of 1B） |
| 同時在線連線數 | ~50M–100M WebSocket 長連線 |
| 每天訊息量 | ~50B+ messages/day（每人平均 100 則） |
| 每秒訊息峰值 | ~數百萬 msg/s |

### 協議面的壓力

| 協議 | 在 1B scale 的問題 |
|---|---|
| Polling | 無法承受：每秒產生天文數字的無效 HTTP 請求 |
| Long Polling | server 需維持數千萬懸掛連線，記憶體爆炸；load balancer sticky session 難做 |
| **WebSocket** | 每台 chat server 約可維持 **10萬~100萬** 條連線（視 memory/CPU）；需水平擴展到數百台 |

### 架構應對方案

```
Client
  │  WebSocket
  ▼
Chat Server 群（stateful，水平擴展）
  │  publish
  ▼
Message Queue（Kafka / RabbitMQ）   ← 解耦、削峰、持久化
  │  consume
  ▼
Chat Server（推送給 receiver）
```

**關鍵設計決策：**

1. **Chat Server 水平擴展**
   - 每台 server 維持一批 WebSocket 連線
   - 需搭配 **Service Discovery**（e.g. ZooKeeper）讓 sender side 知道 receiver 在哪台 server

2. **訊息佇列（Kafka）**
   - sender 把訊息 publish 到 Kafka topic
   - receiver 所在的 chat server subscribe 後推送
   - 確保訊息不遺失、可重放

3. **訊息儲存（Message Storage）**
   - 熱資料：**Key-Value store**（e.g. HBase / Cassandra）— 高寫入吞吐、依 `channel_id + timestamp` 做 row key
   - 歷史訊息：object storage（S3）歸檔

4. **Presence Service（線上狀態）**
   - 獨立服務維護 user online/offline
   - 用 **heartbeat**（e.g. 每 5 秒）更新；斷線後 30 秒標記 offline
   - 發布訂閱（Pub/Sub）通知好友清單

5. **Push Notification（離線推送）**
   - 用戶不在線時走 APNs / FCM
   - Chat server 偵測 user offline → 轉發給 Notification Service

