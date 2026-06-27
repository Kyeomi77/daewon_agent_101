"""Step 3: Gemini 기반 처방 설계 추론.

ICH Q8(R2) QbD 전문가 페르소나를 부여하고, 물성 데이터 + 유사 사례 + DMF 를
통합 분석해 최적 처방 3종을 JSON Schema 강제 출력으로 생성한다.
Temperature = 0.2 (일관성 확보).
"""
from __future__ import annotations

import json
import logging

from vertexai.generative_models import (
    GenerativeModel,
    GenerationConfig,
)

from ..config import Settings
from ..schemas import (
    PhysChemParams,
    SimilarCase,
    FormulationProposal,
    formulation_response_schema,
)

logger = logging.getLogger(__name__)

SYSTEM_PERSONA = """\
당신은 ICH Q8(R2) QbD(Quality by Design) 원칙에 정통한 제약 제제연구 수석 전문가입니다.
원료의약품(API)의 물리화학적 특성, BCS 분류, 과거 유사 처방 사례, 제조처 DMF 자료를
통합적으로 해석하여 과학적 근거에 기반한 최적의 시험 처방을 설계합니다.

설계 원칙:
- BCS 분류에 따른 용해도/투과도 개선 전략을 우선 고려합니다.
- 각 부형제 선택에 대해 QbD 관점의 명확한 근거(rationale)를 제시합니다.
- 처방마다 리스크 등급(Low/Med/High)과 근거를 평가합니다.
- 추측을 최소화하고, 제공된 데이터와 유사 사례에 기반해 추론합니다.
"""


def _build_prompt(
    params: PhysChemParams,
    cases: list[SimilarCase],
    dmf_text: str,
    count: int,
) -> str:
    cases_block = "\n".join(
        f"- [{c.case_id}] (유사도 {c.score}, 출처 {c.source}) {c.summary}"
        for c in cases
    ) or "유사 사례 없음"

    return f"""\
다음 정보를 바탕으로 최적 시험 처방 {count}종을 설계하십시오.

## 물성 데이터
- API: {params.api_name}
- 용해도: {params.solubility_mg_ml} mg/mL
- pKa: {params.pka}
- logP: {params.logp}
- 분자량: {params.molecular_weight}
- 흡수 부위: {params.absorption_site}
- BCS 분류: {params.bcs_class.value if params.bcs_class else '미상'}

## 유사 처방 사례 (RAG Top-{len(cases)})
{cases_block}

## 제조처 DMF 발췌
{dmf_text[:3000]}

## 요구사항
- 정확히 {count}종의 처방안을 제시합니다.
- 각 처방에 부형제 구성, 설계 기대 용출률/함량, 리스크 등급, 근거를 포함합니다.
- 참조한 유사 사례 ID 를 cited_cases 에 명시합니다.
- 반드시 지정된 JSON 스키마로만 응답합니다.
"""


class FormulationInferencer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = GenerativeModel(
            settings.models.generation_model,
            system_instruction=SYSTEM_PERSONA,
        )

    def infer(
        self,
        params: PhysChemParams,
        cases: list[SimilarCase],
        dmf_text: str = "",
    ) -> FormulationProposal:
        count = self.settings.output.formulation_count
        prompt = _build_prompt(params, cases, dmf_text, count)

        config = GenerationConfig(
            temperature=self.settings.models.temperature,
            max_output_tokens=self.settings.models.max_output_tokens,
            response_mime_type="application/json",
            response_schema=formulation_response_schema(count),
        )

        logger.info("Gemini 처방 추론 시작 (model=%s, T=%.2f)",
                    self.settings.models.generation_model,
                    self.settings.models.temperature)
        response = self._model.generate_content(prompt, generation_config=config)
        data = json.loads(response.text)
        proposal = FormulationProposal(**data)
        logger.info("처방 %d종 생성 완료", len(proposal.formulations))
        return proposal

    def regenerate_improvement(self, prompt: str) -> str:
        """Step 6 불합격 시 개선안 생성 (자유 텍스트)."""
        config = GenerationConfig(
            temperature=self.settings.models.temperature,
            max_output_tokens=self.settings.models.max_output_tokens,
        )
        response = self._model.generate_content(prompt, generation_config=config)
        return response.text
