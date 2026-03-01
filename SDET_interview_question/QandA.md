具體邊界例子：

字串欄位：空字串、最大長度、最大長度 +1
數字欄位：0、負數、最大值、小數點
必填欄位：缺少其中一個

異常情境（Negative）

錯誤格式（送 string 給 int 欄位）
未授權（沒帶 token，或 token 過期）
不存在的資源（GET /users/99999）
重複操作（同一筆資料 POST 兩次，應該回 409 還是 idempotent？）
Server 端壓力（rate limit 觸發 429）
