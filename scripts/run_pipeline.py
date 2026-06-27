#!/usr/bin/env python
"""run_pipeline.py — 에이전트 파이프라인 CLI 엔트리포인트.

사용 예:
  # 처방 제안 (Step 1~5)
  python scripts/run_pipeline.py \
    --properties data/sample/properties.docx \
    --dmf data/sample/dmf.pdf \
    --out-dir ./output

  # 실험 결과 반영 후 최종 보고서 (Step 6~7)
  python scripts/run_pipeline.py \
    --properties ... --dmf ... --out-dir ./output \
    --results data/sample/results.json
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daewon_agent import DaewonFormulationAgent  # noqa: E402
from daewon_agent.schemas import ExperimentResult  # noqa: E402


def load_metadata(path: str | None) -> dict | None:
    if path and Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return None


def main():
    ap = argparse.ArgumentParser(description="대원제약 제제연구 에이전트")
    ap.add_argument("--properties", required=True, help="물성 데이터 요약본 (.docx)")
    ap.add_argument("--dmf", required=True, help="제조처 DMF (.pdf)")
    ap.add_argument("--out-dir", default="./output")
    ap.add_argument("--results", help="실험 결과 JSON (있으면 Step 6~7 실행)")
    ap.add_argument("--metadata", default="data/metadata.json",
                    help="벡터 검색 메타데이터 (02_build_index.py 산출물)")
    args = ap.parse_args()

    agent = DaewonFormulationAgent(metadata_store=load_metadata(args.metadata))

    # Step 1~5
    state = agent.propose(args.properties, args.dmf, args.out_dir)
    print(f"\n✔ 처방 도출표 생성: {state.xlsx_path}")
    print(f"  제안 처방: {[f.formulation_id for f in state.proposal.formulations]}")

    # Step 6~7 (실험 결과가 있을 때만)
    if args.results:
        raw = json.loads(Path(args.results).read_text(encoding="utf-8"))
        results = [ExperimentResult(**r) for r in raw]
        state = agent.finalize(state, results, args.out_dir)
        passed = [a.formulation_id for a in state.analyses if a.passed]
        print(f"\n✔ 최종 가이드 생성: {state.docx_path}")
        print(f"  합격 처방: {passed or '없음 (개선안 생성됨)'}")
    else:
        print("\n→ 연구원 Manual 실험 진행 후 --results 옵션으로 재실행하세요.")


if __name__ == "__main__":
    main()
