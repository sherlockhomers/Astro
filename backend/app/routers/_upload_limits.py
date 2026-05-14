"""上传体积限制帮手。

之前 image / qa 路由直接 `await file.read()` 没有大小检查，
攻击者上传 GB 级别文件可以一发把后端打爆。这里集中处理。
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

# 默认 10 MB；天文图片绝大多数都在 1MB 内，留出 10 倍余量
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024


async def enforce_image_size(file: UploadFile, max_bytes: int = DEFAULT_MAX_IMAGE_BYTES) -> bytes:
    """读取并返回上传的图片字节，超过 max_bytes 直接 413。

    优先用 starlette/FastAPI 暴露的 file.size（Content-Length 衍生）做早期判定，
    避免恶意客户端伪造 size 时再用流式累计兜底。
    """
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"上传文件超过 {max_bytes // 1024 // 1024} MB 限制",
        )

    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024  # 1MB 一片，足够大又不会一次吃太多内存
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"上传文件超过 {max_bytes // 1024 // 1024} MB 限制",
            )
        chunks.append(chunk)
    return b"".join(chunks)
