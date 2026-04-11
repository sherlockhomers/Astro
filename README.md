<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.x-42b883?logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Three.js-3D-000000?logo=threedotjs&logoColor=white" alt="Three.js" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/License-MIT-blue" alt="License" />
</p>

<h1 align="center">星智穹图 AstroVista</h1>
<p align="center"><strong>智能体协同与检索增强下的天文科普视界平台</strong></p>
<p align="center">An AI-powered interactive astronomy education platform with RAG, Knowledge Graph, and Multimodal exploration.</p>

---

## 📖 项目简介

**星智穹图**是一个面向中文用户的交互式天文科普智能平台，融合了自适应 RAG（检索增强生成）、知识图谱、多模态 AI 和 3D 可视化技术，为天文爱好者和学习者提供从「提问」到「图谱探索」再到「3D 天体交互」的一站式科普体验。

> 中国计算机设计大赛 · 软件应用与开发 · Web 应用与开发赛道

### 核心特性

- **🤖 智能问答引擎** — 自适应 RAG Agent 架构，支持意图分析、多源混合检索、流式 SSE 输出、多轮对话
- **🕸️ 知识图谱可视化** — ECharts 力导向图、多跳路径推理、实体对比分析、GraphRAG 推理追踪
- **🖼️ 图像检索** — 基于 CLIP ViT-B/32 的向量相似度搜索，支持以文搜图 / 以图搜图
- **🌍 3D 天体交互** — Three.js 渲染行星模型，太阳系真实轨道参数可视化
- **🔭 前沿资讯** — NASA APOD 每日星图、NeoWs 近地小行星数据、arXiv 天文论文实时拉取
- **🌌 深空天图** — Aladin Lite 嵌入，接入 CDS 天文巡天影像数据

---

## 🏗️ 技术架构

```
┌─────────────────── 前端展示层 ───────────────────┐
│  Vue 3 + Vite + TypeScript                        │
│  Element Plus · Three.js · ECharts · Aladin Lite  │
│  SSE 流式渲染 · Pinia 状态管理                     │
└───────────────── REST / SSE ─────────────────────┘
                       ↕
┌─────────────────── 后端服务层 ───────────────────┐
│  FastAPI (Python)                                 │
│  自适应 RAG Agent · GraphRAG · 事实护栏            │
│  CLIP 图像服务 · Explore Bundle 聚合              │
└──────────────────────────────────────────────────┘
                       ↕
┌──── AI 模型层 ────┐  ┌──────── 数据层 ──────────┐
│ AstroSage-8B      │  │ SQLite + NetworkX        │
│ AstroLLaVA        │  │ Milvus (向量)            │
│ CLIP ViT-B/32     │  │ Neo4j (图数据库, 可选)   │
│ GPT-4o-mini (可选)│  │ MinIO (对象存储, 可选)   │
└───────────────────┘  │ Redis (缓存, 可选)       │
                       └──────────────────────────┘
```

---

## 📁 项目结构

```
Astro/
├── frontend/               # Vue 3 前端
│   ├── src/
│   │   ├── views/          # 页面组件 (Landing, QA, Knowledge, Starfield...)
│   │   ├── components/     # 通用组件 (GraphChart, CelestialModel3D...)
│   │   ├── router/         # Vue Router 路由配置
│   │   ├── stores/         # Pinia 状态管理
│   │   └── api.ts          # API 客户端
│   ├── package.json
│   └── .env.example
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── routers/        # API 路由 (qa, graph, image, landing...)
│   │   ├── services/       # 业务逻辑 (qa_service, graphrag, milvus_clip...)
│   │   ├── deps.py         # 依赖注入 & 服务容器
│   │   ├── config.py       # 配置管理
│   │   └── main.py         # FastAPI 入口
│   ├── models/             # AI 模型适配器
│   ├── data/               # 内置知识库语料
│   ├── vendor/             # 第三方模型 (AstroLLaVA)
│   ├── scripts/            # 数据处理脚本
│   ├── requirements.txt
│   └── .env.example
├── data/                   # 数据文件
├── infra/                  # 基础设施配置 (Milvus)
├── scripts/                # 项目启动脚本
├── compose.yaml            # Docker Compose (Neo4j, MinIO, Milvus, Redis)
├── requirements.txt        # Python 根依赖
└── environment.yml         # Conda 环境配置
```

---

## 🚀 快速启动

### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 后端运行环境 |
| Node.js | 18+ | 前端构建工具 |
| npm | 9+ | 包管理器 |
| Docker（可选） | 20+ | 运行 Neo4j / Milvus / MinIO / Redis |

### 1. 克隆项目

```bash
git clone https://github.com/sherlockhomers/Astro.git
cd Astro
```

### 2. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，根据需要修改配置（见下方环境变量说明）

# 启动服务
uvicorn app.main:app --reload --port 8000
```

后端地址：http://localhost:8000
API 文档：http://localhost:8000/docs

### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env

# 启动开发服务器
npm run dev
```

前端地址：http://localhost:5173

### 4. 可选：启动基础设施服务

如需使用 Neo4j 图数据库、Milvus 向量数据库、MinIO 对象存储或 Redis 缓存：

```bash
# 在项目根目录
docker compose up -d
```

启动后在 `backend/.env` 中开启对应配置：

```env
NEO4J_ENABLED=true
MILVUS_ENABLED=true
MINIO_ENABLED=true
```

---

## ⚙️ 环境变量配置

### 后端 (`backend/.env`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CSV_ROOT` | 空 | CSV 数据目录或 Excel 文件路径 |
| `IMAGE_BASE_DIRS` | 空 | 图片根目录（逗号分隔） |
| `AUTO_BUILD_GRAPH_ON_STARTUP` | `true` | 启动时自动构建知识图谱 |
| `NEO4J_ENABLED` | `false` | 是否启用 Neo4j |
| `MILVUS_ENABLED` | `false` | 是否启用 Milvus 向量数据库 |
| `MINIO_ENABLED` | `false` | 是否启用 MinIO 对象存储 |
| `STARWHISPER_ENABLED` | `false` | 是否启用 StarWhisper 本地模型 |
| `STARWHISPER_MODEL_PATH` | 空 | 本地模型权重路径 |
| `AUTH_SECRET` | `change-this-secret` | JWT 签名密钥（请修改） |
| `DYNAMIC_ENABLED` | `true` | 是否启用 NASA Exoplanet 动态数据 |

### 前端 (`frontend/.env`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | 后端 API 地址 |

> 完整配置参见 `backend/.env.example`

---

## 🔌 API 接口概览

| 模块 | 端点 | 说明 |
|------|------|------|
| **认证** | `POST /api/v1/auth/register` | 用户注册 |
| | `POST /api/v1/auth/login` | 用户登录 |
| **问答** | `POST /api/v1/qa/ask` | 智能问答（支持 SSE 流式） |
| | `POST /api/v1/qa/ask-with-image` | 图文多模态问答 |
| **图谱** | `POST /api/v1/graph/build` | 构建知识图谱 |
| | `GET /api/v1/graph/paths` | 关系路径预览 |
| | `POST /api/v1/graph/multi-path` | 多跳路径发现 |
| **GraphRAG** | `POST /api/v1/graphrag/query` | GraphRAG 推理追踪问答 |
| **检索** | `POST /api/v1/retrieval/search` | 混合检索 |
| **图像** | `POST /api/v1/image/search-by-text` | 以文搜图 |
| | `POST /api/v1/image/search-by-image` | 以图搜图 |
| **数据** | `POST /api/v1/data/scan` | 扫描数据目录 |
| | `POST /api/v1/data/load` | 加载数据 |
| **可视化** | `GET /api/v1/visualization/*` | 图谱可视化数据 |
| **Landing** | `GET /api/v1/landing/apod` | NASA 每日天文图片 |
| | `GET /api/v1/landing/frontier` | arXiv 前沿论文 |

> 完整接口文档：启动后端后访问 http://localhost:8000/docs

---

## 🛠️ 技术栈

### 前端

| 技术 | 用途 |
|------|------|
| Vue 3 + Vite | 核心框架 & 构建工具 |
| TypeScript | 类型安全 |
| Element Plus | UI 组件库 |
| Three.js | 3D 天体渲染 |
| ECharts | 知识图谱 & 数据可视化 |
| Aladin Lite | 深空天图嵌入 |
| Pinia | 状态管理 |
| Axios | HTTP 客户端 |

### 后端

| 技术 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| SQLite + Alembic | 数据持久化 |
| NetworkX | 内存知识图谱 |
| Sentence-Transformers | 文本向量化 |
| OpenCLIP (ViT-B/32) | 图像向量化 |
| SSE (Server-Sent Events) | 流式问答推送 |

### AI 模型

| 模型 | 用途 |
|------|------|
| AstroSage-8B | 天文专业问答（本地） |
| AstroLLaVA | 多模态图文理解 |
| CLIP ViT-B/32 | 图像-文本向量匹配 |
| GPT-4o-mini | 云端质量增强（可选） |

### 基础设施（可选）

| 服务 | 用途 |
|------|------|
| Neo4j | 图数据库持久化 |
| Milvus | 向量数据库 |
| MinIO | 对象存储 |
| Redis | 缓存加速 |
| Docker Compose | 容器编排 |

---

## 📊 数据来源

| 数据源 | 说明 |
|--------|------|
| [Astronomical Image and CSV Dataset](https://www.kaggle.com/) | 天文影像与结构化数据 |
| [NASA APOD API](https://api.nasa.gov/) | 每日天文图片 |
| [NASA NeoWs API](https://api.nasa.gov/) | 近地小行星实时数据 |
| [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) | 系外行星数据 |
| [arXiv API](https://arxiv.org/) | 天文学前沿论文 (astro-ph) |
| [CDS Aladin](https://aladin.cds.unistra.fr/) | 天文巡天影像数据 |

---

## 🔧 开发指南

### 前端开发

```bash
cd frontend
npm run dev      # 开发模式（HMR 热更新）
npm run build    # 生产构建
npm run preview  # 预览构建产物
```

### 后端开发

```bash
cd backend
uvicorn app.main:app --reload --port 8000   # 开发模式
```

### 数据处理脚本

```bash
cd backend

# 构建知识图谱（从 CSV）
python scripts/build_kg_from_csv.py

# 构建向量索引
python scripts/build_vector_index.py

# CLIP 图像索引（需要 Milvus）
python scripts/index_milvus_clip.py

# 导入高质量语料
python scripts/ingest_hq_astronomy_corpus.py
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
