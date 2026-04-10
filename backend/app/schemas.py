from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class HealthResponse(APIModel):
    status: str
    app: str
    env: str


class AskRequest(APIModel):
    question: str = Field(min_length=1, max_length=2000)
    image_id: str | None = None
    session_id: str | None = None
    image_hint: str | None = None


class AskResponse(APIModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    graph_path: list[dict[str, Any]] = Field(default_factory=list)
    mode: str
    confidence: str = "medium"
    session_id: str | None = None


class QADiagnosticsResponse(APIModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    graph_path: list[dict[str, Any]] = Field(default_factory=list)
    mode: str
    confidence: str = "medium"
    session_id: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    cache: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunRequest(APIModel):
    sample_size: int = Field(default=12, ge=1, le=100)
    use_cache: bool = True


class EvaluationReportResponse(APIModel):
    generated_at: str | None = None
    dataset_size: int = 0
    sample_size: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    category_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    cases: list[dict[str, Any]] = Field(default_factory=list)


class SearchRequest(APIModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    image_hint: str | None = None


class SearchItem(APIModel):
    id: str
    title: str
    score: float
    source: str
    snippet: str = ""
    image_url: str | None = None


class SearchResponse(APIModel):
    items: list[SearchItem]
    note: str


class ExploreQueryRequest(APIModel):
    query: str = Field(min_length=1, max_length=2000)
    image_hint: str | None = None


class ExploreBundleResponse(APIModel):
    query: str
    intent: str
    headline: str = ""
    note: str = ""
    focus_entity: str = ""
    focus_card: dict[str, Any] = Field(default_factory=dict)
    related_images: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_note: str = ""
    graph: dict[str, Any] = Field(default_factory=dict)
    graph_highlights: list[str] = Field(default_factory=list)
    compare: dict[str, Any] = Field(default_factory=dict)
    model3d: dict[str, Any] = Field(default_factory=dict)
    follow_ups: list[str] = Field(default_factory=list)
    entry_points: list[dict[str, str]] = Field(default_factory=list)


class BuildGraphRequest(APIModel):
    csv_root: str = Field(description="数据源路径（CSV目录或Excel文件）")
    categories: list[str] = Field(default_factory=list)
    write_neo4j: bool = False


class BuildGraphResponse(APIModel):
    accepted: bool
    message: str
    task_id: str


class GraphPathResponse(APIModel):
    items: list[dict[str, str]]


class SystemStatusResponse(APIModel):
    model_ready: bool
    csv_ready: bool
    graph_ready: bool
    message: str


class SystemCapabilityReportResponse(APIModel):
    generated_at: str
    summary: dict[str, Any] = Field(default_factory=dict)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    components: dict[str, Any] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class DataScanRequest(APIModel):
    csv_root: str = Field(description="数据源路径（CSV目录或Excel文件）")


class CsvFileInfo(APIModel):
    name: str
    rows: int
    columns: list[str]


class DataScanResponse(APIModel):
    files: list[CsvFileInfo]
    total_files: int


class DataLoadRequest(APIModel):
    csv_root: str = Field(description="数据源路径（CSV目录或Excel文件）")
    categories: list[str] = Field(default_factory=list)


class DataLoadResponse(APIModel):
    loaded: bool
    source_root: str | None = None
    entity_count: int = 0
    category_count: int = 0
    file_count: int = 0
    extra_entity_count: int = 0


class TextIngestRequest(APIModel):
    text_root: str = Field(description="文本语料目录或文件路径（支持 txt/md/jsonl/json）")
    category_prefix: str = Field(default="text_knowledge", min_length=1, max_length=64)
    chunk_size: int = Field(default=900, ge=300, le=4000)
    overlap: int = Field(default=150, ge=0, le=2000)


class TextIngestResponse(APIModel):
    ok: bool
    text_root: str
    files: int
    chunks: int
    category: str
    entity_count: int
    extra_entity_count: int


class TextIngestClearResponse(APIModel):
    ok: bool
    removed: int
    entity_count: int


class GraphPathQueryResponse(APIModel):
    found: bool
    path: list[dict[str, str]] = Field(default_factory=list)
    message: str


class GraphMultiPathQueryResponse(APIModel):
    found: bool
    paths: list[list[dict[str, str]]] = Field(default_factory=list)
    message: str


class CypherQueryRequest(APIModel):
    query: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class CypherQueryResponse(APIModel):
    ok: bool
    records: list[dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class RegisterRequest(APIModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(APIModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class AuthResponse(APIModel):
    ok: bool
    token: str | None = None
    access_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    user_id: int | None = None
    username: str | None = None
    message: str


class UserProfileResponse(APIModel):
    ok: bool
    user_id: int
    username: str
    created_at: str | None = None


class UpdateProfileRequest(APIModel):
    username: str = Field(min_length=3, max_length=64)


class QAHistoryItem(APIModel):
    id: int
    session_id: str
    question: str
    answer: str
    citations: list[str]
    created_at: str


class QAHistoryResponse(APIModel):
    items: list[QAHistoryItem]
    limit: int = 50
    offset: int = 0
    total: int = 0
    has_more: bool = False


class UserFavoriteCreateRequest(APIModel):
    title: str = Field(min_length=1, max_length=120)
    category: str | None = None
    image_url: str | None = None
    source_query: str | None = None


class UserFavoriteItem(APIModel):
    id: int
    title: str
    category: str | None = None
    image_url: str | None = None
    source_query: str | None = None
    created_at: str


class RecentExploreItem(APIModel):
    id: int
    session_id: str
    question: str
    topic: str
    created_at: str


class ContinueExploreItem(APIModel):
    title: str
    query: str
    reason: str
    path: str = "/app/qa"


class UserOverviewResponse(APIModel):
    ok: bool = True
    user_id: int
    username: str
    created_at: str | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    recent_explorations: list[RecentExploreItem] = Field(default_factory=list)
    favorites: list[UserFavoriteItem] = Field(default_factory=list)
    history_preview: list[QAHistoryItem] = Field(default_factory=list)
    recommended_continue: list[ContinueExploreItem] = Field(default_factory=list)


class MutationStatusResponse(APIModel):
    ok: bool
    message: str
    id: int | None = None


class GraphRAGQueryRequest(APIModel):
    question: str = Field(min_length=1, max_length=2000)


class GraphRAGQueryResponse(APIModel):
    answer: str
    trace: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)


class ModelLoadRequest(APIModel):
    adapter_path: str | None = None
    class_name: str | None = None


class ModelStatusResponse(APIModel):
    loaded: bool
    text_ready: bool = False
    vision_ready: bool = False
    vision_enabled: bool = False
    vision_lazy_load: bool = False
    vision_available: bool = False
    vision_warmup_running: bool = False
    adapter_path: str
    class_name: str
    supports_qa: bool
    supports_image_predict: bool = False
    supports_image_qa: bool = False
    last_error: str | None = None


class ModelLoadResponse(APIModel):
    ok: bool
    message: str
    status: ModelStatusResponse


class GraphExportCypherRequest(APIModel):
    output_path: str


class GraphExportCypherResponse(APIModel):
    ok: bool
    output_path: str
    node_count: int
    relation_count: int
    message: str
