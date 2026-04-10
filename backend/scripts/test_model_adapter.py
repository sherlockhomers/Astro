"""
测试自定义模型适配器是否可被系统加载。

示例：
python scripts/test_model_adapter.py --adapter-path "models/custom_model.py" --class-name "AstroModel"
"""

from __future__ import annotations

import argparse

from app.services.model_service import ModelService


def main() -> None:
    parser = argparse.ArgumentParser(description="测试模型适配器")
    parser.add_argument("--adapter-path", default="models/custom_model.py")
    parser.add_argument("--class-name", default="AstroModel")
    args = parser.parse_args()

    service = ModelService()
    ok, message = service.load(args.adapter_path, args.class_name)
    print(f"load ok={ok} message={message}")
    print(f"status={service.get_status()}")

    if ok:
        ok_qa, qa_res = service.answer("火星有几颗卫星？", {"session_id": "demo"})
        print(f"qa ok={ok_qa} res={qa_res}")
        ok_img, img_res = service.predict_image(b"demo", "mars.jpg")
        print(f"img ok={ok_img} res={img_res}")


if __name__ == "__main__":
    main()
