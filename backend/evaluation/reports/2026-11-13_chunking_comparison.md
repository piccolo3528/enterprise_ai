# Chunking comparison

Date 2026-11-13 · 22 documents · 50 scored questions · run took 399 s. Same relevance rule as run_eval.py.

| Chunking | Chunks | Mean tokens | Mode | Hit@1 | Hit@5 | Recall@5 | Recall@10 | MRR@10 | Precision@5 | Tokens in top 5 | Old version first |
|---|---|---|---|---|---|---|---|---|---|---|---|
| heading 400/60 | 333 | 173 | semantic | 58% | 86% | 72% | 82% | 0.715 | 24% | 1111 | 6 of 15 |
| heading 400/60 | 333 | 173 | keyword | 66% | 98% | 81% | 87% | 0.789 | 28% | 1483 | 2 of 15 |
| heading 400/60 | 333 | 173 | hybrid | 72% | 96% | 83% | 90% | 0.814 | 29% | 1341 | 2 of 15 |
| recursive 400/60 | 164 | 332 | semantic | 56% | 90% | 74% | 81% | 0.690 | 30% | 1700 | 2 of 15 |
| recursive 400/60 | 164 | 332 | keyword | 56% | 94% | 77% | 90% | 0.717 | 30% | 1791 | 5 of 15 |
| recursive 400/60 | 164 | 332 | hybrid | 62% | 98% | 82% | 88% | 0.752 | 33% | 1771 | 3 of 15 |
| recursive 200/30 | 313 | 165 | semantic | 58% | 96% | 76% | 84% | 0.724 | 30% | 852 | 4 of 15 |
| recursive 200/30 | 313 | 165 | keyword | 60% | 90% | 69% | 79% | 0.721 | 28% | 865 | 6 of 15 |
| recursive 200/30 | 313 | 165 | hybrid | 68% | 92% | 72% | 81% | 0.788 | 29% | 856 | 5 of 15 |
| fixed 400 | 136 | 368 | semantic | 66% | 96% | 82% | 88% | 0.776 | 29% | 1909 | 3 of 15 |
| fixed 400 | 136 | 368 | keyword | 64% | 96% | 80% | 91% | 0.763 | 31% | 1969 | 4 of 15 |
| fixed 400 | 136 | 368 | hybrid | 64% | 98% | 85% | 91% | 0.782 | 32% | 1948 | 3 of 15 |
| overlap 400/60 | 155 | 374 | semantic | 60% | 92% | 76% | 84% | 0.733 | 30% | 1940 | 2 of 15 |
| overlap 400/60 | 155 | 374 | keyword | 64% | 96% | 80% | 91% | 0.770 | 34% | 1964 | 5 of 15 |
| overlap 400/60 | 155 | 374 | hybrid | 66% | 96% | 80% | 90% | 0.788 | 33% | 1968 | 5 of 15 |
