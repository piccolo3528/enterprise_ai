# Retrieval evaluation: heading 400/60 no-header

Date 2026-11-13 · 22 documents · 333 chunks (mean 150 tokens) · 57 questions, 50 scored (answerable, labelled with sections) · top 10 shown, 20 candidates per retriever · run took 98 s (chunk+store 3.6 s, embed 19.8 s, index 3.8 s) · vectors in Qdrant's HNSW graph: 0 (0 = exact search over all vectors)

Relevance: a chunk counts if its text overlaps the body of an expected section (or a subsection of it) in the expected document **and version**. *Old version first*: of the questions about a document that exists in several versions, how often an unexpected version of it came before the expected one.

## Summary

| Variant | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | Precision@5 | MRR@10 | Tokens in top 5 | Old version first |
|---|---|---|---|---|---|---|---|---|---|---|
| semantic | 60% | 80% | 86% | 96% | 71% | 84% | 24% | 0.722 | 943 | 6 of 15 |
| semantic (no prefix) | 58% | 82% | 92% | 96% | 78% | 83% | 26% | 0.717 | 972 | 6 of 15 |
| keyword | 66% | 90% | 98% | 98% | 81% | 87% | 28% | 0.789 | 1347 | 2 of 15 |
| hybrid | 72% | 92% | 96% | 100% | 83% | 89% | 29% | 0.821 | 1206 | 1 of 15 |
| hybrid (no prefix) | 68% | 92% | 96% | 100% | 82% | 88% | 28% | 0.808 | 1222 | 2 of 15 |

## Hybrid by question type

| Type | n | Hit@5 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| amendment_combination | 6 | 83% | 38% | 0.399 |
| exception_eligibility | 6 | 100% | 94% | 0.917 |
| factual | 6 | 100% | 100% | 1.000 |
| keyword_ambiguity | 6 | 83% | 72% | 0.663 |
| multi_document | 7 | 100% | 73% | 1.000 |
| multi_passage | 5 | 100% | 100% | 0.800 |
| numerical | 7 | 100% | 100% | 0.929 |
| superseded | 7 | 100% | 87% | 0.814 |

## Can a similarity threshold detect unanswerable questions?

Top-1 cosine similarity (semantic, with prefix):

| Questions | n | min | median | max |
|---|---|---|---|---|
| answerable | 50 | 0.592 | 0.747 | 0.838 |
| unanswerable | 7 | 0.582 | 0.695 | 0.751 |

Best single threshold: 0.592 → 89% correct, vs 88% for "always answer". Unanswerable questions' top-1 scores: Q037 0.751, Q036 0.748, Q033 0.717, Q038 0.695, Q035 0.639, Q034 0.629, Q032 0.582

## Latency (server-side stages, ms)

| Variant | total p50 | total p95 | stages p50 |
|---|---|---|---|
| semantic | 239 | 248 | embed 24, connect_and_scope_check 58, vector_search 151, load_passages 62 |
| semantic (no prefix) | 239 | 249 | embed 23, connect_and_scope_check 58, vector_search 152, load_passages 63 |
| keyword | 185 | 196 | connect_and_scope_check 57, keyword_search 63, load_passages 64 |
| hybrid | 240 | 271 | embed 23, connect_and_scope_check 57, keyword_search 62, vector_search 151, load_passages 64 |
| hybrid (no prefix) | 244 | 279 | embed 22, connect_and_scope_check 58, keyword_search 65, vector_search 153, load_passages 65 |

## Hybrid failures (nothing relevant in the top 5)

- **Q050** (keyword_ambiguity) How much notice do I need to give to take a week of annual leave?
  - expected: NX-HR-002 v3.0 §5.2
  - got (top 3, sections covered): NX-HR-008 v1.4 7.1, 7.2, 7.3, 7.4; NX-HR-008 v1.4 6.1, 6.2, 6.3, 6.4, 6.5; NX-HR-002 v3.0 9.1, 9.2, 9.3, 9.4
- **Q055** (amendment_combination) What hotel limit and per diem apply to an L7 Director visiting Delhi in September 2026?
  - expected: NX-FIN-001-A1 v1.0 §3.1, NX-FIN-001-A1 v1.0 §3.2, NX-OPS-002 v2026.1 §4.1
  - got (top 3, sections covered): NX-FIN-001-A1 v1.0 6; NX-FIN-001-A1 v1.0 5.1, 5.2; NX-FIN-001 v2.0 5.1, 5.2, 5.3, 5.4, 5.5
