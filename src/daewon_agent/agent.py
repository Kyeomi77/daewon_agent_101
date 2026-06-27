"""대원제약 제제연구 에이전트 오케스트레이터.

LangChain RunnableSequence 로 Step 1 ~ Step 7 파이프라인을 구성한다.
각 단계는 독립 모듈로 분리되어 있어 테스트/교체가 용이하다.

전체 흐름:
  parse → extract → embed → search → infer → write_xlsx
  → (실험 결과 입력) → analyze → write_docx → (ELN 연동)
"""
from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings, get_settings
from .schemas import (
    PhysChemParams,
    SimilarCase,
    FormulationProposal,
    ExperimentResult,
    DeviationAnalysis,
)
from .parsers.document_ai import DocumentParser
from .parsers.param_extractor import extract_parameters
from .rag.embedder import Embedder
from .rag.vector_search import VectorSearchClient
from .inference.formulation import FormulationInferencer
from .feedback.deviation import DeviationAnalyzer
from .outputs.xlsx_writer import write_formulation_xlsx
from .outputs.docx_writer import write_guide_docx

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """파이프라인 전 단계에 걸쳐 누적되는 상태 (감사 추적 단위)."""
    params: Optional[PhysChemParams] = None
    dmf_text: str = ""
    similar_cases: list[SimilarCase] = field(default_factory=list)
    proposal: Optional[FormulationProposal] = None
    xlsx_path: Optional[Path] = None
    analyses: list[DeviationAnalysis] = field(default_factory=list)
    docx_path: Optional[Path] = None


class DaewonFormulationAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        metadata_store: dict | None = None,
    ):
        self.settings = settings or get_settings()
        logging.basicConfig(
            level=getattr(logging, self.settings.logging.level, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        self.parser = DocumentParser(self.settings)
        self.embedder = Embedder(self.settings)
        self.vector_search = VectorSearchClient(self.settings, metadata_store)
        self.inferencer = FormulationInferencer(self.settings)
        self.analyzer = DeviationAnalyzer(self.settings, self.inferencer)

    # ---- Step 1 ~ 5: 처방 제안까지 --------------------------------------
    def propose(
        self,
        properties_path: str | Path,
        dmf_path: str | Path,
        out_dir: str | Path,
    ) -> PipelineState:
        state = PipelineState()
        out_dir = Path(out_dir)

        # Step 1: 입력 파싱 + 파라미터 추출
        logger.info("=== Step 1: 입력 파싱 ===")
        props_text = self.parser.parse(properties_path)
        state.dmf_text = self.parser.parse(dmf_path)
        state.params = extract_parameters(props_text)
        logger.info("추출 파라미터: %s", state.params.model_dump(exclude={"raw_text"}))

        # Step 2: 임베딩 + 벡터 검색
        logger.info("=== Step 2: RAG 벡터 검색 ===")
        query_vec = self.embedder.embed_query(state.params)
        state.similar_cases = self.vector_search.search(query_vec)

        # Step 3: 처방 추론
        logger.info("=== Step 3: Gemini 처방 추론 ===")
        state.proposal = self.inferencer.infer(
            state.params, state.similar_cases, state.dmf_text
        )

        # Step 4: 처방 도출표 .xlsx
        logger.info("=== Step 4: 처방 도출표 생성 ===")
        state.xlsx_path = write_formulation_xlsx(
            state.proposal, out_dir / "처방도출표.xlsx"
        )
        # Step 5 (연구원 Manual 실험)는 외부 단계
        logger.info("Step 5: 연구원 Manual 실험 단계로 인계")
        return state

    # ---- Step 6 ~ 7: 실험 결과 반영 후 최종 보고서 ----------------------
    def finalize(
        self,
        state: PipelineState,
        results: list[ExperimentResult],
        out_dir: str | Path,
    ) -> PipelineState:
        if state.proposal is None or state.params is None:
            raise ValueError("propose() 를 먼저 실행해야 합니다.")
        out_dir = Path(out_dir)

        # Step 6: 편차 분석 + 개선안
        logger.info("=== Step 6: 결과 편차 분석 ===")
        result_map = {r.formulation_id: r for r in results}
        for f in state.proposal.formulations:
            r = result_map.get(f.formulation_id)
            if r is None:
                continue
            state.analyses.append(self.analyzer.analyze(state.params, f, r))

        # Step 7: 최종 처방 가이드 .docx
        logger.info("=== Step 7: 최종 보고서 저장 ===")
        state.docx_path = write_guide_docx(
            state.proposal, state.analyses, out_dir / "최적처방가이드.docx"
        )

        if self.settings.output.eln_integration:
            self._push_to_eln(state)
        return state

    @staticmethod
    def _push_to_eln(state: PipelineState) -> None:
        """클라우독/ELN 연동 (스텁). 실제 사내 API 연동 시 구현."""
        logger.info("ELN 연동: %s 업로드 (스텁)", state.docx_path)
