# Redis 與鎖 (Redis & Locking)

## 0. 先釐清:Redis 跟樂觀/悲觀鎖是「不同層」的東西

- **樂觀鎖 / 悲觀鎖** → 是 **DB 層** 的概念,解決「同一筆資料被併發修改」。
  見 [[optimistic-vs-pessimistic-locking]]。
- **Redis** → 通常擋在 **DB 前面**,目的是「讓流量根本不要打到 DB」。

> 所以在講 DB 鎖的文件裡沒看到 Redis 是**正常的** —— 它們不是同一層。

```
   流量 ──→ Redis(擋/預扣)──→ MQ(削峰)──→ DB(樂觀/悲觀鎖)
            ^擋住大部分                     ^最後少量才落庫
```

---

## 1. Redis 三種用法,對應不同概念

| Redis 用法 | 本質 | 對應概念 |
|---|---|---|
| `DECR` / `INCR` 預扣庫存、計數 | **原子操作** | 不是樂觀也不是悲觀,靠單執行緒原子性 |
| `SET key val NX EX` 分散式鎖 | **搶鎖、別人等** | ≈ **悲觀鎖**(跨服務版) |
| `WATCH / MULTI / EXEC` 交易 | **提交前驗證** | ≈ **樂觀鎖**(Redis 的 CAS) |

---

## 2. 用法 A:原子預扣庫存(秒殺最常見)

Redis 是 **單執行緒** 處理指令,`DECR` 本身就是原子的,不會兩個請求同時扣到同一個值 → **天生防超賣**,不需要額外加鎖。

```
DECR stock        # 原子扣減,回傳扣完後的值
```

```
10萬請求 → Redis DECR (原子,擋住超賣)
         → 只有前 N 個結果 >= 0 → 才放行打 DB
         → 其餘直接回「售罄」,DB 完全沒被打到
```

實務上會用 Lua 腳本把「判斷 + 扣減」包成一個原子操作:

```lua
-- KEYS[1]=stock_key
if tonumber(redis.call('GET', KEYS[1])) > 0 then
    return redis.call('DECR', KEYS[1])
else
    return -1   -- 售罄
end
```

> 重點:這裡**既不是樂觀也不是悲觀**,是靠「原子指令 / 單執行緒」省掉鎖。

---

## 3. 用法 B:分散式鎖(≈ 悲觀鎖)

DB 的鎖只在單一 DB 內有效。當有**多台機器 / 多個服務**要搶同一個資源,就需要跨服務的鎖 → Redis 分散式鎖。

```
SET lock_key <uuid> NX EX 10    # NX:不存在才設成功=搶到鎖;EX:自動過期防死鎖
... 做事 ...
-- 用 Lua 確保「是自己的鎖才刪」,避免刪到別人的
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
```

注意事項:
- **一定要設過期時間 (EX)** → 否則持鎖的機器掛了會永久死鎖。
- **value 放唯一 uuid** → 釋放時驗證是自己的鎖,別誤刪別人。
- **任務比過期時間長怎麼辦?** → 用 **看門狗 (watchdog)** 自動續期。生產級直接用 **Redisson**(內建看門狗)。
- **要更嚴謹** → **Redlock** 演算法(多個獨立 Redis 節點過半數才算成功)。

本質 = **悲觀鎖思路**(先搶鎖、搶不到的等或放棄),只是把鎖從 DB 內搬到跨服務的 Redis。

---

## 4. 用法 C:WATCH/MULTI/EXEC(≈ 樂觀鎖)

Redis 內建的樂觀鎖:`WATCH` 一個 key,如果在 `EXEC` 前那個 key 被別人改動,整個交易會失敗(回 nil),需重試。

```
WATCH stock
val = GET stock
if val > 0:
    MULTI
    DECR stock
    EXEC        # 若 stock 在 WATCH 後被改過 → EXEC 失敗 → 重試
```

本質 = **樂觀鎖**(提交前驗證有沒有被動過,失敗就重試)。

---

## 5. 總結

> - Redis 跟 DB 鎖是**不同層**;在 DB 鎖文件沒看到 Redis 很正常。
> - **預扣庫存** → 用 Redis **原子操作 (DECR)**,不需要鎖。
> - **跨服務搶資源** → Redis **分散式鎖 (SET NX)**,≈ 悲觀鎖,生產用 Redisson。
> - **Redis 內 CAS** → `WATCH/MULTI/EXEC`,≈ 樂觀鎖。
> - 秒殺典型架構:**Redis 預扣 → MQ 削峰 → DB 落庫(樂觀鎖兜底)**。

延伸:[[optimistic-vs-pessimistic-locking]]、[[keyword]](下訂單失敗 / Saga)
