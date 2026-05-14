from __future__ import annotations

import json
import logging
import re
import uuid
from queue import Empty, Queue
from threading import Thread

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.deps import ServiceContainer, extract_token, get_services, optional_user, require_internal
from app.routers._upload_limits import enforce_image_size
from app.schemas import AskRequest, AskResponse, EvaluationReportResponse, EvaluationRunRequest, QADiagnosticsResponse

router = APIRouter(prefix="/api/v1", tags=["qa"])
logger = logging.getLogger("astrograph")


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _answer_chunks(answer: str) -> list[str]:
    text = str(answer or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*|\n+", text) if part.strip()]
    if not parts:
        return [text]
    return [part if part.endswith(("。", "！", "？", ".", "!", "?", "；", ";")) else f"{part} " for part in parts]


def _public_citations(citations: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in citations:
        raw = str(item or "").strip()
        if not raw:
            continue
        if raw.startswith(("http://", "https://", "image:/")):
            candidate = raw
        elif "http://" in raw or "https://" in raw:
            idx_http = raw.find("http://")
            idx_https = raw.find("https://")
            candidates = [x for x in [idx_http, idx_https] if x >= 0]
            candidate = raw[min(candidates):] if candidates else ""
        else:
            continue
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def _derive_confidence(result: dict) -> str:
    reflection = result.get("trace", {}).get("reflection", {}) if isinstance(result, dict) else {}
    issues = reflection.get("issues", []) if isinstance(reflection, dict) else []
    count = len(issues) if isinstance(issues, list) else 0
    if count <= 1:
        return "high"
    if count <= 3:
        return "medium"
    return "low"


def _derive_image_confidence(result: dict) -> str:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    prediction = trace.get("prediction", {}) if isinstance(trace, dict) else {}
    focus_name = str(trace.get("focus_name", "") or "").strip().lower()
    image_result_count = int(trace.get("image_result_count", 0) or 0)
    score = prediction.get("confidence")
    try:
        confidence_score = float(score)
    except Exception:
        confidence_score = 0.0
    ambiguous_labels = {"unknown", "", "星座", "constellation", "galaxy", "星系"}
    if focus_name in ambiguous_labels:
        return "low" if image_result_count <= 0 else "medium"
    if confidence_score >= 0.72 and image_result_count >= 1:
        return "high"
    if confidence_score >= 0.58 or image_result_count >= 1:
        return "medium"
    return "low"


@router.post("/qa/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    user: dict | None = Depends(optional_user),
    svc: ServiceContainer = Depends(get_services),
) -> AskResponse:
    sid = payload.session_id or uuid.uuid4().hex[:12]
    result = svc.qa.ask_detailed(payload.question, sid)
    answer = str(result.get("answer", "")).strip()
    citations = [str(x) for x in result.get("citations", []) if str(x).strip()]
    graph_path = list(result.get("graph_path", []))
    mode = str(result.get("mode", "adaptive_rag_agent"))
    confidence = _derive_confidence(result)
    sid = str(result.get("session_id", sid))

    if user:
        svc.user.save_history(
            user_id=user["user_id"],
            session_id=sid,
            question=payload.question,
            answer=answer,
            citations_json=json.dumps(citations, ensure_ascii=False),
        )
    return AskResponse(
        answer=answer,
        citations=_public_citations(citations),
        graph_path=graph_path,
        mode=mode,
        confidence=confidence,
        session_id=sid,
    )


@router.post("/qa/stream")
def ask_question_stream(
    payload: AskRequest,
    authorization: str | None = Header(default=None),
    svc: ServiceContainer = Depends(get_services),
):
    sid = payload.session_id or uuid.uuid4().hex[:12]
    token = extract_token(authorization)
    user = svc.user.get_user_by_token(token) if token else None

    def event_stream():
        stream_queue: Queue[dict | None] = Queue()
        result_box: dict[str, object] = {}

        def emit(stage: str, event_payload: dict | None = None) -> None:
            data = {"stage": stage}
            if isinstance(event_payload, dict):
                data.update(event_payload)
            stream_queue.put(data)

        def worker() -> None:
            try:
                result_box["result"] = svc.qa.ask_detailed_with_timeout(
                    payload.question,
                    sid,
                    emit_stage=emit,
                    max_total_seconds=settings.qa_stream_total_timeout_seconds,
                )
            except Exception as exc:
                result_box["error"] = exc
            finally:
                stream_queue.put(None)

        thread = Thread(target=worker, daemon=True)
        thread.start()
        yield _sse_event("status", {"stage": "start", "message": "正在建立回答链路。"})
        sent_preview = ""

        while True:
            try:
                item = stream_queue.get(timeout=0.35)
            except Empty:
                if thread.is_alive():
                    yield ": ping\n\n"
                    continue
                item = None
            if item is None:
                break
            delta_text = str(item.get("delta", "") or "") if isinstance(item, dict) else ""
            if delta_text:
                sent_preview += delta_text
                yield _sse_event("delta", {"text": delta_text, "preview": True})
                item = {k: v for k, v in item.items() if k != "delta"}
            if item:
                yield _sse_event("status", item)

        thread.join()
        error = result_box.get("error")
        if error is not None:
            yield _sse_event("error", {"message": "问答链路暂时超时，系统已回退到安全提示。", "detail": str(error)})
            return

        result = dict(result_box.get("result") or {})
        answer = str(result.get("answer", "")).strip()
        citations = _public_citations([str(x) for x in result.get("citations", []) if str(x).strip()])
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "adaptive_rag_agent"))
        confidence = _derive_confidence(result)

        remaining_answer = answer
        if sent_preview and answer.startswith(sent_preview):
            remaining_answer = answer[len(sent_preview):].lstrip()
        for chunk in _answer_chunks(remaining_answer):
            yield _sse_event("delta", {"text": chunk})

        if user:
            svc.user.save_history(
                user_id=user["user_id"],
                session_id=sid,
                question=payload.question,
                answer=answer,
                citations_json=json.dumps(citations, ensure_ascii=False),
            )
        yield _sse_event("done", {
            "answer": answer, "citations": citations, "graph_path": graph_path,
            "mode": mode, "confidence": confidence, "session_id": sid,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/qa/stream-with-image")
async def ask_question_stream_with_image(
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
    svc: ServiceContainer = Depends(get_services),
):
    image_bytes = await enforce_image_size(file)
    filename = file.filename or "upload.png"
    sid = session_id or uuid.uuid4().hex[:12]
    token = extract_token(authorization)
    user = svc.user.get_user_by_token(token) if token else None

    def event_stream():
        stream_queue: Queue[dict | None] = Queue()
        result_box: dict[str, object] = {}

        def emit(stage: str, event_payload: dict | None = None) -> None:
            data = {"stage": stage}
            if isinstance(event_payload, dict):
                data.update(event_payload)
            stream_queue.put(data)

        def worker() -> None:
            try:
                result_box["result"] = svc.qa.ask_with_image_detailed_with_timeout(
                    question=question, image_bytes=image_bytes, filename=filename,
                    session_id=sid, max_total_seconds=settings.qa_image_timeout_seconds,
                    emit_stage=emit,
                )
            except Exception as exc:
                result_box["error"] = exc
            finally:
                stream_queue.put(None)

        preview = None
        try:
            preview = svc.qa.build_image_preview(question, image_bytes, filename)
        except Exception:
            preview = None

        thread = Thread(target=worker, daemon=True)
        thread.start()
        sent_preview = ""
        yield _sse_event("status", {"stage": "image_received", "message": "已接收图片，正在提取视觉特征。"})

        if preview:
            focus_name = str(preview.get("focus_name", "")).strip()
            if focus_name:
                yield _sse_event("status", {"stage": "vision_preview", "message": f"已完成初步识别，主体更接近{focus_name}。"})
            preview_text = str(preview.get("answer", "")).strip()
            if preview_text:
                sent_preview = preview_text
                yield _sse_event("delta", {"text": preview_text, "preview": True})

        while True:
            try:
                item = stream_queue.get(timeout=0.45)
            except Empty:
                if thread.is_alive():
                    yield ": ping\n\n"
                    continue
                item = None
            if item is None:
                break
            # ask_with_image_detailed 现在会把每个阶段 push 进 stream_queue
            if isinstance(item, dict):
                yield _sse_event("status", item)

        thread.join()
        error = result_box.get("error")
        if error is not None:
            yield _sse_event("error", {"message": "图片问答暂时没有稳定完成。建议换一张主体更清晰的图片再试。", "detail": str(error)})
            return

        result = dict(result_box.get("result") or {})
        answer = str(result.get("answer", "")).strip()
        citations = _public_citations([str(x) for x in result.get("citations", []) if str(x).strip()])
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "image_grounded_agent"))
        confidence = _derive_image_confidence(result)

        remaining_answer = answer
        if sent_preview and answer.startswith(sent_preview):
            remaining_answer = answer[len(sent_preview):].lstrip()
        for chunk in _answer_chunks(remaining_answer):
            yield _sse_event("delta", {"text": chunk})

        if user:
            svc.user.save_history(
                user_id=user["user_id"], session_id=sid, question=question,
                answer=answer, citations_json=json.dumps(citations, ensure_ascii=False),
            )
        yield _sse_event("done", {
            "answer": answer, "citations": citations, "graph_path": graph_path,
            "mode": mode, "confidence": confidence, "session_id": sid,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/qa/ask-with-image", response_model=AskResponse)
async def ask_with_image(
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    user: dict | None = Depends(optional_user),
    svc: ServiceContainer = Depends(get_services),
) -> AskResponse:
    image_bytes = await enforce_image_size(file)
    filename = file.filename or "upload.png"
    sid = session_id or uuid.uuid4().hex[:12]
    try:
        result = svc.qa.ask_with_image_detailed_with_timeout(
            question=question, image_bytes=image_bytes, filename=filename,
            session_id=sid, max_total_seconds=settings.qa_image_timeout_seconds,
        )
        answer = str(result.get("answer", "")).strip()
        citations = [str(x) for x in result.get("citations", []) if str(x).strip()]
        graph_path = list(result.get("graph_path", []))
        mode = str(result.get("mode", "image_grounded_agent"))
        confidence = _derive_image_confidence(result)
    except Exception as exc:
        logger.warning("image qa failed: %s", exc)
        answer = "这张图片的识别流程暂时没有稳定完成。建议换一张主体更清晰、对比度更高的图片再试。"
        citations, graph_path = [], []
        mode, confidence = "image_grounded_agent", "low"

    if user:
        svc.user.save_history(
            user_id=user["user_id"], session_id=sid, question=question,
            answer=answer, citations_json=json.dumps(citations, ensure_ascii=False),
        )
    return AskResponse(
        answer=answer, citations=_public_citations(citations), graph_path=graph_path,
        mode=mode, confidence=confidence, session_id=sid,
    )


@router.post("/qa/diagnostics", response_model=QADiagnosticsResponse)
def ask_question_diagnostics(
    payload: AskRequest,
    _: None = Depends(require_internal),
    svc: ServiceContainer = Depends(get_services),
) -> QADiagnosticsResponse:
    sid = payload.session_id or uuid.uuid4().hex[:12]
    result = svc.qa.ask_detailed(payload.question, sid)
    result["confidence"] = _derive_confidence(result)
    return QADiagnosticsResponse(**result)


@router.get("/eval/report", response_model=EvaluationReportResponse)
def eval_report(
    _: None = Depends(require_internal),
    svc: ServiceContainer = Depends(get_services),
) -> EvaluationReportResponse:
    return EvaluationReportResponse(**svc.evaluation.latest_report())


@router.post("/eval/run", response_model=EvaluationReportResponse)
def eval_run(
    payload: EvaluationRunRequest,
    _: None = Depends(require_internal),
    svc: ServiceContainer = Depends(get_services),
) -> EvaluationReportResponse:
    report = svc.evaluation.run(sample_size=payload.sample_size, use_cache=payload.use_cache)
    return EvaluationReportResponse(**report)
