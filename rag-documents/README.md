# rag-documents/

Local-only folder for documents you collect yourself and want to try in the app. Everything
here except this README is **git-ignored**, because you may not have the right to publish
documents you collected.

- **The project's evaluation corpus is not here.** The fictional Nexora policies live in
  [`backend/evaluation/corpus/`](../backend/evaluation/corpus/) and are committed, so anyone can
  reproduce the evaluation. Upload from there when testing the app.
- `_spec-drafts/` holds earlier drafts (v0–v4) of the corpus authoring spec. The final spec is
  [`backend/evaluation/CORPUS_SPEC.md`](../backend/evaluation/CORPUS_SPEC.md).
- **No confidential files.** Text you upload is sent to Gemini's free tier, where Google may use it
  to improve its products, and chunk text is stored in Neon (cloud).
- **Limits (planned):** PDF, DOCX, TXT or MD; 20 MB per file. PDFs need a text layer (no OCR).
- **Don't upload the same document twice in different formats into one knowledge base.** The
  duplicate passages would crowd out other relevant results.
