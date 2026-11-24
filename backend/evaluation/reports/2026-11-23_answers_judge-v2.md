# Answer evaluation (2026-11-23)

57 labelled questions (50 answerable, 7 unanswerable) through `rag.answer_question` with `gemini-3.5-flash-lite`, multi-query on, versions `demote`, 10 sources; judged by `gemini-3.5-flash-lite` (judge-v2, validated on hand-labelled cases: `*_judge_validation.md`). Run took 38 min. One question is 2 points of 50: smaller differences are noise.

**Faithfulness** = claims the judge found stated by the sources / all claims. **Citation accuracy** = cited claims whose citation includes a supporting source. **Correct** = the judge's verdict against the dataset's reference answer.

## Summary

| Variant | Unanswerable refused | False refusals | Correct | Partial | Incorrect | Faithfulness (claims) | Fully faithful answers | Citation accuracy | Cited passages relevant | Invalid citations | Relevance yes | Context tokens | Answer time p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rank | 7 of 7 | 0 of 50 | 44 | 6 | 0 | 100% (184 of 184) | 50 of 50 | 100% | 75% | 0 | 100% | 2508 | 7.8 / 9.1 s |
| sandwich | 7 of 7 | 3 of 50 | 44 | 3 | 0 | 100% (175 of 175) | 47 of 47 | 100% | 74% | 0 | 100% | 2508 | 2.7 / 4.1 s |
| compress | 7 of 7 | 4 of 50 | 42 | 4 | 0 | 99% (180 of 181) | 45 of 46 | 99% | 76% | 0 | 98% | 2040 | 2.6 / 3.7 s |

## Latency by stage (rank, ms)

The evaluation's judge calls share the app's rate limiter (10 calls a minute), so `plan` and `total` include queue time a lone user wouldn't have; `total minus limiter wait` removes the answer call's wait (the planning call's wait can't be separated).

| Stage | p50 | p95 | n |
|---|---|---|---|
| plan | 5225 | 6196 | 57 |
| retrieval | 1182 | 1539 | 57 |
| generate | 1282 | 2110 | 57 |
| total | 11467 | 12413 | 57 |
| total minus limiter wait | 7760 | 9128 | 57 |

## By question type (correct of n / faithfulness)

| Type | n | rank | sandwich | compress |
|---|---|---|---|---|
| amendment_combination | 6 | 5 / 100% | 4 / 100% | 5 / 100% |
| exception_eligibility | 6 | 6 / 100% | 6 / 100% | 6 / 100% |
| factual | 6 | 5 / 100% | 5 / 100% | 4 / 100% |
| keyword_ambiguity | 6 | 5 / 100% | 5 / 100% | 4 / 97% |
| multi_document | 7 | 7 / 100% | 7 / 100% | 7 / 100% |
| multi_passage | 5 | 4 / 100% | 4 / 100% | 5 / 100% |
| numerical | 7 | 6 / 100% | 7 / 100% | 5 / 100% |
| superseded | 7 | 6 / 100% | 6 / 100% | 6 / 100% |

## Answers to read: rank (not correct, or with unsupported claims)

- **Q004** (factual) partial: The answer correctly identifies Tuesday and Wednesday as mandatory anchor days, but omits mentioning that the third office day is chosen by the employee in agreement with their Reporting Manager as noted in the reference.
- **Q007** (multi_passage) partial: The answer correctly details the immediate next step (Level 2), the deadline, handlers, and turnaround times, but misses mentioning that the employee can further escalate to Level 3 if they are still unsatisfied.
- **Q025** (numerical) partial: The assistant correctly identifies that 50% applies and mentions the ₹15,000 cap in the text/note, but the final direct answer states ₹20,000 instead of being capped at ₹15,000 as per the reference answer.
- **Q044** (superseded) partial: The assistant correctly points out that city tiers are defined in NX-OPS-002 §4 (which is not provided in the sources) and lists the correct potential limits based on the provided table. However, it fails to determine that Kochi was a Tier C city at the time based on external/missing knowledge (though given the limited sources provided, it handles the missing dependency accurately by listing the conditional limits). Since the reference expects the exact limit of ₹2,500 based on Kochi's tier in 2025 (which cannot be definitively resolved solely from the provided text without NX-OPS-002), the correctness is partial because it does not state ₹2,500 as the single definitive answer, but its reasoning regarding the missing tier document is completely factual according to the sources.
- **Q046** (keyword_ambiguity) partial: The answer correctly details the data classification definition of 'Restricted', but misses the second meaning defined in the sources (restricted holidays). Because it misses one of the two definitions mentioned in the reference, the correctness is partial.
- **Q054** (amendment_combination) partial: The assistant correctly notes that city tiers are defined in another document (NX-OPS-002) not provided in full, but gives conditional limits rather than directly identifying Kochi as Tier B based on general external knowledge or making a definite statement. The reference expected a direct answer identifying Kochi as Tier B. However, the answer is fully supported by the provided text since Kochi's tier is indeed absent from the provided source excerpts.

## Answers to read: sandwich (not correct, or with unsupported claims)

- **Q004** (factual) partial: The answer correctly identifies Tuesday and Wednesday as mandatory office days, but omits the information about how the third office day is chosen.
- **Q007** (multi_passage) partial: The answer correctly addresses what to do after Level 1, the deadline, and the Level 2 timeframes, but misses mentioning that the user can further escalate to Level 3 if they are still unsatisfied after Level 2.
- **Q044** (superseded) refused (false refusal)
- **Q046** (keyword_ambiguity) partial: The assistant correctly describes the data classification meaning of 'Restricted' and its handling rules based on the provided text, but misses the alternative meaning of 'restricted holiday' mentioned in the reference grading notes (though that second meaning is only obliquely referenced as an office holiday calendar source in the texts).
- **Q054** (amendment_combination) refused (false refusal)
- **Q057** (amendment_combination) refused (false refusal)

## Answers to read: compress (not correct, or with unsupported claims)

- **Q004** (factual) partial: The answer correctly identifies Tuesday and Wednesday as mandatory days, but misses mentioning that the third office day is chosen by the employee with their Reporting Manager as per the reference answer.
- **Q005** (factual) refused (false refusal)
- **Q021** (numerical) refused (false refusal)
- **Q022** (numerical) refused (false refusal)
- **Q044** (superseded) partial: The assistant correctly states that the provided sources do not specify Kochi's city tier (referencing NX-OPS-002 which is missing) and lists the correct limits per tier for November 2025 based on the text. However, it fails to definitively provide the single correct answer (₹2,500) because it lacks the external city-tier classification document, though it correctly outlines all possibilities from the text.
- **Q046** (keyword_ambiguity) partial: The answer accurately describes 'Restricted' in terms of information classification and data handling as defined in the provided data, but it misses the secondary meaning of 'restricted holiday' mentioned in the reference grading notes.
- **Q047** (keyword_ambiguity) partial: The answer correctly identifies multiple policy contexts for 'Level 2' (job level, grievance escalation, rating, incident severity) and captures the details for grievance Level 2 well, aligning with the reference. However, it incorrectly maps 'Level 2' to the 'Internal' information classification level when the sources do not designate classification levels by numbers in that manner. Unsupported: ['Information classification Level 2 refers to Internal information requiring the label Internal in the document footer.']
- **Q054** (amendment_combination) refused (false refusal)
