"""설정 로더. config/settings.yaml 을 pydantic 모델로 검증해 로드한다."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field


class GCPConfig(BaseModel):
    project_id: str
    location: str = "asia-northeast3"
    staging_bucket: str


class DocumentAIConfig(BaseModel):
    processor_location: str = "us"
    processor_id: str


class ModelsConfig(BaseModel):
    embedding_model: str = "text-multilingual-embedding-002"
    generation_model: str = "gemini-1.5-pro-002"
    temperature: float = 0.2
    max_output_tokens: int = 8192


class VectorSearchConfig(BaseModel):
    index_endpoint_id: str
    deployed_index_id: str
    dimensions: int = 768
    top_k: int = 5


class AcceptanceCriteria(BaseModel):
    dissolution_min: float = 85.0
    assay_min: float = 98.5


class OutputConfig(BaseModel):
    formulation_count: int = 3
    eln_integration: bool = False


class LoggingConfig(BaseModel):
    audit_trail: bool = True
    level: str = "INFO"


class Settings(BaseModel):
    gcp: GCPConfig
    document_ai: DocumentAIConfig
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    vector_search: VectorSearchConfig
    acceptance_criteria: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)
    external_sources: dict = Field(default_factory=dict)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"


@lru_cache(maxsize=1)
def get_settings(path: str | None = None) -> Settings:
    cfg_path = Path(path or os.getenv("DAEWON_CONFIG", DEFAULT_CONFIG_PATH))
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"설정 파일을 찾을 수 없습니다: {cfg_path}\n"
            "config/settings.example.yaml 을 settings.yaml 로 복사 후 값을 채우세요."
        )
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Settings(**raw)
