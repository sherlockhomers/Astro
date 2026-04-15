import warnings
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        protected_namespaces=(),
        extra="ignore",
    )

    # ─── Security-critical fields (require env override in production) ───────────
    auth_secret: str = Field(
        default="",
        description="JWT signing secret — MUST override in production with ≥32 random chars",
    )
    neo4j_password: str = Field(
        default="neo4j-CHANGE-IN-PROD",
        description="Neo4j password — MUST override in production",
    )
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    mcp_nasa_api_key: str = Field(
        default="NASA-KEY-REQUIRED",
        description="NASA API key — MUST set real key in .env",
    )
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:8000",
        description="CORS origins (comma-separated); set explicit origins in production",
    )

    # ─── Pydantic Validators ──────────────────────────────────────────────────

    @field_validator("auth_secret")
    @classmethod
    def _warn_weak_auth_secret(cls, v: str) -> str:
        import os, secrets
        weak = {"change-this-secret", "secret", "password", "changeme", "admin",
                "insecuredevonlyoverrideinprod", ""}
        normalized = v.lower().replace("-", "").replace("_", "")
        env = os.getenv("APP_ENV", "dev").lower()
        if normalized in weak or len(v) < 32:
            if env in ("production", "prod", "staging"):
                raise ValueError(
                    f"auth_secret is too weak for {env} environment. "
                    "Generate a strong random secret (≥32 chars) and set it in .env."
                )
            if not v or normalized in weak:
                v = secrets.token_urlsafe(48)
                warnings.warn(
                    f"[Security] auth_secret was empty/weak — auto-generated a random "
                    f"dev secret ({v[:12]}...). Set a permanent secret in .env for production.",
                    UserWarning,
                )
            else:
                warnings.warn(
                    f"[Security WARN] auth_secret appears weak ('{v[:20]}...'). "
                    "Generate a strong random secret (≥32 chars) for production.",
                    UserWarning,
                )
        return v

    @field_validator("neo4j_password")
    @classmethod
    def _warn_weak_neo4j_password(cls, v: str) -> str:
        if v.lower() in {"password", "neo4j", "changeme", "neo4j-change-in-prod"}:
            warnings.warn(
                "[Security WARN] neo4j_password is unchanged from default. "
                "Set a strong password in .env for production.",
                UserWarning,
            )
        return v

    @field_validator("allowed_origins")
    @classmethod
    def _warn_permissive_cors(cls, v: str) -> str:
        unsafe = {"*", "0.0.0.0", "0.0.0.0:0", "all"}
        if any(x.strip() in unsafe for x in v.split(",")):
            warnings.warn(
                "[Security WARN] allowed_origins contains '*' or 0.0.0.0 — "
                "this allows any origin. Set explicit origins in .env for production.",
                UserWarning,
            )
        return v

    @field_validator("mcp_nasa_api_key")
    @classmethod
    def _warn_demo_nasa_key(cls, v: str) -> str:
        if v.upper() in {"NASA-KEY-REQUIRED", "DEMO_KEY", ""}:
            warnings.warn(
                "[Security WARN] mcp_nasa_api_key is still the placeholder value. "
                "Set your real NASA API key in .env.",
                UserWarning,
            )
        return v

    # ─── Application config ─────────────────────────────────────────────────────
    app_name: str = "AstroGraph API"
    app_env: str = "dev"
    csv_ready: bool = False
    csv_root: str = ""
    image_base_dirs: str = ""
    text_corpus_root: str = ""
    text_corpus_auto_ingest_on_startup: bool = True
    local_fact_rules_path: str = "D:/Astro/backend/data/local_fact_rules.jsonl"
    auto_load_images_catalog: bool = True
    auto_build_graph_on_startup: bool = True
    neo4j_enabled: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    sqlite_path: str = "astrograph.db"
    admin_token: str = Field(
        default="",
        description="Separate admin API token. Falls back to auth_secret if empty.",
    )
    auth_token_expire_hours: int = 72
    auth_access_token_minutes: int = 30
    auth_refresh_token_days: int = 14
    auth_cookie_name: str = "astro_refresh_token"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    model_adapter_path: str = "models/custom_model.py"
    model_class_name: str = "AstroModel"
    starwhisper_enabled: bool = False
    starwhisper_required: bool = True
    starwhisper_model_path: str = ""
    starwhisper_tokenizer_path: str = ""
    starwhisper_lazy_load: bool = True
    starwhisper_quantization: str = "none"
    starwhisper_max_new_tokens: int = 512
    starwhisper_temperature: float = 0.3
    starwhisper_top_p: float = 0.9
    starwhisper_repetition_penalty: float = 1.08
    starwhisper_cpu_offload: bool = True
    starwhisper_offload_dir: str = "tmp/starwhisper_offload"
    starwhisper_offload_state_dict: bool = False
    starwhisper_max_cpu_memory: str = ""
    starwhisper_min_total_memory_gib: float = 40.0
    starwhisper_min_available_memory_gib: float = 20.0
    spectrum_enabled: bool = True
    spectrum_model_id: str = "AstroYuYang/Spectrum-Captioner"
    spectrum_model_path: str = ""
    spectrum_lazy_load: bool = True
    spectrum_auto_download: bool = False
    spectrum_min_total_memory_gib: float = 32.0
    spectrum_min_available_memory_gib: float = 12.0
    minio_enabled: bool = False
    minio_endpoint: str = "localhost:9000"
    minio_secure: bool = False
    minio_bucket: str = "astro-images"
    milvus_enabled: bool = False
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "astro_image_clip"
    milvus_connect_timeout_seconds: float = 1.8
    milvus_fail_cooldown_seconds: float = 15.0
    milvus_auto_index_on_startup: bool = True
    milvus_auto_index_batch_size: int = 64
    milvus_auto_index_clip_batch_size: int = 24
    milvus_auto_index_max_images: int = 0
    milvus_dedup_manifest_path: str = "D:/Astro/backend/data/image_dedup_manifest.json"
    milvus_dedup_enable_perceptual: bool = True
    milvus_dedup_hamming_threshold: int = 2
    clip_model_name: str = "ViT-B-32"
    clip_pretrained: str = "laion2b_s34b_b79k"
    dynamic_enabled: bool = True
    dynamic_timeout_seconds: float = 5.0
    dynamic_cache_ttl_hours: int = 24
    web_search_enabled: bool = True
    web_search_timeout_seconds: float = 6.0
    model_enhance_timeout_seconds: float = 90.0
    mcp_tools_enabled: bool = True
    mcp_timeout_seconds: float = 6.0
    agent_enable_llm_planner: bool = False
    agent_enable_reflection: bool = True
    agent_retrieval_top_k: int = 5
    agent_kb_min_score: float = 0.45
    agent_simple_top_k: int = 3
    agent_medium_top_k: int = 4
    agent_complex_top_k: int = 6
    retrieval_cache_ttl_seconds: int = 1800
    retrieval_cache_max_entries: int = 512
    graph_query_cache_ttl_seconds: int = 1800
    graph_query_cache_max_entries: int = 256
    image_cache_ttl_seconds: int = 1800
    image_cache_max_entries: int = 256
    qa_cache_ttl_seconds: int = 900
    qa_cache_max_entries: int = 256
    sqlite_busy_timeout_ms: int = 8000
    qa_stream_total_timeout_seconds: float = 45.0
    qa_image_timeout_seconds: float = 30.0
    qa_rate_limit_per_minute: int = 20
    astro_vision_warmup_on_startup: bool = True
    astro_vision_warmup_delay_seconds: float = 6.0
    clip_warmup_on_startup: bool = True

    cloud_llm_enabled: bool = False
    cloud_llm_provider: str = "openai"
    cloud_llm_api_key: str = ""
    cloud_llm_model: str = "gpt-4o-mini"
    cloud_llm_timeout_seconds: float = 30.0
    cloud_llm_max_tokens: int = 800

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
