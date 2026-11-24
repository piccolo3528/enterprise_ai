"""Check the M15 answer judge against hand-labelled cases before trusting its numbers.

    python evaluation/validate_judge.py      # 10 Gemini calls the first time (then cached)

Writes evaluation/reports/<date>_judge_validation.md. A case agrees on a dimension when the
judge's verdict matches the label: every claim supported (faithfulness), every cited claim cites a
supporting source (citations), correctness within the acceptable verdicts, relevance.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings  # noqa: E402
from app.services.llm.prompts import SourceInput  # noqa: E402
from evaluation.harness import REPORTS_DIR  # noqa: E402
from evaluation.judge import (  # noqa: E402
    JudgeCache,
    Judgement,
    build_judge_prompt,
    judge,
    judge_client,
)

CASES = Path(__file__).resolve().parent / "datasets" / "judge_validation.json"


def agreement(case: dict, j: Judgement) -> dict[str, bool | None]:
    cited = [c.citation_correct for c in j.claims if c.citation_correct is not None]
    return {
        "faithfulness": all(c.supported for c in j.claims) == case["all_supported"],
        "citations": None if case["citation_ok"] is None else (all(cited) == case["citation_ok"]),
        "correctness": j.correctness in case["correctness"],
        "relevance": j.relevance == case["relevance"],
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    settings = load_settings()
    llm = judge_client(settings)
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cache = JudgeCache.load()
    rows = []
    for case in data["cases"]:
        sources = [
            SourceInput(i, **data["sources"][key])
            for i, key in enumerate(case["sources"], start=1)
        ]
        prompt = build_judge_prompt(sources, case["question"], case["answer"],
                                    case["expected"], case["notes"])  # fmt: skip
        j = judge(llm, llm.model, prompt, cache)
        rows.append((case, j, agreement(case, j)))
        print(case["id"], {k: v for k, v in rows[-1][2].items()}, flush=True)

    dims = ("faithfulness", "citations", "correctness", "relevance")
    lines = [
        f"# Judge validation ({date.today().isoformat()})", "",
        f"{len(rows)} hand-labelled cases (`datasets/judge_validation.json`), judge "
        f"`{llm.model}`. ✔ = the judge's verdict matches the label.", "",
        "| Dimension | Agreement |", "|---|---|",
    ]  # fmt: skip
    for d in dims:
        scored = [a[d] for _, _, a in rows if a[d] is not None]
        lines.append(f"| {d} | {sum(scored)} of {len(scored)} |")
    lines += ["", "| Case | Kind | Claims (supported) | Correctness | Relevance | "
              + " | ".join(dims) + " |", "|---|---|---|---|---|" + "---|" * len(dims)]  # fmt: skip
    for case, j, a in rows:
        marks = " | ".join("–" if a[d] is None else ("✔" if a[d] else "✘") for d in dims)
        claims = f"{len(j.claims)} ({sum(c.supported for c in j.claims)})"
        lines.append(f"| {case['id']} | {case['kind']} | {claims} | {j.correctness} | "
                     f"{j.relevance} | {marks} |")  # fmt: skip
    lines += ["", "## Disagreements", ""]
    for case, j, a in rows:
        if any(v is False for v in a.values()):
            lines.append(f"- **{case['id']}** ({case['kind']}): judge said {j.correctness} / "
                         f"{j.relevance}; {j.reason}")  # fmt: skip
            for c in j.claims:
                lines.append(f"  - {'✔' if c.supported else '✘'} \"{c.text}\" evidence "
                             f"{list(c.evidence)} cited {list(c.cited)}")  # fmt: skip
    path = REPORTS_DIR / f"{date.today().isoformat()}_judge_validation.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("report:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
