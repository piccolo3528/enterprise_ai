"""Print a random sample of judged answers for a human to grade (M15 judge check on real answers).

    python evaluation/spot_check.py reports/<date>_answers.json [--n 10] [--seed 15]

Shows the question, the dataset's reference and grading notes, the answer, and the judge's
verdict, so a person can record their own verdict and compare.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "datasets" / "eval_dataset.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--variant", default="rank")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=15)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    reference = {q["question_id"]: q
                 for q in json.loads(DATASET.read_text(encoding="utf-8"))["questions"]}  # fmt: skip
    rows = [r for r in json.loads(args.run.read_text(encoding="utf-8"))[args.variant]
            if r.get("judgement")]  # fmt: skip
    for r in sorted(random.Random(args.seed).sample(rows, min(args.n, len(rows))),
                    key=lambda r: r["id"]):  # fmt: skip
        ref, j = reference[r["id"]], r["judgement"]
        unsupported = [c["claim"] for c in j["claims"] if not c["supported"]]
        print(f"=== {r['id']} ({r['type']})\nQ: {ref['question']}"
              f"\nEXPECTED: {ref['expected_answer']}"
              f"\nNOTES: {ref.get('grading_notes', '')}\nANSWER: {r['answer']}\nJUDGE: "
              f"{j['correctness']} / relevance {j['relevance']} / {len(j['claims'])} claims, "
              f"unsupported {unsupported}\nREASON: {j['reason']}\n")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
