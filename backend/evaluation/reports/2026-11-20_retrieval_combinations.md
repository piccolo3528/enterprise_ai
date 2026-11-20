# Retrieval techniques (M14)

Date 2026-11-20 · 22 documents · 333 chunks (heading 400/60) · 57 questions, 50 scored · top 10 kept (the context gets 10 sources) · run took 679 s

Same relevance rules as M11: a chunk counts if it overlaps an expected section of the expected document **and version**. *Old version first* counts questions about a multi-version document where an unexpected version came before the expected one. *Amendments R@5*: Recall@5 on the 6 `amendment_combination` questions. Latency is server-side retrieval (search + every stage), p50/p95 over the 57 questions, after a warm-up.

## Summary

| Variant | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | MRR@10 | Old version first | Amendments R@5 | Tokens in top 10 | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (hybrid, M11) | 72% | 88% | 96% | 100% | 83% | 90% | 0.814 | 2 of 15 | 49% | 2523 | 289 / 373 ms |
| versions: demote | 74% | 88% | 98% | 100% | 85% | 90% | 0.826 | 0 of 15 | 49% | 2523 | 294 / 454 ms |
| rerank 20 fused with hybrid (RRF) | 70% | 88% | 96% | 100% | 83% | 90% | 0.802 | 2 of 15 | 40% | 2463 | 3035 / 6230 ms |
| fused rerank + demote + amendments | 72% | 88% | 98% | 100% | 85% | 90% | 0.813 | 0 of 15 | 40% | 2525 | 3126 / 5989 ms |
| multi-query (3 phrasings) | 80% | 94% | 98% | 100% | 85% | 89% | 0.870 | 2 of 15 | 46% | 2566 | 1004 / 8672 ms |
| multi-query + demote | 82% | 96% | 98% | 100% | 85% | 89% | 0.881 | 0 of 15 | 46% | 2566 | 911 / 1369 ms |

## By question type (Recall@5 / MRR@10)

| Type | n | baseline (hybrid, M11) | versions: demote | rerank 20 fused with hybrid (RRF) | fused rerank + demote + amendments | multi-query (3 phrasings) | multi-query + demote |
|---|---|---|---|---|---|---|---|
| amendment_combination | 6 | 49% / 0.39 | 49% / 0.39 | 40% / 0.37 | 40% / 0.37 | 46% / 0.66 | 46% / 0.66 |
| exception_eligibility | 6 | 94% / 1.00 | 94% / 1.00 | 94% / 0.92 | 94% / 0.92 | 94% / 0.92 | 94% / 0.92 |
| factual | 6 | 100% / 0.92 | 100% / 1.00 | 100% / 1.00 | 100% / 1.00 | 100% / 0.92 | 100% / 1.00 |
| keyword_ambiguity | 6 | 72% / 0.54 | 72% / 0.54 | 89% / 0.64 | 89% / 0.64 | 89% / 0.78 | 89% / 0.78 |
| multi_document | 7 | 76% / 1.00 | 76% / 1.00 | 81% / 0.90 | 81% / 0.90 | 73% / 1.00 | 73% / 1.00 |
| multi_passage | 5 | 100% / 0.80 | 100% / 0.80 | 100% / 0.80 | 100% / 0.80 | 100% / 1.00 | 100% / 1.00 |
| numerical | 7 | 100% / 0.93 | 100% / 0.93 | 100% / 0.93 | 100% / 0.93 | 100% / 0.90 | 100% / 0.90 |
| superseded | 7 | 73% / 0.88 | 87% / 0.89 | 65% / 0.81 | 80% / 0.89 | 80% / 0.79 | 80% / 0.80 |

## Adjacent chunks in the top 10 (would merging them save tokens?)

| Variant | Questions with an adjacent pair | Pairs | Duplicate tokens at most |
|---|---|---|---|
| baseline (hybrid, M11) | 49 of 57 | 103 | 6180 (≤ 60 per pair) |
| versions: demote | 49 of 57 | 103 | 6180 (≤ 60 per pair) |
| rerank 20 fused with hybrid (RRF) | 50 of 57 | 99 | 5940 (≤ 60 per pair) |
| fused rerank + demote + amendments | 51 of 57 | 104 | 6240 (≤ 60 per pair) |
| multi-query (3 phrasings) | 50 of 57 | 102 | 6120 (≤ 60 per pair) |
| multi-query + demote | 50 of 57 | 102 | 6120 (≤ 60 per pair) |

## Failures: baseline (hybrid, M11) (nothing relevant in the top 5)

- **Q041** (superseded) How many days a week can I work from home?
- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: versions: demote (nothing relevant in the top 5)

- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: rerank 20 fused with hybrid (RRF) (nothing relevant in the top 5)

- **Q041** (superseded) How many days a week can I work from home?
- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: fused rerank + demote + amendments (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: multi-query (3 phrasings) (nothing relevant in the top 5)

- **Q055** (amendment_combination) What hotel limit and per diem apply to an L7 Director visiting Delhi in September 2026?

## Failures: multi-query + demote (nothing relevant in the top 5)

- **Q055** (amendment_combination) What hotel limit and per diem apply to an L7 Director visiting Delhi in September 2026?
