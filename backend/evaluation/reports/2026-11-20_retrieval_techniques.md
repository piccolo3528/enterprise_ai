# Retrieval techniques (M14)

Date 2026-11-20 · 22 documents · 333 chunks (heading 400/60) · 57 questions, 50 scored · top 10 kept (the context gets 10 sources) · run took 2045 s

Same relevance rules as M11: a chunk counts if it overlaps an expected section of the expected document **and version**. *Old version first* counts questions about a multi-version document where an unexpected version came before the expected one. *Amendments R@5*: Recall@5 on the 6 `amendment_combination` questions. Latency is server-side retrieval (search + every stage), p50/p95 over the 57 questions, after a warm-up.

## Summary

| Variant | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | MRR@10 | Old version first | Amendments R@5 | Tokens in top 10 | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline (hybrid, M11) | 72% | 88% | 96% | 100% | 83% | 90% | 0.814 | 2 of 15 | 49% | 2528 | 364 / 432 ms |
| rerank pool 20 | 64% | 88% | 98% | 100% | 81% | 92% | 0.770 | 4 of 15 | 32% | 2381 | 4109 / 4850 ms |
| rerank pool 30 | 64% | 82% | 98% | 100% | 81% | 90% | 0.764 | 4 of 15 | 32% | 2350 | 5062 / 6804 ms |
| rerank pool 50 | 64% | 82% | 98% | 100% | 81% | 88% | 0.764 | 4 of 15 | 32% | 2332 | 8582 / 12744 ms |
| versions: demote | 74% | 88% | 98% | 100% | 85% | 90% | 0.826 | 0 of 15 | 49% | 2528 | 388 / 571 ms |
| versions: filter | 74% | 88% | 98% | 100% | 85% | 90% | 0.826 | 0 of 15 | 49% | 2439 | 373 / 452 ms |
| amendments | 72% | 86% | 96% | 100% | 83% | 90% | 0.809 | 2 of 15 | 49% | 2536 | 474 / 857 ms |
| rerank 20 + demote | 70% | 90% | 98% | 100% | 82% | 92% | 0.803 | 0 of 15 | 32% | 2436 | 3925 / 4514 ms |
| rerank 20 + demote + amendments | 70% | 90% | 98% | 100% | 82% | 92% | 0.803 | 0 of 15 | 32% | 2448 | 3862 / 7917 ms |
| demote + amendments (no rerank) | 74% | 86% | 98% | 100% | 85% | 90% | 0.821 | 0 of 15 | 49% | 2536 | 442 / 787 ms |
| multi-query (3 phrasings) | 80% | 94% | 98% | 100% | 85% | 89% | 0.870 | 2 of 15 | 46% | 2557 | 1032 / 1075 ms |
| multi-query + rerank 20 + demote + amendments | 70% | 90% | 98% | 100% | 81% | 92% | 0.808 | 0 of 15 | 32% | 2492 | 4375 / 5386 ms |

## By question type (Recall@5 / MRR@10)

| Type | n | baseline (hybrid, M11) | rerank pool 20 | rerank pool 30 | rerank pool 50 | versions: demote | versions: filter | amendments | rerank 20 + demote | rerank 20 + demote + amendments | demote + amendments (no rerank) | multi-query (3 phrasings) | multi-query + rerank 20 + demote + amendments |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| amendment_combination | 6 | 49% / 0.39 | 32% / 0.35 | 32% / 0.32 | 32% / 0.32 | 49% / 0.39 | 49% / 0.39 | 49% / 0.39 | 32% / 0.35 | 32% / 0.35 | 49% / 0.39 | 46% / 0.66 | 32% / 0.35 |
| exception_eligibility | 6 | 94% / 1.00 | 83% / 0.81 | 83% / 0.79 | 83% / 0.79 | 94% / 1.00 | 94% / 1.00 | 94% / 1.00 | 83% / 0.89 | 83% / 0.89 | 94% / 1.00 | 94% / 0.92 | 83% / 0.92 |
| factual | 6 | 100% / 0.92 | 100% / 0.92 | 100% / 0.92 | 100% / 0.92 | 100% / 1.00 | 100% / 1.00 | 100% / 0.92 | 100% / 0.92 | 100% / 0.92 | 100% / 1.00 | 100% / 0.92 | 100% / 0.92 |
| keyword_ambiguity | 6 | 72% / 0.54 | 81% / 0.67 | 81% / 0.66 | 81% / 0.66 | 72% / 0.54 | 72% / 0.54 | 72% / 0.50 | 81% / 0.68 | 81% / 0.68 | 72% / 0.50 | 89% / 0.78 | 81% / 0.68 |
| multi_document | 7 | 76% / 1.00 | 75% / 0.83 | 75% / 0.83 | 75% / 0.83 | 76% / 1.00 | 76% / 1.00 | 76% / 1.00 | 79% / 0.83 | 79% / 0.83 | 76% / 1.00 | 73% / 1.00 | 75% / 0.83 |
| multi_passage | 5 | 100% / 0.80 | 100% / 0.90 | 100% / 0.90 | 100% / 0.90 | 100% / 0.80 | 100% / 0.80 | 100% / 0.80 | 100% / 0.90 | 100% / 0.90 | 100% / 0.80 | 100% / 1.00 | 100% / 0.90 |
| numerical | 7 | 100% / 0.93 | 100% / 1.00 | 100% / 1.00 | 100% / 1.00 | 100% / 0.93 | 100% / 0.93 | 100% / 0.93 | 100% / 1.00 | 100% / 1.00 | 100% / 0.93 | 100% / 0.90 | 100% / 1.00 |
| superseded | 7 | 73% / 0.88 | 80% / 0.67 | 80% / 0.67 | 80% / 0.67 | 87% / 0.89 | 87% / 0.89 | 73% / 0.88 | 80% / 0.83 | 80% / 0.83 | 87% / 0.89 | 80% / 0.79 | 80% / 0.83 |

## Adjacent chunks in the top 10 (would merging them save tokens?)

| Variant | Questions with an adjacent pair | Pairs | Duplicate tokens at most |
|---|---|---|---|
| baseline (hybrid, M11) | 49 of 57 | 102 | 6120 (≤ 60 per pair) |
| rerank pool 20 | 49 of 57 | 100 | 6000 (≤ 60 per pair) |
| rerank pool 30 | 44 of 57 | 93 | 5580 (≤ 60 per pair) |
| rerank pool 50 | 47 of 57 | 97 | 5820 (≤ 60 per pair) |
| versions: demote | 49 of 57 | 102 | 6120 (≤ 60 per pair) |
| versions: filter | 48 of 57 | 98 | 5880 (≤ 60 per pair) |
| amendments | 49 of 57 | 104 | 6240 (≤ 60 per pair) |
| rerank 20 + demote | 52 of 57 | 104 | 6240 (≤ 60 per pair) |
| rerank 20 + demote + amendments | 51 of 57 | 98 | 5880 (≤ 60 per pair) |
| demote + amendments (no rerank) | 49 of 57 | 103 | 6180 (≤ 60 per pair) |
| multi-query (3 phrasings) | 48 of 57 | 98 | 5880 (≤ 60 per pair) |
| multi-query + rerank 20 + demote + amendments | 53 of 57 | 102 | 6120 (≤ 60 per pair) |

## A rerank-score threshold for the context? (rerank pool 20, top 10)

| Drop passages scoring below | Relevant passages lost | Irrelevant dropped | Tokens saved per question |
|---|---|---|---|
| -10 | 0 of 88 | 35 of 482 | 170 |
| -8 | 3 of 88 | 79 of 482 | 380 |
| -6 | 5 of 88 | 131 of 482 | 601 |
| -4 | 17 of 88 | 239 of 482 | 1097 |
| -2 | 33 of 88 | 327 of 482 | 1537 |
| 0 | 45 of 88 | 388 of 482 | 1807 |

## Failures: baseline (hybrid, M11) (nothing relevant in the top 5)

- **Q041** (superseded) How many days a week can I work from home?
- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: rerank pool 20 (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: rerank pool 30 (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: rerank pool 50 (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: versions: demote (nothing relevant in the top 5)

- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: versions: filter (nothing relevant in the top 5)

- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: amendments (nothing relevant in the top 5)

- **Q041** (superseded) How many days a week can I work from home?
- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: rerank 20 + demote (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: rerank 20 + demote + amendments (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?

## Failures: demote + amendments (no rerank) (nothing relevant in the top 5)

- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?

## Failures: multi-query (3 phrasings) (nothing relevant in the top 5)

- **Q055** (amendment_combination) What hotel limit and per diem apply to an L7 Director visiting Delhi in September 2026?

## Failures: multi-query + rerank 20 + demote + amendments (nothing relevant in the top 5)

- **Q052** (amendment_combination) What is the hotel limit and per diem for an L5 Manager travelling to Mumbai in August 2026?
