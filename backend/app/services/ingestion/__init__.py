"""Turning an uploaded file into clean, structured text (M7), and later into chunks and vectors.

validation  - is this upload what it claims to be? (runs inside the request, before 202)
extractors  - PDF / DOCX / TXT / Markdown -> one common representation (list of Blocks)
cleaning    - Unicode, ligatures, hyphenated line breaks, control characters, whitespace
pipeline    - the background job and the document status lifecycle
"""
