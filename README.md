# AstroGraph（阶段二可联调版）

基于你的需求与技术文档生成，当前版本已升级为“核心功能联调版”：

- 前后端可运行
- CSV 扫描与加载
- 基于 CSV 的混合检索与问答（本地哈希向量 + BM25）
- 后端文本语料扩展（txt/md/jsonl/json，后端接口，不改前端）
- 内存图谱构建 + 可选 Neo4j 写入
- 模型未上传时自动降级到规则/检索问答
- 多轮会话问答（session_id）
- 路径发现（多跳）
- 用户注册/登录与问答历史
- 可视化数据接口（图谱、对比、时间线）
- GraphRAG 追踪接口（意图/检索/上下文/生成）
- Three.js 3D 星图点云 + ECharts 图谱渲染

## 当前状态说明

- `Astronomical Image and CSV Dataset` 体量大，暂未接入本仓库
- 训练模型暂未上传，图像识别和高质量问答先返回占位结果
- 知识图谱构建将在你上传 CSV 后执行（接口已预留）

## 项目结构

- `backend`：FastAPI 后端（问答、检索、图谱、图像接口）
- `frontend`：Vue 3 + Vite 前端（问答演示、状态面板）
- `compose.yaml`：本地依赖服务模板（Neo4j、MinIO、Milvus）

## 快速启动

### 1) 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

后端地址：`http://localhost:8000`  
接口文档：`http://localhost:8000/docs`

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:5173`

## 环境变量

参考：

- `backend/.env.example`
- `frontend/.env.example`

## 已实现的核心接口

- `POST /api/v1/data/scan`：扫描 CSV 目录
- `POST /api/v1/data/load`：加载 CSV 到内存
- `POST /api/v1/data/ingest-text`：后端导入文本语料扩充知识库
- `POST /api/v1/retrieval/search`：检索数据
- `POST /api/v1/qa/ask`：问答（模型未就绪时走规则/检索）
- `POST /api/v1/graphrag/query`：GraphRAG流程追踪问答
- `POST /api/v1/graph/build`：构建图谱（可选写入 Neo4j）
- `GET /api/v1/graph/paths`：预览关系路径
- `GET /api/v1/graph/path`：路径发现
- `POST /api/v1/auth/register`、`POST /api/v1/auth/login`：用户体系
- `GET /api/v1/user/history`：问答历史
- `GET /api/v1/visualization/*`：图谱可视化数据接口

## 你后续上传模型后的步骤

1. 将训练好的推理代码接入 `backend/models/custom_model.py`
2. 调用 `POST /api/v1/model/load` 完成模型热加载
3. 上传 CSV 后调用 `POST /api/v1/graph/build`
4. 可选：调用 `POST /api/v1/graph/export-cypher` 导出图谱脚本

这就是最终交付需要你手动做的两件事：**换模型 + 给CSV**。

## 说明

当前阶段目标仍是“可运行 + 可扩展 + 可演示”，不阻塞你后续模型训练与大数据接入流程。
