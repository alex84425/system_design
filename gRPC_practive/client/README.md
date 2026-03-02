# gRPC Client (Local)

代表前端，在 local 執行，透過 gRPC 呼叫 Docker 裡的 server_A。

## 前置需求

安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/)：

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 備用（pip）：若 curl 因 SSL 受限（如 Netskope 環境）
pip install uv
```

## 安裝依賴

```bash
cd client
uv sync

# 備用（pip）
pip install grpcio grpcio-tools --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

## 生成 gRPC Stub（proto → python）

```bash
uv run python generate_proto.py

# 備用（直接 python）
python generate_proto.py
```

執行後會在 `client/` 目錄產生 `hello_pb2.py` 和 `hello_pb2_grpc.py`。

## 啟動 server（Docker）

```bash
# 在 gRPC_practive/ 目錄下
docker compose up --build
```

## 執行 Client

```bash
cd client
uv run python client.py
```

預期輸出：

```
Will try to greet world ...
Connecting to localhost:50051...
Greeter client received: Hello, Local Client User!
```
