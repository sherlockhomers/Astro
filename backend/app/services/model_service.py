from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path
from typing import Any

from app.config import settings


class ModelService:
    def __init__(self) -> None:
        self._adapter: Any | None = None
        self._adapter_path = settings.model_adapter_path
        self._class_name = settings.model_class_name
        self._last_error: str | None = None
        self._supports_qa = False
        self._supports_image_predict = False
        self._supports_image_qa = False
        self._vision_warmup_thread: threading.Thread | None = None

    def load(self, adapter_path: str | None = None, class_name: str | None = None) -> tuple[bool, str]:
        path = adapter_path or self._adapter_path
        klass = class_name or self._class_name
        file_path = Path(path)
        if not file_path.exists():
            self._adapter = None
            self._supports_qa = False
            self._supports_image_predict = False
            self._supports_image_qa = False
            self._last_error = f"Model adapter file not found: {file_path}"
            return False, self._last_error

        try:
            spec = importlib.util.spec_from_file_location("astro_custom_model", str(file_path))
            if spec is None or spec.loader is None:
                raise RuntimeError("Failed to create import spec for model adapter")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if not hasattr(module, klass):
                raise AttributeError(f"Adapter class not found: {klass}")

            adapter_cls = getattr(module, klass)
            adapter = adapter_cls()
            self._adapter = adapter
            self._adapter_path = str(file_path)
            self._class_name = klass
            self._supports_qa = callable(getattr(adapter, "answer", None))
            self._supports_image_predict = callable(getattr(adapter, "predict_image", None))
            self._supports_image_qa = callable(getattr(adapter, "answer_with_image", None))

            adapter_ready = bool(getattr(adapter, "ready", True))
            if adapter_ready:
                self._last_error = None
                return True, "Model adapter loaded."

            adapter_err = str(getattr(adapter, "_load_error", "")).strip() or "Model adapter not ready."
            self._last_error = adapter_err
            return False, f"Model adapter loaded but not ready: {adapter_err}"
        except Exception as exc:  # noqa: BLE001
            self._adapter = None
            self._supports_qa = False
            self._supports_image_predict = False
            self._supports_image_qa = False
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False, f"Failed to load model adapter: {self._last_error}"

    @property
    def ready(self) -> bool:
        if self._adapter is None:
            return False
        return bool(getattr(self._adapter, "ready", True))

    @property
    def text_ready(self) -> bool:
        if self._adapter is None:
            return False
        value = getattr(self._adapter, "text_ready", None)
        if value is None:
            return self.ready
        return bool(value)

    @property
    def vision_ready(self) -> bool:
        if self._adapter is None:
            return False
        value = getattr(self._adapter, "vision_ready", None)
        if value is None:
            return bool(self._supports_image_predict or self._supports_image_qa)
        return bool(value)

    def get_status(self) -> dict[str, Any]:
        adapter_err = None
        if self._adapter is not None:
            raw_err = getattr(self._adapter, "_load_error", None)
            if raw_err:
                adapter_err = str(raw_err)
        return {
            "loaded": self.ready,
            "text_ready": self.text_ready,
            "vision_ready": self.vision_ready,
            "vision_enabled": bool(getattr(self._adapter, "_vision_enabled", False)) if self._adapter is not None else False,
            "vision_lazy_load": bool(getattr(self._adapter, "_vision_lazy_load", False)) if self._adapter is not None else False,
            "vision_available": bool(self._supports_image_predict or self._supports_image_qa),
            "adapter_path": self._adapter_path,
            "class_name": self._class_name,
            "supports_qa": self._supports_qa,
            "supports_image_predict": self._supports_image_predict,
            "supports_image_qa": self._supports_image_qa,
            "vision_warmup_running": bool(self._vision_warmup_thread and self._vision_warmup_thread.is_alive()),
            "last_error": self._last_error or adapter_err,
        }

    def answer(self, question: str, context: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
        if self._adapter is None or not self._supports_qa or not self.ready:
            return False, "Model is not ready or does not support answer()."
        try:
            result = self._adapter.answer(question=question, context=context)
            return True, result
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def warmup_vision(self) -> tuple[bool, str]:
        if self._adapter is None:
            return False, "Model adapter not loaded."
        if not (self._supports_image_predict or self._supports_image_qa):
            return False, "Vision capability not supported."
        try:
            warmup = getattr(self._adapter, "warmup_vision", None)
            if callable(warmup):
                ok = bool(warmup())
            else:
                ok = bool(getattr(self._adapter, "_ensure_vision_loaded", lambda: False)())
            if ok:
                return True, "Vision warmup completed."
            return False, str(getattr(self._adapter, "_load_error", "")).strip() or "Vision warmup failed."
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def warmup_vision_background(self, delay_seconds: float = 0.0) -> tuple[bool, str]:
        if self._adapter is None:
            return False, "Model adapter not loaded."
        if self._vision_warmup_thread is not None and self._vision_warmup_thread.is_alive():
            return False, "Vision warmup already running."

        def _worker() -> None:
            if delay_seconds > 0:
                time.sleep(max(0.0, float(delay_seconds)))
            self.warmup_vision()

        self._vision_warmup_thread = threading.Thread(
            target=_worker,
            daemon=True,
            name="astro-vision-warmup",
        )
        self._vision_warmup_thread.start()
        return True, "Vision warmup started."

    def predict_image(
        self,
        image_bytes: bytes,
        filename: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | str]:
        if self._adapter is None or not self._supports_image_predict:
            return False, "Model does not support predict_image()."
        try:
            result = self._adapter.predict_image(
                image_bytes=image_bytes,
                filename=filename,
                context=context or {},
            )
            return True, result
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def answer_with_image(
        self,
        question: str,
        image_bytes: bytes,
        filename: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any] | str]:
        if self._adapter is None or not self._supports_image_qa:
            return False, "Model does not support answer_with_image()."
        try:
            result = self._adapter.answer_with_image(
                question=question,
                image_bytes=image_bytes,
                filename=filename,
                context=context or {},
            )
            return True, result
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
