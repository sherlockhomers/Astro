# Frontend（Vue 3 + Vite）

## 启动

```bash
npm install
npm run dev
```

默认地址：`http://localhost:5173`

## 环境变量

复制 `.env.example` 为 `.env` 并按需修改：

```env
VITE_API_BASE_URL=http://localhost:8000
```

## 页面能力（阶段一）

- 系统状态查看
- 模型适配器热加载（路径+类名）
- CSV 扫描与加载
- 用户注册/登录与问答历史
- 问答接口联调（支持 session 多轮）
- 图像问答（上传图片 + 问题）
- 数据检索结果展示
- 触发构图并查看关系路径
- 多跳路径发现
- 可视化数据加载、实体对比、时间线
- ECharts 图谱关系可视化（交互缩放拖拽）
- Three.js 3D 星图点云演示
- 知识图谱 Cypher 一键导出

后续可按需求文档扩展：图谱可视化、图像检索、3D 星图、多轮对话等。
