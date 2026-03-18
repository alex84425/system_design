Docker Desktop already install
我想在 Docker Desktop（已啟用 K8s）上練習 Kubernetes。

## 環境
- Docker Desktop with Kubernetes enabled
- Single node cluster
- Mac / Windows（請問我是哪個再調整指令）

## 目標架構
我想建立以下結構：

Cluster
└── Node: docker-desktop
    ├── Namespace: my-practice
    ├── Deployment: my-app（管理 Pod 數量）
    │   ├── replicas: 2
    │   ├── Pod 1
    │   │   ├── container: server-a (port 8080, /health)
    │   │   ├── container: server-b (port 8081, /health)
    │   │   └── container: server-c (port 8082, /health)
    │   └── Pod 2
    │       ├── container: server-a (port 8080, /health)
    │       ├── container: server-b (port 8081, /health)
    │       └── container: server-c (port 8082, /health)
    └── Service: my-app-service（流量分配到 Pod）

## 每個 container 的設定
- 各自有獨立的 livenessProbe 和 readinessProbe 檢查 /health
- 任何一個 container 不健康 → 整個 Pod 重啟
- Pod 重啟期間 → Service 自動把流量切去另一個 Pod

## 我需要你幫我
1. 確認 Docker Desktop K8s 是否正常運作的指令
2. 產生完整可以直接 apply 的 YAML 檔案，包含：
   - Namespace
   - Deployment（multi-container pod, replicas: 2）
   - Service（NodePort，讓我可以用 localhost 訪問）
3. 逐步教我 apply 和驗證的指令
4. 教我怎樣模擬一個 Pod 掛掉，觀察 Service 自動切換到另一個 Pod

## 備注
- Image 先用 nginx 代替 server-a/b/c（因為我還沒有真實 image）
- 但 port 和 health check path 保持上面的設定
- 請解釋每個 YAML 欄位的意思