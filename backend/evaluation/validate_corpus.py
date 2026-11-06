"""Validate the Nexora evaluation corpus and dataset against CORPUS_SPEC.md.

Run from backend/ with the venv active:
    python evaluation/validate_corpus.py

Why this exists: an evaluation is only as trustworthy as its ground truth. If a question
expects "NX-HR-002 v3.0 §4.1" but that section doesn't exist, every retrieval metric computed
on that question is wrong. So we check the corpus and the dataset *before* using them.

Checks
  Documents  front matter schema; filename/folder/ID/version/status agree; matches the spec's
             version timeline; visible Document Control table agrees with front matter;
             section numbering (## N. / ### N.M / #### N.M.K) is well-formed and sequential;
             supersedes/superseded_by and amends/amended_by links are consistent;
             related_documents and in-text "NX-... §N.M" references resolve.
  Dataset    schema and enums; unique IDs; expected documents/versions/sections exist;
             answerable <-> unanswerable type; spec minimums (>= 4 amendment questions,
             >= 1 HR-002 transition question).
  Gaps       the spec's "deliberate gaps" topics don't appear to be answered in the corpus.
  Stats      per-document size and section lengths in embedding-model tokens (input for M8).

Exit code 1 if any FAIL. WARNs are things a human should look at.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
SPEC_PATH = EVAL_DIR / "CORPUS_SPEC.md"
DATASET_PATH = EVAL_DIR / "datasets" / "eval_dataset.json"

DEPT_FOLDERS = {"GOV": "governance", "HR": "hr", "FIN": "finance", "IT": "it", "OPS": "operations"}
REQUIRED_FIELDS = {
    "document_id": str, "title": str, "version": str, "status": str,
    "effective_date": dt.date, "superseded_date": (dt.date, type(None)),
    "last_reviewed": dt.date, "next_review_due": dt.date, "department_owner": str,
    "approved_by": str, "supersedes": (str, type(None)), "superseded_by": (str, type(None)),
    "amends": (str, type(None)), "amended_by": list, "classification": str,
    "related_documents": list,
}  # fmt: skip
STATUSES = {"current", "superseded", "withdrawn"}
QUESTION_TYPES = {
    "factual", "multi_passage", "multi_document", "numerical", "exception_eligibility",
    "unanswerable", "superseded", "keyword_ambiguity", "amendment_combination",
}  # fmt: skip
DOC_ID_RE = re.compile(r"^NX-(GOV|HR|FIN|IT|OPS)-\d{3}(-A\d+)?$")
FILENAME_RE = re.compile(
    r"^(?P<id>NX-[A-Z]+-\d{3}(?:-A\d+)?)_(?P<title>.+)_v(?P<ver>[\d.]+?)(?P<arch>_ARCHIVED)?\.md$"
)
HEADING_RE = re.compile(r"^(?P<hashes>#{2,4})\s+(?P<num>\d+(?:\.\d+)*)\.?\s+(?P<title>.+?)\s*$")
XREF_RE = re.compile(r"(NX-[A-Z]+-\d{3}(?:-A\d+)?)\s*(?:v[\d.]+\s*)?§\s*(\d+(?:\.\d+)*)")
# Topics the spec says must NOT be answerable from the corpus (§7).
GAP_PATTERNS = {
    "sabbatical": r"sabbatical", "stock options": r"stock option|\bESOP",
    "gym/wellness": r"\bgym\b",
    "pet policy": r"\bpets?\b", "MBA sponsorship": r"\bMBA\b", "salary bands": r"salary band",
}  # fmt: skip


@dataclass
class Doc:
    path: Path
    meta: dict
    body: str
    sections: dict[str, str] = field(default_factory=dict)  # "4.2" -> title
    section_text: dict[str, str] = field(default_factory=dict)  # "4.2" -> text under heading

    @property
    def key(self) -> str:  # "NX-HR-002 v3.0"
        return f"{self.meta['document_id']} v{self.meta['version']}"


class Report:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def __call__(self, level: str, where: str, msg: str) -> None:
        self.counts[level] += 1
        print(f"[{level}] {where}: {msg}")


report = Report()


# --------------------------------------------------------------------------- parsing
def split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("no YAML front matter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm)  # safe_load: plain data only, never arbitrary Python objects
    if not isinstance(meta, dict):
        raise ValueError("front matter is not a mapping")
    return meta, body


def parse_sections(body: str) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Return numbered headings, the text under each, and a list of numbering problems."""
    sections: dict[str, str] = {}
    text: dict[str, list[str]] = defaultdict(list)
    problems: list[str] = []
    expected_depth = {"##": 1, "###": 2, "####": 3}
    last_child: dict[str, int] = defaultdict(int)  # parent number -> last child index seen
    current: str | None = None
    in_code = False
    for line in body.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING_RE.match(line)
        if m:
            num, depth = m["num"], len(m["num"].split("."))
            if expected_depth[m["hashes"]] != depth:
                problems.append(f"'{line.strip()}' uses {m['hashes']} for a depth-{depth} number")
            parent, idx = num.rpartition(".")[0], int(num.split(".")[-1])
            if parent and parent not in sections:
                problems.append(f"§{num} appears before its parent §{parent}")
            if idx != last_child[parent] + 1:
                problems.append(
                    f"§{num} follows §{parent + '.' if parent else ''}{last_child[parent]}"
                )
            last_child[parent] = idx
            if num in sections:
                problems.append(f"duplicate §{num}")
            sections[num] = m["title"]
            current = num
        elif current:
            # Text belongs to the heading and all its ancestors (§4 contains §4.1's text).
            parts = current.split(".")
            for i in range(1, len(parts) + 1):
                text[".".join(parts[:i])].append(line)
    return sections, {k: "\n".join(v) for k, v in text.items()}, problems


def parse_timeline(spec: str) -> dict[tuple[str, str], tuple[str, dt.date]]:
    """Spec §3 table -> {(doc_id, version): (status, effective_date)}."""
    timeline = {}
    section = spec.split("## 3. Version timeline", 1)[1].split("\n## ", 1)[0]
    for row in section.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 4 and DOC_ID_RE.match(cells[0]):
            status = "superseded" if "superseded" in cells[2] else "current"
            eff = dt.date.fromisoformat(re.search(r"\d{4}-\d{2}-\d{2}", cells[3]).group())
            timeline[(cells[0], cells[1])] = (status, eff)
    return timeline


def control_table(body: str) -> dict[str, str]:
    """The visible '| Document Control | |' table under the title."""
    rows = {}
    block = body.split("| Document Control", 1)
    if len(block) == 2:
        for row in block[1].split("\n\n", 1)[0].splitlines():
            cells = [c.strip().strip("*") for c in row.strip().strip("|").split("|")]
            if len(cells) == 2 and not set(cells[0]) <= {"-", ""}:
                rows[cells[0].lower()] = cells[1]
    return rows


# --------------------------------------------------------------------------- checks
def load_documents() -> dict[str, Doc]:
    docs: dict[str, Doc] = {}
    for path in sorted(CORPUS_DIR.rglob("*.md")):
        where = path.relative_to(CORPUS_DIR).as_posix()
        try:
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            report("FAIL", where, f"cannot parse: {exc}")
            continue
        doc = Doc(path, meta, body)
        doc.sections, doc.section_text, problems = parse_sections(body)
        for p in problems:
            report("WARN", where, f"section numbering: {p}")
        docs[where] = doc
    return docs


def check_document(where: str, doc: Doc, timeline: dict) -> None:
    meta = doc.meta
    for name, typ in REQUIRED_FIELDS.items():
        if name not in meta:
            report("FAIL", where, f"missing front-matter field '{name}'")
        elif name == "next_review_due" and meta[name] is None and meta.get("status") != "current":
            continue  # a superseded version is never reviewed again
        elif not isinstance(meta[name], typ):
            report("FAIL", where, f"'{name}' has type {type(meta[name]).__name__}")
    if not isinstance(meta.get("version"), str):
        return  # an unquoted version (e.g. 3.0 -> float) already failed above
    doc_id, version, status = meta.get("document_id", ""), meta["version"], meta.get("status")

    if not DOC_ID_RE.match(doc_id):
        report("FAIL", where, f"bad document_id {doc_id!r}")
    if status not in STATUSES:
        report("FAIL", where, f"bad status {status!r}")
    if meta.get("classification") != "Internal":
        report(
            "WARN", where, f"classification is {meta.get('classification')!r}, spec says Internal"
        )

    m = FILENAME_RE.match(doc.path.name)
    if not m:
        report("FAIL", where, "filename doesn't follow <DocID>_<Title>_v<version>[_ARCHIVED].md")
    else:
        if m["id"] != doc_id or m["ver"] != version:
            report(
                "FAIL",
                where,
                f"filename says {m['id']} v{m['ver']}, front matter {doc_id} v{version}",
            )
        if bool(m["arch"]) != (status == "superseded"):
            report("FAIL", where, f"_ARCHIVED suffix doesn't match status {status!r}")
        dept = doc_id.split("-")[1]
        if doc.path.parent.name != DEPT_FOLDERS.get(dept):
            report("FAIL", where, f"{dept} document should be in '{DEPT_FOLDERS.get(dept)}/'")

    spec_entry = timeline.get((doc_id, version))
    if spec_entry is None:
        report("FAIL", where, f"{doc_id} v{version} is not in the spec's version timeline")
    else:
        spec_status, spec_eff = spec_entry
        if spec_status != status:
            report("FAIL", where, f"status {status!r}, spec timeline says {spec_status!r}")
        if spec_eff != meta.get("effective_date"):
            report(
                "FAIL", where, f"effective_date {meta.get('effective_date')}, spec says {spec_eff}"
            )
    if status == "current" and meta.get("superseded_date") is not None:
        report("FAIL", where, "current document has a superseded_date")
    if status == "superseded" and meta.get("superseded_date") is None:
        report("FAIL", where, "superseded document has no superseded_date")

    table = control_table(doc.body)
    if not table:
        report("FAIL", where, "no visible Document Control table")
    else:
        if table.get("document id") != doc_id:
            report("FAIL", where, f"control table ID {table.get('document id')!r} != {doc_id}")
        if table.get("version") != version:
            report("FAIL", where, f"control table version {table.get('version')!r} != {version}")
        # Human-readable qualifiers are allowed, e.g. "CURRENT — AMENDED" for an amended base doc.
        if not (table.get("status") or "").lower().startswith(str(status)):
            report("FAIL", where, f"control table status {table.get('status')!r} != {status}")
    if not doc.sections:
        report("FAIL", where, "no numbered sections")


def check_links(docs: dict[str, Doc]) -> None:
    by_key = {d.key: d for d in docs.values()}
    ids = {d.meta.get("document_id") for d in docs.values()}
    current = {d.meta["document_id"]: d for d in docs.values() if d.meta.get("status") == "current"}
    for where, d in docs.items():
        m = d.meta
        for rel in m.get("related_documents") or []:
            if rel not in ids:
                report("WARN", where, f"related document {rel} is not in the corpus")
        for amendment in m.get("amended_by") or []:
            a = current.get(amendment)
            if not a or not str(a.meta.get("amends", "")).startswith(m["document_id"]):
                report(
                    "FAIL",
                    where,
                    f"amended_by {amendment}, but it doesn't amend {m['document_id']}",
                )
        if m.get("amends"):
            base_id = str(m["amends"]).split()[0]
            base = current.get(base_id)
            if not base or m["document_id"] not in (base.meta.get("amended_by") or []):
                report(
                    "FAIL",
                    where,
                    f"amends {m['amends']}, but the base doesn't list it in amended_by",
                )
        if m.get("status") == "superseded":
            nxt = f"{m['document_id']} v{m.get('superseded_by')}"
            if nxt not in by_key:
                report(
                    "FAIL", where, f"superseded_by {m.get('superseded_by')!r} not found in corpus"
                )
            elif by_key[nxt].meta.get("supersedes") != m["version"]:
                report("FAIL", where, f"{nxt} doesn't list v{m['version']} in 'supersedes'")
        # In-text cross references must point at sections that exist in the current version.
        for ref_id, sec in set(XREF_RE.findall(d.body)):
            target = current.get(ref_id)
            if target is None:
                if ref_id not in ids:
                    report(
                        "WARN", where, f"text references {ref_id} §{sec}; document not in corpus"
                    )
            elif sec not in target.sections and not str(m.get("amends") or "").startswith(ref_id):
                # (An amendment may legitimately ADD a section to its base, e.g. A1 adds
                # NX-FIN-001 §5.8, so references from an amendment to its base are exempt.)
                report(
                    "WARN",
                    where,
                    f"text references {ref_id} §{sec}; no such section in {target.key}",
                )


SECTION_REF_RE = re.compile(r"^(NX-[A-Z]+-\d{3}(?:-A\d+)?) v([\d.]+) §(\d+(?:\.\d+)*)$")


def check_dataset(docs: dict[str, Doc]) -> None:
    where = "eval_dataset.json"
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    questions = data["questions"]
    by_key = {d.key: d for d in docs.values()}
    ids = {d.meta.get("document_id") for d in docs.values()}
    if data.get("question_count") != len(questions):
        report("FAIL", where, f"question_count {data.get('question_count')} != {len(questions)}")
    seen = Counter(q.get("question_id") for q in questions)
    for qid, n in seen.items():
        if n > 1:
            report("FAIL", where, f"duplicate question_id {qid}")
    required = {"question_id", "question", "expected_answer", "expected_document_ids",
                "expected_versions", "expected_sections", "question_type", "difficulty",
                "answerable", "grading_notes"}  # fmt: skip
    for q in questions:
        qw = f"{where} {q.get('question_id')}"
        missing = required - q.keys()
        if missing:
            report("FAIL", qw, f"missing fields {sorted(missing)}")
            continue
        if q["question_type"] not in QUESTION_TYPES:
            report("FAIL", qw, f"unknown question_type {q['question_type']!r}")
        if q["difficulty"] not in {"easy", "medium", "hard"}:
            report("FAIL", qw, f"unknown difficulty {q['difficulty']!r}")
        if (q["question_type"] == "unanswerable") == bool(q["answerable"]):
            report("FAIL", qw, "answerable flag contradicts question_type")
        if q["answerable"] and not q["expected_sections"]:
            report("FAIL", qw, "answerable question has no expected_sections (Recall@K impossible)")
        for doc_id in q["expected_document_ids"]:
            if doc_id not in ids:
                report("FAIL", qw, f"expected document {doc_id} not in corpus")
        for ver in q["expected_versions"]:
            if ver not in by_key:
                report("FAIL", qw, f"expected version {ver!r} not in corpus")
        for ref in q["expected_sections"]:
            m = SECTION_REF_RE.match(ref)
            if not m:
                report("FAIL", qw, f"section ref {ref!r} isn't '<DocID> v<ver> §<N.M>'")
                continue
            doc = by_key.get(f"{m[1]} v{m[2]}")
            if doc is None:
                report("FAIL", qw, f"section ref {ref!r}: document version not in corpus")
            elif m[3] not in doc.sections:
                report("FAIL", qw, f"section ref {ref!r}: no §{m[3]} in that document")
            if m[1] not in q["expected_document_ids"]:
                report("WARN", qw, f"section ref {ref!r} not listed in expected_document_ids")

    types = Counter(q["question_type"] for q in questions)
    amend = [q for q in questions if q["question_type"] == "amendment_combination"
             and {"NX-FIN-001", "NX-FIN-001-A1"} <= set(q["expected_document_ids"])]  # fmt: skip
    if len(amend) < 4:
        report("FAIL", where, f"spec requires >= 4 FIN-001 + A1 questions, found {len(amend)}")
    transition = [q for q in questions if "NX-HR-002" in q["expected_document_ids"]
                  and re.search(r"transition|carried into 2026|year-end 2026", q["question"]
                                + q["expected_answer"], re.I)]  # fmt: skip
    if not transition:
        report("FAIL", where, "spec requires >= 1 HR-002 transition-rule question")
    print(
        f"\nDataset: {len(questions)} questions | types {dict(types)} | "
        f"difficulty {dict(Counter(q['difficulty'] for q in questions))} | "
        f"amendment (FIN-001+A1) {len(amend)} | HR-002 transition {len(transition)}"
    )


def check_gaps(docs: dict[str, Doc]) -> None:
    for topic, pattern in GAP_PATTERNS.items():
        for where, d in docs.items():
            for line in d.body.splitlines():
                if re.search(pattern, line, re.I):
                    report("WARN", where, f"deliberate gap '{topic}' mentioned (check it isn't "
                                          f"answered): {line.strip()[:110]}")  # fmt: skip


def stats(docs: dict[str, Doc]) -> None:
    """Sizes in embedding-model tokens: what chunking (M8) will have to deal with."""
    try:
        import os

        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
        count = lambda s: len(tok.encode(s, add_special_tokens=False))  # noqa: E731
        unit = "tokens"
    except Exception:  # noqa: BLE001 - model not downloaded: fall back to words
        count, unit = (lambda s: len(s.split())), "words"

    print(f"\n{'document':<62} {unit:>7} {'sections':>8} {'largest §':>12}")
    totals, leaf_sizes = 0, []
    for where, d in docs.items():
        n = count(d.body)
        totals += n
        leaves = [s for s in d.sections if not any(o.startswith(s + ".") for o in d.sections)]
        sizes = {s: count(d.section_text.get(s, "")) for s in leaves}
        leaf_sizes += sizes.values()
        big = max(sizes, key=sizes.get) if sizes else "-"
        largest = f"§{big} {sizes.get(big, 0)}"
        print(f"{where:<62} {n:>7} {len(d.sections):>8} {largest:>12}")
    leaf_sizes.sort()
    if leaf_sizes:
        pct = lambda p: leaf_sizes[min(len(leaf_sizes) - 1, int(p * len(leaf_sizes)))]  # noqa: E731
        over = sum(s > 400 for s in leaf_sizes)
        print(
            f"\nTotal {totals} {unit} in {len(docs)} documents. Leaf sections: {len(leaf_sizes)}, "
            f"median {pct(0.5)}, p90 {pct(0.9)}, max {leaf_sizes[-1]} {unit}; "
            f"{over} leaf sections exceed 400 {unit} (need splitting at CHUNK_SIZE_TOKENS=400)."
        )


def main() -> int:
    timeline = parse_timeline(SPEC_PATH.read_text(encoding="utf-8"))
    docs = load_documents()
    for where, doc in docs.items():
        check_document(where, doc, timeline)
    found = {(d.meta.get("document_id"), d.meta.get("version")) for d in docs.values()}
    for doc_id, version in sorted(set(timeline) - found):
        report("FAIL", "corpus", f"spec timeline lists {doc_id} v{version}, file missing")
    check_links(docs)
    check_dataset(docs)
    check_gaps(docs)
    stats(docs)
    c = report.counts
    print(f"\nSummary: {len(docs)} documents checked | {c['FAIL']} FAIL | {c['WARN']} WARN")
    return 1 if c["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
