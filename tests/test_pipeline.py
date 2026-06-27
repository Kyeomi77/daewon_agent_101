"""단위 테스트 — 외부 GCP 호출 없이 동작 검증 (모킹).

실행: pytest tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daewon_agent.parsers.param_extractor import extract_parameters
from daewon_agent.schemas import (
    BCSClass, PhysChemParams, Formulation, ExcipientSpec, RiskLevel,
    FormulationProposal, ExperimentResult, formulation_response_schema,
)
from daewon_agent.outputs.xlsx_writer import write_formulation_xlsx
from daewon_agent.outputs.docx_writer import write_guide_docx


# ---- Step 1: 파라미터 추출 ----------------------------------------------
def test_extract_parameters_korean():
    text = (
        "화합물명: Telmisartan\n"
        "용해도: 0.09 mg/mL\n"
        "pKa: 4.1\n"
        "logP: 7.7\n"
        "분자량: 514.6\n"
        "흡수 부위: 소장\n"
        "BCS class: II\n"
    )
    p = extract_parameters(text)
    assert p.api_name == "Telmisartan"
    assert p.solubility_mg_ml == 0.09
    assert p.pka == 4.1
    assert p.logp == 7.7
    assert p.molecular_weight == 514.6
    assert p.absorption_site == "소장"
    assert p.bcs_class == BCSClass.II


def test_extract_parameters_partial():
    p = extract_parameters("pKa: 5.0 만 존재")
    assert p.pka == 5.0
    assert p.solubility_mg_ml is None


# ---- 스키마 검증 ---------------------------------------------------------
def test_response_schema_count():
    schema = formulation_response_schema(3)
    assert schema["properties"]["formulations"]["minItems"] == 3
    assert schema["properties"]["formulations"]["maxItems"] == 3


def _sample_proposal() -> FormulationProposal:
    return FormulationProposal(
        api_name="Telmisartan",
        bcs_class=BCSClass.II,
        formulations=[
            Formulation(
                formulation_id=f"F{i}",
                rationale="BCS II 용해도 개선을 위한 고체분산체 적용",
                excipients=[
                    ExcipientSpec(name="HPMC", function="결합제", amount_mg=20.0, percent=10.0),
                    ExcipientSpec(name="SLS", function="가용화제", amount_mg=5.0, percent=2.5),
                ],
                expected_dissolution=88.0 + i,
                expected_assay=99.0,
                risk_level=RiskLevel.MEDIUM,
                risk_notes="가용화제 과량 시 안정성 저하 가능",
            )
            for i in range(1, 4)
        ],
        cited_cases=["case_001", "pubmed_12345"],
    )


# ---- Step 4: xlsx 생성 ---------------------------------------------------
def test_write_xlsx(tmp_path):
    out = write_formulation_xlsx(_sample_proposal(), tmp_path / "out.xlsx")
    assert out.exists()
    assert out.stat().st_size > 0


# ---- Step 7: docx 생성 ---------------------------------------------------
def test_write_docx(tmp_path):
    from daewon_agent.schemas import DeviationAnalysis
    analyses = [
        DeviationAnalysis(
            formulation_id="F1", delta_dissolution=2.0, delta_assay=0.5,
            passed=True, improvement_plan=None,
        ),
        DeviationAnalysis(
            formulation_id="F2", delta_dissolution=-10.0, delta_assay=-1.0,
            passed=False, improvement_plan="가용화제 함량 증대 및 입자 크기 축소 검토",
        ),
    ]
    out = write_guide_docx(_sample_proposal(), analyses, tmp_path / "guide.docx")
    assert out.exists()


# ---- Step 6: 편차 분석 로직 (모킹) --------------------------------------
def test_deviation_pass_fail(monkeypatch):
    from daewon_agent.feedback.deviation import DeviationAnalyzer

    class FakeSettings:
        class acceptance_criteria:  # noqa: N801
            dissolution_min = 85.0
            assay_min = 98.5

    class FakeInferencer:
        def regenerate_improvement(self, prompt):
            return "개선안: 붕해제 증량"

    analyzer = DeviationAnalyzer.__new__(DeviationAnalyzer)
    analyzer.settings = FakeSettings()
    analyzer.inferencer = FakeInferencer()
    analyzer.crit_diss = 85.0
    analyzer.crit_assay = 98.5

    proposal = _sample_proposal()
    f = proposal.formulations[0]

    # 합격 케이스
    res_pass = ExperimentResult(formulation_id="F1", measured_dissolution=90.0,
                                measured_assay=99.0)
    a = analyzer.analyze(_sample_params(), f, res_pass)
    assert a.passed is True
    assert a.improvement_plan is None

    # 불합격 케이스
    res_fail = ExperimentResult(formulation_id="F1", measured_dissolution=70.0,
                                measured_assay=97.0)
    a2 = analyzer.analyze(_sample_params(), f, res_fail)
    assert a2.passed is False
    assert a2.improvement_plan is not None


def _sample_params() -> PhysChemParams:
    return PhysChemParams(api_name="Telmisartan", bcs_class=BCSClass.II,
                          solubility_mg_ml=0.09, logp=7.7)
