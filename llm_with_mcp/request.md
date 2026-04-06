![alt text](image.png)

你能猜出要怎麼做的嗎?

create plan can be create by given json to 對應API

how to get the json schema of create plan

已知有json schema is from python pydantic model

# 問題核心

圖片描述的功能：

> 整合 LLM 與 MCP server，讓使用者用**自然語言**建立 test plan，大幅降低 onboarding 時間。

---

## 問題拆解

```
使用者自然語言 → LLM → MCP Tool → create plan API (JSON) → 後端
```

**已知條件：**

1. 後端有一個 `create plan` API，接受 JSON payload
2. 該 JSON schema 來自 Python Pydantic model
3. 目標：讓 LLM 理解 schema，把自然語言轉成合法 JSON 並呼叫 API

---

## 關鍵技術問題：如何取得 JSON Schema？

**Pydantic v2：**

```python
from pydantic import BaseModel

class CreatePlanRequest(BaseModel):
    name: str
    description: str
    test_cases: list[str]

# 取得 JSON Schema
schema = CreatePlanRequest.model_json_schema()
print(schema)
```

**Pydantic v1：**

```python
schema = CreatePlanRequest.schema()
```

---

## 系統架構

```
┌──────────────┐     自然語言      ┌─────────────────┐
│   使用者      │ ──────────────→  │   LLM (Claude)  │
└──────────────┘                  └────────┬────────┘
                                           │ tool call
                                           ↓
                                  ┌─────────────────┐
                                  │   MCP Server    │
                                  │  Tool: create_  │
                                  │  plan(json)     │
                                  └────────┬────────┘
                                           │ HTTP POST
                                           ↓
                                  ┌─────────────────┐
                                  │  create plan API│
                                  └─────────────────┘
```

---

# 列出所需要技術

| 層次        | 技術                                             |
| ----------- | ------------------------------------------------ |
| Schema 定義 | Python Pydantic model                            |
| Schema 傳遞 | MCP tool description 內嵌 JSON Schema            |
| LLM 推理    | Claude / GPT（支援 tool use / function calling） |
| MCP Server  | `mcp` Python SDK（`@mcp.tool()` decorator）      |
| API 呼叫    | `httpx` / `requests` 在 MCP tool handler 內呼叫  |

---

## 核心邏輯（MCP tool 範例）

```python
import mcp
import httpx
from pydantic import BaseModel

class CreatePlanRequest(BaseModel):
    name: str
    description: str
    test_cases: list[str]

@mcp.tool(
    description=f"Create a test plan. Schema: {CreatePlanRequest.model_json_schema()}"
)
async def create_plan(payload: CreatePlanRequest) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://your-api/plans",
            json=payload.model_dump()
        )
    return response.json()
```

**重點：** MCP tool 的 description 直接內嵌 Pydantic schema → LLM 自動知道要填哪些欄位。

---

## 下一步建議

1. 確認 Pydantic model 在哪個 repo / service
2. 確認 create plan API endpoint 及認証方式
3. 建立 MCP Server 包裝這個 API
4. 選擇 LLM host（local Claude Desktop / remote）

# 實做要求

1.use uv 管理環境2. 自己假設一個簡單的test plan,原本是打request,現在你先只要echo只要user fit model

2.  input 自然語言只包含 只給兩個參數
    if create plan需要三個參數
    怎處理?
3.  可以開始實做
    LLM 用你自己
    MCP 你要自己架設

---

# 實做紀錄

## 專案結構

```
llm_with_mcp/
├── server.py        ← MCP Server（含 Pydantic model + create_plan tool）
├── client.py        ← 模擬 MCP client 呼叫
├── pyproject.toml   ← uv 管理依賴
└── .venv/           ← uv 自動建立
```

---

## Step 1：初始化 uv 專案 & 安裝依賴

```bash
cd llm_with_mcp
uv init --no-readme
uv add mcp pydantic
```

**Output：**

```
Initialized project `llm-with-mcp`
Creating virtual environment at: .venv
Installed 32 packages in 3.10s
 + mcp==1.26.0
 + pydantic==2.12.5
 + httpx==0.28.1
 + uvicorn==0.42.0
 ...
```

---

## Step 2：定義 Pydantic Model（server.py）

```python
class TestCase(BaseModel):
    title: str
    steps: list[str]
    expected_result: str

class CreatePlanRequest(BaseModel):
    plan_name: str
    description: str
    test_cases: list[TestCase]
```

**重點**：`CreatePlanRequest.model_json_schema()` 把這個結構轉成 JSON Schema 並內嵌進 MCP tool description，讓 LLM 知道要填哪些欄位、格式為何。

---

## Step 3：建立 MCP Tool（server.py）

```python
@mcp.tool(
    description=(
        "Create a test plan from natural language. "
        f"JSON Schema: {CreatePlanRequest.model_json_schema()}"
    )
)
def create_plan(plan_name: str, description: str, test_cases: list[dict]) -> str:
    payload = CreatePlanRequest(
        plan_name=plan_name,
        description=description,
        test_cases=test_cases,
    )
    return json.dumps({"status": "ok (echo mode)", "received": payload.model_dump()}, ensure_ascii=False)
```

**echo mode**：目前不打真實 API，只做 Pydantic validate 後原樣回傳，確認 LLM 填的資料是合法的。

---

## Step 4：建立 MCP Client（client.py）

```python
async def main():
    params = StdioServerParameters(command="uv", args=["run", "python", "server.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("create_plan", { ... })
            print(result.content[0].text)
```

**重點**：client **自動 spawn** server process，透過 stdio 溝通，不需要手動先啟動 server。

---

## Step 5：執行

```bash
cd llm_with_mcp
uv run python client.py
```

**Output：**

```json
{
    "status": "ok (echo mode)",
    "received": {
        "plan_name": "電商結帳流程測試計畫",
        "description": "驗證使用者從加入購物車到完成付款的完整流程，確保各步驟功能正常",
        "test_cases": [
            {
                "title": "加入商品至購物車",
                "steps": [
                    "開啟商品頁面",
                    "選擇商品尺寸與數量",
                    "點擊「加入購物車」按鈕",
                    "查看購物車圖示數量"
                ],
                "expected_result": "購物車顯示正確商品數量，商品資訊（名稱、價格、數量）正確"
            },
            {
                "title": "填寫收件資訊",
                "steps": [
                    "點擊「前往結帳」",
                    "輸入姓名、電話、地址",
                    "選擇配送方式",
                    "點擊「下一步」"
                ],
                "expected_result": "成功進入付款頁面，收件資訊顯示正確"
            },
            {
                "title": "信用卡付款",
                "steps": [
                    "輸入信用卡號碼",
                    "輸入有效期限與 CVV",
                    "點擊「確認付款」"
                ],
                "expected_result": "顯示訂單確認頁面，收到訂單確認 email"
            }
        ]
    }
}
```

---

## 完整資料流

```
client.py
  │
  ├─ spawn → server.py (stdio)
  │
  ├─ MCP initialize handshake
  │
  ├─ call_tool("create_plan", { plan_name, description, test_cases })
  │             ↓
  │         Pydantic validates CreatePlanRequest
  │             ↓
  │         echo JSON back
  │
  └─ print result
```

---

## 下一步（接真實 API）

將 server.py 的 echo 換成真實 HTTP call：

```python
import httpx

async def create_plan(...) -> str:
    payload = CreatePlanRequest(...)
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://your-api/plans", json=payload.model_dump())
    return resp.text
```
