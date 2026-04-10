# 模型接入说明（最终交付用）

你后续训练好模型后，只需要完成这两步：

1. 把模型推理包装写进 `custom_model.py` 的 `AstroModel` 类  
2. 调用后端接口 `POST /api/v1/model/load` 进行热加载

当前仓库已内置 StarWhisper 适配器实现（`custom_model.py`），可直接配置以下环境变量启用：

```bash
STARWHISPER_ENABLED=true
STARWHISPER_MODEL_PATH=D:/models/starwhisper-checkpoint
STARWHISPER_TOKENIZER_PATH=D:/models/starwhisper-checkpoint
STARWHISPER_LAZY_LOAD=true
```

## 适配器接口约定

`AstroModel` 支持以下方法（至少实现一个）：

- `answer(question: str, context: dict) -> str | dict`
- `predict_image(image_bytes: bytes, filename: str, context: dict) -> dict`

返回推荐格式：

```python
{
  "answer": "...",
  "citations": ["..."],
  "graph_path": [{"from": "...", "rel": "...", "to": "..."}]
}
```

## 快速测试

```bash
python scripts/test_model_adapter.py --adapter-path "models/custom_model.py" --class-name "AstroModel"
```
