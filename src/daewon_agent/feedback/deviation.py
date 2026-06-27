"""Step 6: 결과 편차 분석 및 개선안 생성 (Feedback Loop).

실측값 vs 설계 기대값의 Delta 를 계산하고, 합격 기준
(용출률 ≥ 85%, 함량 ≥ 98.5%) 충족 여부를 판정한다.
불합격 시 Gemini 를 재호출해 원인 분석 및 개선안을 도출한다.
"""
from __future__ import annotations

import logging

from ..config import Settings
from ..schemas import (
    Formulation,
    ExperimentResult,
    DeviationAnalysis,
    PhysChemParams,
)

# NOTE: FormulationInferencer 는 타입 힌트용으로만 참조하며, 런타임 import 를 피해
# vertexai 미설치 환경에서도 본 모듈을 단독 테스트할 수 있게 한다.
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..inference.formulation import FormulationInferencer

logger = logging.getLogger(__name__)


def _improvement_prompt(
    params: PhysChemParams,
    formulation: Formulation,
    result: ExperimentResult,
    crit_diss: float,
    crit_assay: float,
) -> str:
    return f"""\
다음 처방의 실험 결과가 합격 기준에 미달했습니다. 원인을 분석하고 개선안을 제시하십시오.

## 물성
- API: {params.api_name}, BCS: {params.bcs_class.value if params.bcs_class else '미상'}
- 용해도 {params.solubility_mg_ml} mg/mL, logP {params.logp}

## 처방 {formulation.formulation_id}
부형제: {', '.join(f'{e.name}({e.function}, {e.amount_mg}mg)' for e in formulation.excipients)}
설계 기대: 용출 {formulation.expected_dissolution}%, 함량 {formulation.expected_assay}%

## 실측 결과
- 용출률: {result.measured_dissolution}% (기준 ≥ {crit_diss}%)
- 함량: {result.measured_assay}% (기준 ≥ {crit_assay}%)

## 요구사항
1. 미달 원인을 QbD 관점에서 분석하십시오.
2. 부형제 종류/함량 조정 등 구체적 개선안을 제시하십시오.
3. 재시험 계획을 간략히 제안하십시오.
"""


class DeviationAnalyzer:
    def __init__(self, settings: Settings, inferencer: "FormulationInferencer"):
        self.settings = settings
        self.inferencer = inferencer
        self.crit_diss = settings.acceptance_criteria.dissolution_min
        self.crit_assay = settings.acceptance_criteria.assay_min

    def analyze(
        self,
        params: PhysChemParams,
        formulation: Formulation,
        result: ExperimentResult,
    ) -> DeviationAnalysis:
        delta_diss = round(result.measured_dissolution - formulation.expected_dissolution, 2)
        delta_assay = round(result.measured_assay - formulation.expected_assay, 2)

        passed = (
            result.measured_dissolution >= self.crit_diss
            and result.measured_assay >= self.crit_assay
        )

        improvement = None
        if not passed:
            logger.info("처방 %s 불합격 → 개선안 생성", formulation.formulation_id)
            prompt = _improvement_prompt(
                params, formulation, result, self.crit_diss, self.crit_assay
            )
            improvement = self.inferencer.regenerate_improvement(prompt)
        else:
            logger.info("처방 %s 합격 → 확정", formulation.formulation_id)

        return DeviationAnalysis(
            formulation_id=formulation.formulation_id,
            delta_dissolution=delta_diss,
            delta_assay=delta_assay,
            passed=passed,
            improvement_plan=improvement,
        )
