# Answer evaluation (2026-11-24)

57 labelled questions (50 answerable, 7 unanswerable) through `rag.answer_question` answered by **gemini-fallback: gemini-3.1-flash-lite, re-judged**, multi-query on, versions `demote`, 10 sources; judged by `openai/gpt-oss-120b` (judge-v3, validated on hand-labelled cases: `*_judge_validation.md`). Run took 1 min. One question is 2 points of 50: smaller differences are noise.

**Faithfulness** = claims the judge found stated by the sources / all claims. **Citation accuracy** = cited claims whose citation includes a supporting source. **Correct** = the judge's verdict against the dataset's reference answer.

## Summary

| Variant | Unanswerable refused | False refusals | Correct | Partial | Incorrect | Faithfulness (claims) | Fully faithful answers | Citation accuracy | Cited passages relevant | Invalid citations | Relevance yes | Context tokens | Answer time p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rank | 7 of 7 | 0 of 48 | 9 | 3 | 0 | 100% (55 of 55) | 12 of 12 | 100% | 77% | 0 | 100% | 2523 | 3.7 / 27.1 s |
| ↳ rank: 2 questions failed (LLM errors) and are excluded | | | | | | | | | | | | | |
| ↳ rank: 36 answers not judged yet (judge quota): excluded from correctness, faithfulness and relevance; `--rejudge` fills them | | | | | | | | | | | | | |

## Latency by stage (rank, ms)

The app's Gemini rate limiter (10 calls a minute) also queues the evaluation's back-to-back questions, so `plan` and `total` include queue time a lone user wouldn't have; `total minus limiter wait` removes the answer call's wait (the planning call's wait can't be separated). Free-tier Gemini latency varies: a slow call is the model, not the pipeline.

| Stage | p50 | p95 | n |
|---|---|---|---|
| retrieval | 1159 | 1343 | 55 |
| generate | 1781 | 11641 | 55 |
| total | 5990 | 27149 | 55 |
| total minus limiter wait | 3701 | 27149 | 55 |

## By question type (correct of n / faithfulness)

| Type | n | rank |
|---|---|---|
| amendment_combination | 5 | 0 / – |
| exception_eligibility | 6 | 0 / – |
| factual | 5 | 5 / 100% |
| keyword_ambiguity | 6 | 0 / – |
| multi_document | 7 | 1 / 100% |
| multi_passage | 5 | 3 / 100% |
| numerical | 7 | 0 / – |
| superseded | 7 | 0 / – |

## Answers to read: rank (not correct, or with unsupported claims)

- **Q001** error: llm_unavailable
- **Q007** (multi_passage) partial: The answer correctly states the escalation path, deadline, immediate escalation condition, responsible parties and resolution time, but omits the Level 2 acknowledgement timeframe and does not mention the next possible escalation to Level 3, so it is only partially complete.
- **Q011** (multi_passage) partial: The answer includes the response time and escalation details, matching the reference, but omits the requirement that a rejection must be recorded with a reason, a key fact in the expected answer.
- **Q012** (multi_document) partial: The answer correctly describes the encashment of up to 30 days of unused Annual Leave and the exclusion of other leave types, but it omits the reference’s detail about the full and final settlement being paid within 45 days, so it is only partially correct.
- **Q057** error: llm_unavailable
