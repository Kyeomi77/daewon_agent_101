"""Step 2: 물성 데이터 임베딩.

text-multilingual-embedding-002 모델로 물성 데이터를 768차원 벡터로 변환한다.
한국어 + 영문 동시 지원.
"""
from __future__ import annotations

import logging

from vertexai.language_models import TextEmbeddingModel, TextEmbeddingInput

from ..config import Settings
from ..schemas import PhysChemParams

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = TextEmbeddingModel.from_pretrained(
            settings.models.embedding_model
        )

    @staticmethod
    def params_to_text(params: PhysChemParams) -> str:
        """물성 파라미터를 임베딩용 자연어 문장으로 직렬화."""
        return (
            f"API: {params.api_name or 'unknown'}. "
            f"용해도 {params.solubility_mg_ml} mg/mL, "
            f"pKa {params.pka}, logP {params.logp}, "
            f"분자량 {params.molecular_weight}, "
            f"흡수부위 {params.absorption_site}, "
            f"BCS {params.bcs_class.value if params.bcs_class else 'unknown'}."
        )

    def embed_query(self, params: PhysChemParams) -> list[float]:
        text = self.params_to_text(params)
        inputs = [TextEmbeddingInput(text=text, task_type="RETRIEVAL_QUERY")]
        embeddings = self._model.get_embeddings(inputs)
        logger.info("쿼리 임베딩 생성 완료 (dim=%d)", len(embeddings[0].values))
        return embeddings[0].values

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """인덱스 적재용 문서 배치 임베딩."""
        inputs = [
            TextEmbeddingInput(text=t, task_type="RETRIEVAL_DOCUMENT")
            for t in texts
        ]
        embeddings = self._model.get_embeddings(inputs)
        return [e.values for e in embeddings]
