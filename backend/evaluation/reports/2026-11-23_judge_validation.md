# Judge validation (2026-11-23)

13 hand-labelled cases (`datasets/judge_validation.json`), judge `openai/gpt-oss-120b`. ✔ = the judge's verdict matches the label.

| Dimension | Agreement |
|---|---|
| faithfulness | 13 of 13 |
| citations | 8 of 8 |
| correctness | 13 of 13 |
| relevance | 13 of 13 |

| Case | Kind | Claims (supported) | Correctness | Relevance | faithfulness | citations | correctness | relevance |
|---|---|---|---|---|---|---|---|---|
| J01 | faithful and correct | 1 (1) | correct | yes | ✔ | ✔ | ✔ | ✔ |
| J02 | wrong number | 1 (0) | incorrect | yes | ✔ | – | ✔ | ✔ |
| J03 | faithful to a superseded source, so wrong | 1 (1) | incorrect | yes | ✔ | ✔ | ✔ | ✔ |
| J04 | right fact, wrong citation | 1 (1) | correct | yes | ✔ | ✔ | ✔ | ✔ |
| J05 | an invented claim mixed in | 2 (1) | incorrect | yes | ✔ | – | ✔ | ✔ |
| J06 | partial answer | 1 (1) | partial | yes | ✔ | ✔ | ✔ | ✔ |
| J07 | off-topic but faithful | 1 (1) | incorrect | no | ✔ | ✔ | ✔ | ✔ |
| J08 | outside knowledge added | 2 (1) | correct | yes | ✔ | – | ✔ | ✔ |
| J09 | arithmetic from stated numbers | 3 (3) | correct | yes | ✔ | ✔ | ✔ | ✔ |
| J10 | faithful paraphrase | 1 (1) | correct | yes | ✔ | ✔ | ✔ | ✔ |
| J11 | a cap stated in the source is ignored | 1 (0) | incorrect | yes | ✔ | – | ✔ | ✔ |
| J12 | the cap applied correctly | 1 (1) | correct | yes | ✔ | ✔ | ✔ | ✔ |
| J13 | wrong headline, right value only in a later note (real Q025 pattern) | 3 (2) | incorrect | yes | ✔ | – | ✔ | ✔ |

## Disagreements

