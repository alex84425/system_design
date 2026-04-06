# K8s 基本概念

---

## Q1：Pod 和 Node 的概念與差異？

### Node（節點）

Node 是**實體或虛擬機器**，是 K8s 叢集中真正跑程式的機器。  
每個 Node 上由 K8s 管理一組系統元件（kubelet、kube-proxy、container runtime）。

```
Cluster
├── Node A（實體/VM，例如 t3.medium）
├── Node B（實體/VM）
└── Node C（實體/VM）
```

### Pod（容器組）

Pod 是 K8s 最小的**部署單位**，內部包含一或多個 Container。  
同一個 Pod 裡的 Container 共享：

- 同一個 IP（localhost 互通）
- 同一份儲存（Volume）
- 同一個生命週期（一起起、一起死）

Pod 跑在 Node 上，一個 Node 可以跑多個 Pod。

### 對比表

| 維度   | Node                    | Pod                           |
| ------ | ----------------------- | ----------------------------- |
| 本質   | 機器（VM / 實體機）     | 一組 Container 的封裝         |
| 資源   | CPU、記憶體、磁碟       | 使用 Node 的資源              |
| IP     | 機器 IP                 | 每個 Pod 有自己的叢集內 IP    |
| 數量   | 通常幾台到幾十台        | 可能幾十到上千個              |
| 誰管理 | Cloud Provider / 你自己 | K8s Scheduler 自動分配到 Node |

### 視覺化關係

```
Cluster
└── Node A (IP: 192.168.1.10, 8 CPU, 32GB RAM)
    ├── Pod 1 (IP: 10.1.0.1)
    │   ├── container: service_A
    │   └── container: service_B
    └── Pod 2 (IP: 10.1.0.2)
        └── container: service_C

└── Node B (IP: 192.168.1.11, 8 CPU, 32GB RAM)
    └── Pod 3 (IP: 10.1.0.3)
        ├── container: service_A
        └── container: service_B
```

---

## Q2：SaaS 產品有 service_A、service_B、service_C，K8s 怎麼 Scaling 並避免服務下線？

### 架構設計

實際 SaaS 產品中，每個 service 通常會**各自獨立部署成一個 Deployment + Service**（微服務架構）。  
這樣可以對個別服務做 scale，而不影響其他服務。

```
Cluster
├── Namespace: production
│
├── Deployment: service-a  →  Pod × N
├── Deployment: service-b  →  Pod × N
├── Deployment: service-c  →  Pod × N
│
├── Service: service-a-svc  （ClusterIP，流量導向 service-a pods）
├── Service: service-b-svc
├── Service: service-c-svc
│
└── Ingress（對外入口，路由規則）
```

### 避免服務下線的關鍵機制

#### 1. Replicas（多副本）

```yaml
spec:
    replicas: 3 # 同時跑 3 個 Pod，掛一個還有兩個頂著
```

#### 2. Rolling Update（滾動更新）

```yaml
strategy:
    type: RollingUpdate
    rollingUpdate:
        maxUnavailable: 1 # 更新時最多允許 1 個 Pod 不可用
        maxSurge: 1 # 更新時最多額外多開 1 個 Pod
```

> 部署新版本時，K8s 會先起新 Pod、確認健康後，才關舊 Pod。Zero Downtime Deploy。

#### 3. Readiness Probe（就緒探針）

```yaml
readinessProbe:
    httpGet:
        path: /health
        port: 8080
    initialDelaySeconds: 5
    periodSeconds: 5
```

> 新 Pod 啟動後，K8s 確認 `/health` 回傳 200 才把流量導過去。  
> 沒過 readiness check 的 Pod 不會收到任何請求。

#### 4. Liveness Probe（存活探針）

```yaml
livenessProbe:
    httpGet:
        path: /health
        port: 8080
    initialDelaySeconds: 10
    periodSeconds: 10
    failureThreshold: 3
```

> 連續 3 次失敗 → K8s 自動 restart 該 Pod。

#### 5. HPA（Horizontal Pod Autoscaler）— 自動 Scaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
    name: service-a-hpa
spec:
    scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: service-a
    minReplicas: 2
    maxReplicas: 10
    metrics:
        - type: Resource
          resource:
              name: cpu
              target:
                  type: Utilization
                  averageUtilization: 70 # CPU 超過 70% 就自動擴展
```

> 流量暴增時自動加 Pod，流量降低時自動縮減，無需人工介入。

#### 6. PodDisruptionBudget（PDB）— 維護期間保護

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
    name: service-a-pdb
spec:
    minAvailable: 2 # 任何時刻至少要有 2 個 Pod 在線
    selector:
        matchLabels:
            app: service-a
```

> Node 維護、升級時，K8s 不會一次把所有 Pod 都驅逐走。

### 完整保護流程圖

```
使用者請求
    │
    ▼
Ingress（入口）
    │
    ▼
Service（負載均衡，只把流量給 Ready 的 Pod）
    │
    ├──▶ Pod 1 ✅ （service_A/B/C，readiness OK）
    ├──▶ Pod 2 ✅
    └──▶ Pod 3 ❌ （liveness fail → K8s 自動重啟，重啟期間不收流量）

當流量增加：
HPA 偵測到 CPU > 70% → 自動新增 Pod 4, 5...

當部署新版本：
Rolling Update → 先起新 Pod → 通過 readiness → 才刪舊 Pod
```

### 結論

| 機制            | 解決的問題                 |
| --------------- | -------------------------- |
| Replicas ≥ 2    | 單點故障，一個掛了還有備援 |
| Rolling Update  | 部署新版不中斷服務         |
| Readiness Probe | 確保流量只進健康的 Pod     |
| Liveness Probe  | 自動重啟卡死的 Pod         |
| HPA             | 流量暴增時自動擴容         |
| PDB             | Node 維護時不讓服務斷線    |

2. 為什麼需要 Cluster？(核心價值)
   有了 Cluster，你不再需要關心你的 SaaS 服務具體在哪台電腦上運行。你只需要跟「大腦」溝通：

你 (開發者)：「幫我跑 5 個 service_A 的 Pod。」
Cluster (大腦)：「沒問題。我看 Node 1 現在很閒，跑 3 個；Node 2 資源還夠，跑 2 個。分配完畢！」
