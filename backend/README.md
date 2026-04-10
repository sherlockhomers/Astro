# Backend（FastAPI）

## 启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 关键接口

- `GET /health`
- `GET /api/v1/model/status`
- `POST /api/v1/model/load`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/system/status`
- `POST /api/v1/data/scan`
- `POST /api/v1/data/load`
- `POST /api/v1/data/ingest-text`（后端扩展文本知识库，不改前端）
- `POST /api/v1/data/ingest-text/clear`
- `GET /api/v1/data/status`
- `POST /api/v1/qa/ask`
- `POST /api/v1/qa/ask-with-image`
- `POST /api/v1/graphrag/query`
- `POST /api/v1/retrieval/search`
- `GET /api/v1/retrieval/vector-schema`
- `POST /api/v1/graph/build`
- `POST /api/v1/graph/export-cypher`
- `GET /api/v1/graph/status`
- `GET /api/v1/graph/schema-summary`
- `GET /api/v1/graph/paths`
- `GET /api/v1/graph/path`
- `POST /api/v1/graph/cypher`
- `GET /api/v1/visualization/graph`
- `GET /api/v1/visualization/compare`
- `GET /api/v1/visualization/timeline`
- `GET /api/v1/visualization/starfield`
- `GET /api/v1/user/history`
- `POST /api/v1/image/predict`
- `POST /api/v1/image/search-by-image`（query：`page`、`page_size`；兼容 `top_k`）
- `GET /api/v1/image/search-by-text`（同上）
- `GET /api/v1/image/vector-status`（Milvus 连接、索引条数、CLIP 是否已加载）
- `GET /api/v1/image/list`
- `GET /api/v1/image/detail/{image_id}`
- `GET /api/v1/image/file/{image_id}`
- `GET /api/v1/metrics`

## 模型与数据未就绪策略

- 模型适配器未加载：问答走规则与检索，不阻塞联调
- 数据源未加载：检索与问答给出明确提示，可先在前端执行“扫描/加载数据源”
- `NEO4J_ENABLED=false`：图谱仅构建在内存；开启后可写入 Neo4j
- 用户认证使用轻量 token（开发阶段方案）

## 最终交付接入步骤（你要的流程）

1. 把训练好的模型接到 `models/custom_model.py`（按 `models/README.md` 约定）
2. 通过 `POST /api/v1/model/load` 加载模型，`GET /api/v1/model/status` 验证
3. 上传数据源（CSV目录或Excel）后调用 `POST /api/v1/graph/build`
4. 如需离线导入 Neo4j，调用 `POST /api/v1/graph/export-cypher` 导出 Cypher

## StarWhisper 直连（已接入适配器）

`models/custom_model.py` 已改为 StarWhisper 适配器，按下面配置即可切换：

1. 在 `.env` 中设置：

```bash
STARWHISPER_ENABLED=true
STARWHISPER_MODEL_PATH=D:/models/starwhisper-checkpoint
STARWHISPER_TOKENIZER_PATH=D:/models/starwhisper-checkpoint
STARWHISPER_LAZY_LOAD=true
```

2. 安装依赖并重启后端：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

3. 验证：
- `GET /api/v1/model/status`：`loaded=true` 且 `supports_qa=true`
- `POST /api/v1/model/load`：可热加载适配器

若权重未配置或加载失败，系统会自动回退到现有检索问答链路，不会阻塞主流程。
本地目录模式下会自动校验权重分片完整性（`pytorch_model.bin.index.json` 对应的 `pytorch_model-xxxxx.bin`）。

## 后续扩展点

- `app/services/qa_service.py`：替换为 GraphRAG + LLM
- `app/services/retrieval_service.py`：替换为 ES + Milvus + Neo4j 混合检索
- `app/services/graph_service.py`：按需求增强实体映射、关系抽取和异步任务跟踪

## Excel 数据源（你当前要的模式）

- `CSV_ROOT` 现在可直接填 Excel 文件路径，例如：

```bash
CSV_ROOT=E:/astronomical_dataset/astronomical-image-and-csv-dataset/天文学数据集.xlsx
```

- 后端会按工作表（sheet）加载实体，`category` 默认取 sheet 名（可被表内 `category/type/分类/类别` 覆盖）。
- 图片字段支持中英文字段（如 `image_url` / `图片地址` / `图像路径` / `链接`），可直接用于图搜与预览。
- 若 Excel 中是相对图片路径，可在 `.env` 设置 `IMAGE_BASE_DIRS`（逗号分隔多个目录），后端会自动尝试拼接解析。
- 若 Excel 同目录存在 `images_catalog.csv` 且 `AUTO_LOAD_IMAGES_CATALOG=true`，后端会自动把该图片清单并入加载结果。

## 后端扩展文本知识库（不改前端）

- 新接口：`POST /api/v1/data/ingest-text`
- 支持导入 `txt/md/jsonl/json` 文本语料，自动分块并并入后端检索与问答知识库。
- 适合你后续“只在后端扩容知识图谱/知识库，不调整前端页面”的场景。

示例请求：

```bash
curl -X POST http://localhost:8000/api/v1/data/ingest-text \
  -H "Content-Type: application/json" \
  -d "{\"text_root\":\"F:/astro_text_corpus\",\"category_prefix\":\"text_knowledge\",\"chunk_size\":900,\"overlap\":150}"
```

或直接脚本导入：

```bash
python scripts/ingest_text_corpus.py --text-root "F:/astro_text_corpus" --csv-root "F:/天文学数据集/天文学数据集.xlsx"
```

## 图片ID与对象键（M1）

- 运行数据加载后，系统会为每张图片生成稳定 `image_id`，并返回 `image_url=/api/v1/image/file/{image_id}`。
- `DataService` 会为每张图生成 MinIO 对象键规划：
  - `astro/images/{prefix}/{image_id}/original.xxx`
  - `astro/images/{prefix}/{image_id}/thumb_1024.webp`
  - `astro/images/{prefix}/{image_id}/thumb_512.webp`
  - `astro/images/{prefix}/{image_id}/thumb_256.webp`
- 可用脚本生成清单：

```bash
python scripts/prepare_image_manifest.py --csv-root "D:/your_dataset.xlsx" --output "tmp/image_manifest.jsonl"
```

## CLIP + Milvus（以文搜图 / 以图搜图）

1. 使用官方或自建 **Milvus 2.x**。本仓库提供 compose：`infra/milvus/docker-compose.yml`。在 PowerShell 中可执行 `infra/milvus/start-milvus.ps1`，或在该目录运行 `docker compose up -d`（对外端口 **19530**）。
2. 在 `.env` 中设置 `MILVUS_ENABLED=true`，并按需配置 `MILVUS_HOST`、`MILVUS_PORT`、`MILVUS_COLLECTION`（默认集合名与索引脚本一致）。
3. 安装依赖：`pip install -r requirements.txt`（含 `torch`、`open-clip-torch`、`pymilvus`、`transformers`、`modelscope`）。
4. 先在前端或接口完成 **数据源扫描与加载**（CSV目录或 Excel），保证图片字段路径可读。
5. 建立集合并写入向量：

```bash
python scripts/index_milvus_clip.py
```

6. 重启后端，检查 `GET /api/v1/image/vector-status`（`milvus_connected`、`indexed_vectors`、`clip_ready`）。
7. 若集合已存在且需全量重建，请在 Milvus 中删除对应 collection 后再跑索引脚本，避免主键冲突。

未启用 Milvus 或索引为空时：**以文搜图**降级为本地弱检索；**以图搜图**返回空并在响应 `note` 中说明。

## 向量检索与索引快照（M2）

- 检索服务已升级为“向量召回 + 混合检索融合（本地索引实现）”。
- 查询当前向量索引 schema：

```bash
curl http://localhost:8000/api/v1/retrieval/vector-schema
```

- 生成本地向量索引快照（便于校验/演示）：

```bash
python scripts/build_vector_index.py --csv-root "D:/your_csv_root" --output "tmp/vector_snapshot.json"
```

## 监控与压测（M4）

- 内置轻量指标接口：`GET /api/v1/metrics`
- 压测脚本：

```bash
python scripts/load_test.py --base-url "http://localhost:8000" --requests 200 --concurrency 20
```
