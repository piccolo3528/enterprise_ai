# Nexora Corpus — Authoring Specification

> **Authoring reference only. Do not ingest this file into the RAG index.**
> It fixes the shared facts, metadata schema and version timeline that every batch must follow. Where a value below belongs to a document not yet written, that document must use exactly this value.

---

## 1. Folder and file conventions

- Path: `corpus/<folder>/<DocID>_<Title_With_Underscores>_v<version>.md`
- Archived (superseded) files add `_ARCHIVED` before the extension, e.g. `NX-HR-002_Annual_Leave_and_Leave_Management_Policy_v2.0_ARCHIVED.md`, and sit in the same folder as the current version so the retriever sees both.
- Markdown is the single source of truth. PDF and DOCX are generated from it and never edited by hand.

## 2. Metadata schema

Every corpus file carries the metadata twice:

1. **YAML front matter** — machine-readable, for ingestion and metadata filtering.
2. **Visible "Document Control" table** under the title — because PDF/DOCX conversion usually drops front matter, and the LLM should be able to read status from the chunk text itself.

| Field | Type | Rule |
|---|---|---|
| `document_id` | string | `NX-<DEPT>-<NNN>`; amendments `NX-<DEPT>-<NNN>-A<n>` |
| `title` | string | Full title |
| `version` | string | Quoted, e.g. `"3.0"` |
| `status` | enum | `current` \| `superseded` \| `withdrawn` |
| `effective_date` | date | ISO 8601 |
| `superseded_date` | date \| null | Last day the version was in force; `null` if current |
| `last_reviewed` | date | ISO 8601 |
| `next_review_due` | date | ISO 8601 |
| `department_owner` | string | Owning department |
| `approved_by` | string | Role, never a person's name |
| `supersedes` | string \| null | Previous version (may not exist in the corpus) |
| `superseded_by` | string \| null | Next version |
| `amends` | string \| null | Amendments only: base doc ID + version |
| `amended_by` | list | Base docs only: amendment IDs in force |
| `classification` | string | Always `Internal` for policies (per NX-IT-002) |
| `related_documents` | list | Doc IDs |

Only two predecessors are physically in the corpus: NX-HR-002 v2.0 and NX-HR-003 v1.0. Other `supersedes` values (e.g. HR-001 v3.1) are realistic history only.

## 3. Version timeline

| Doc ID | Version | Status | Effective | Superseded date |
|---|---|---|---|---|
| NX-GOV-001 | 1.2 | current | 2025-07-01 | — |
| NX-GOV-002 | 3.0 | current | 2025-10-01 | — |
| NX-GOV-003 | 2.0 | current | 2026-03-01 | — |
| NX-HR-001 | 4.0 | current | 2026-01-01 | — |
| NX-HR-002 | 2.0 | **superseded** | 2024-04-01 | 2026-03-31 |
| NX-HR-002 | 3.0 | current | 2026-04-01 | — |
| NX-HR-003 | 1.0 | **superseded** | 2023-06-01 | 2026-01-31 |
| NX-HR-003 | 2.0 | current | 2026-02-01 | — |
| NX-HR-004 | 2.2 | current | 2026-02-01 | — |
| NX-HR-005 | 2.1 | current | 2026-04-01 (minor; v2.0 rules from 2025-04-01) | — |
| NX-HR-006 | 1.3 | current | 2026-01-15 | — |
| NX-HR-007 | 2.1 | current | 2026-04-01 (v2.0 entitlements from 2025-08-01; 2.1 is a terminology update, v2.0 not in corpus) | — |
| NX-HR-008 | 1.4 | current | 2026-05-01 | — |
| NX-FIN-001 | 2.0 | current (amended by A1) | 2025-04-01 | — |
| NX-FIN-001-A1 | 1.0 | current | 2026-07-01 | — |
| NX-FIN-002 | 2.3 | current | 2026-07-01 (minor; adds A1 references) | — |
| NX-FIN-003 | 2.0 | current | 2026-04-01 (v1.1 DH expense limit was ₹75,000) | — |
| NX-IT-001 | 3.1 | current | 2026-02-15 | — |
| NX-IT-002 | 2.1 | current | 2026-05-20 (minor; v2.0 rules from 2025-06-01) | — |
| NX-IT-003 | 1.0 | current | 2025-11-01 | — |
| NX-OPS-001 | 1.5 | current | 2026-06-01 | — |
| NX-OPS-002 | 2026.1 | current | 2026-01-01 | — |

## 4. Canonical facts register (locked values)

Each fact has exactly one owner. Other documents reference the owner's section and do not restate numbers unless quoting them for a worked example.

| Fact | Owner § | Locked values |
|---|---|---|
| Precedence, versioning, status | GOV-001 §6, §7, §9 | See GOV-001 |
| Employment categories | HR-001 §3 | Full-time permanent; fixed-term contract (6–24 months); intern (≤6 months) |
| Job levels | HR-001 §4 | L1 Associate · L2 Engineer/Analyst · L3 Senior Engineer/Senior Analyst · L4 Lead · L5 Manager/Principal · L6 Senior Manager · L7 Director · L8 Vice President. Bands: Foundation (L1–L2), Professional (L3–L4), Management (L5–L6), Leadership (L7–L8) |
| Probation | HR-001 §5 | 6 months (L7–L8 lateral hires: 3 months); one extension ≤3 months; max 9 months; review due ≥15 calendar days before end; deemed confirmed if review not completed |
| Working hours | HR-001 §6 | Mon–Fri, 9 h incl. 60 min break; core hours 11:00–16:00 IST; flexible start 08:00–11:00 |
| Leave year & types | HR-002 §3, §4 | Leave year Jan–Dec. **v2.0:** 18 earned leave days; carry-forward max 15; year-end encashment up to 10 days; combined casual/sick leave 10 days. **v3.0:** 20 annual leave days (1.67/month); carry-forward max 10; year-end encashment discontinued (encashment only at exit, per HR-008, max 30 days); sick leave 8 days; casual leave 6 days; ≥5 consecutive working days of annual leave need 14 calendar days' notice. Transition: balances carried into 2026 under v2.0 are retained; the 10-day cap first applies at year-end 2026. Comp-off: ≥4 h on weekend/holiday with prior RM approval, avail within 60 days, not for L6+ |
| Remote/hybrid | HR-003 §4 | **v1.0:** up to 3 WFH days/week. **v2.0:** minimum 3 office days/week, Tuesday and Wednesday are mandatory anchor days; work-from-anywhere (within India) up to 15 working days/year |
| Rating scale | HR-005 §4 | 5 Outstanding · 4 Exceeds · 3 Meets · 2 Partially Meets · 1 Does Not Meet |
| Notice periods | HR-008 §4 | Probation: 15 days (all levels). Confirmed: L1–L3 60 days; L4–L6 90 days; L7–L8 120 days |
| City tiers | OPS-002 §4 | Tier A: Mumbai, Delhi NCR (Delhi, Gurugram, Noida), Bengaluru, Hyderabad, Chennai, Kolkata, Pune. Tier B: Ahmedabad, Jaipur, Kochi, Lucknow, Chandigarh, Coimbatore, Visakhapatnam, Indore, Bhubaneswar, Nagpur. Tier C: all other domestic cities |
| Holidays | OPS-002 §6 | 10 fixed public holidays per location + 2 restricted holidays per employee per year |
| Data classes | IT-002 §3 | Public · Internal · Confidential · Restricted |
| Incident severity | OPS-001 §4 | Sev-1 Critical · Sev-2 High · Sev-3 Moderate · Sev-4 Low |
| Conduct violation severity | GOV-002 §13 | Low · Medium · High |
| Grievance levels | GOV-003 §5 | L1 Reporting Manager (ack 2 wd, resolve 7 wd); L2 HRBP + Department Head (ack 2 wd, resolve 10 wd); L3 Grievance Redressal Committee (hearing ≤10 wd, decision ≤15 wd, final) |
| Approval roles & limits | FIN-003 §3, §4 | Roles: Reporting Manager, Department Head, HR Business Partner, Head of HR, Finance Controller, CFO, CEO. Expense approvals: ≤₹25,000 RM · ₹25,001–₹1,00,000 DH · ₹1,00,001–₹5,00,000 Finance Controller · >₹5,00,000 CFO |
| Travel caps | FIN-001 §5, §6; A1 | Tier A hotel/night base: L1–L3 ₹4,500 · L4–L6 ₹6,000 · L7–L8 ₹9,000. **A1 replaces Tier A row only:** L1–L3 ₹5,500 · L4–L6 ₹7,500 · L7–L8 ₹9,000 (unchanged). Tier A per diem ₹1,200 → ₹1,500 (A1). Tier B/C rows unchanged |
| Expense claims | FIN-002 | Submit within 30 days; 31–60 days with DH approval; >60 days rejected |
| L&D budget | HR-006 | ₹30,000 (L1–L3) · ₹50,000 (L4–L6) · ₹75,000 (L7–L8) per year; 40 learning hours/year target; sponsorship >₹50,000 carries 12-month service commitment, pro-rata recovery |
| Parental leave | HR-007 | Maternity 26 weeks (first two children), 12 weeks (third+), 80-day eligibility; up to 8 weeks pre-delivery; adoption/surrogacy 12 weeks; paternity 10 working days within 3 months, max 2 blocks (v1.0 was 5 days); miscarriage 6 weeks; 12 weeks fully remote after maternity; Hyderabad on-site creche (6 months–6 years); Bengaluru/Pune creche allowance ₹5,000/month; maternity insurance sub-limits ₹50,000 normal / ₹75,000 caesarean; parental leave >4 weeks during probation extends probation |
| Leave approvals | HR-002 §5.3 → FIN-003 §4 | ≤10 consecutive working days: RM; >10: RM + DH. LWP ≤30 days: DH; 31–90 days: DH + Head of HR |
| Leave v2.0 extras | HR-002 v2.0 | Called "Earned Leave"; 1.5 days/month; ≥5-day EL needs 10 calendar days' notice; comp-off within 90 days, not L7–L8; bereavement 3 days; full EL balance encashed at exit |
| Leave v3.0 extras | HR-002 v3.0 | Bereavement 5 days (immediate family) / 2 (grandparents); marriage leave 5 days after confirmation; advance AL up to 3 days; SL certificate >2 days; CL max 3 consecutive; 2026 accrual = 19.5 days; CSL→SL conversion max 4 days + 6 SL + 4.5 CL for Apr–Dec 2026 |
| Remote extras | HR-003 v2.0 | Office day = any Nexora office, client site or business travel; <4 h badge doesn't count; WFA blocks ≤10 days, 7 days' notice, not in probation; fully remote: DH + Head of HR, 6-month approvals; internet ₹1,000 hybrid / ₹1,500 fully remote; home office ₹5,000 one-time; new joiners office every day for 4 weeks (v1.0: 2 weeks). HR-008 must define "garden leave" |
| Performance (HR-005 v2.1) | HR-005 | Cycle 1 Apr–31 Mar; ratings released by 31 May; promotions effective 1 July; time in level L1→L2 12m, L2→L3 18m, L3→L4 24m, L4→L5 24m, L5→L6 36m, L6→L7 36m, L7→L8 CEO discretion; accelerated −6 months after two Outstanding (not L6→L7); PIP 60 days + one 30-day extension; joiners after 31 Dec not rated; rating capped at Meets if mandatory training missed or Medium/High finding |
| L&D extras (HR-006 v1.3) | HR-006 | Budget year Apr–Mar; probation may use 50%; exam fee reimbursed for pass on 1st or 2nd attempt; exam leave 1 day/exam, max 4/yr; record learning within 30 days; conferences max 16 h; v1.2 budgets were ₹25k/₹40k/₹60k, commitment threshold ₹40k |
| Exit extras (HR-008 v1.4) | HR-008 | Notice starts day after resignation; shortfall recovered at basic/30 per day; F&F within 45 days of LWD; access ends 18:00 IST on LWD; expense claims must be submitted before LWD; redundancy severance 15 days' basic per completed year (min 1 month); non-solicitation 12 months; garden leave defined §6.5 |
| FIN-003 §4 must include | FIN-003 | Leave ≤10 consecutive working days RM, >10 RM + DH; LWP ≤30 days DH, 31–90 DH + Head of HR; promotions L2–L4 DH, L5–L6 DH + Head of HR, L7–L8 CEO; notice shortfall waiver ≤30 days DH, >30 DH + Head of HR; L&D ≤₹50,000 within budget RM, >₹50,000 DH, above annual budget DH + Head of HR; policy exceptions where unspecified DH + Head of HR (GOV-001 §12.1) |
| Finance extras | FIN-001/A1/002/003 | Tier B hotel ₹3,500/₹4,500/₹7,000; Tier C ₹2,500/₹3,500/₹5,500; per diem B ₹1,000, C ₹800; long stay >15 nights = 75% of cap; lodging with friends ₹1,000/night; day trip >8 h = 50% per diem; all meals provided = 25%; A1 peak-period up to +25% with DH pre-approval (§5.8); international Zone 1/Zone 2 (USD 180/260/75; 120/180/50); advances ≤80%, settle 10 working days, recover after 30 days; receipts ≥₹500; self-declaration ≤₹2,000/month; lost receipts ≤₹3,000, max 2/year; claims approved by 20th paid that month; client entertainment ₹2,000/person; corporate card L6+ ₹1.5L, L7–L8 ₹3L; FIN-003 Table 4.5: local admin DH + Head of IT Security; Restricted data access info owner + Head of IT Security; USB exception and unapproved tools/GenAI Head of IT Security; Table 4.6: Sev-2 declared by Head of Operations, Sev-1 by CEO |
| IT/OPS extras (Batch 5) | IT-001/002/003, OPS-001/002 | IT-001: passwords ≥14 chars, change every 180 days, no reuse of last 5; lockout 15 min after 5 failures; updates within 14 days; screen lock 5 min; local admin ≤90 days; USB exception ≤30 days; report incidents within 1 hour (ext 7100); refresher by 30 June; 2 failed phishing sims → retrain within 14 days; Tier 1/2/3 support; P1 30 min/4 h, P2 1 h/8 h, P3 4 wh/3 wd, P4 1 wd/10 wd; v3.0 raised password length 12→14. IT-002: "Highly Confidential" renamed Restricted in v2.0; aggregation rule; Restricted never in GenAI, Confidential only in enterprise assistant; retention employee 7 y, grievance 5 y, expenses 8 y, client data 30 days after engagement. IT-003: refresh 4 years; theft police report 24 h; first loss free; second damage 50% up to ₹15,000; recovery value −25%/completed year, min 20%; charger ₹2,500, headset ₹3,000, bag ₹1,500, monitor ₹8,000, badge ₹500; no device sales. OPS-001: Critical RTO 4 h/RPO 1 h, Essential 24/24, Standard 72/24; SMS within 30 min; safety check-in within 2 h; post-incident review 10 wd. OPS-002: HQ Hyderabad 260, Bengaluru 150, Pune 90; Pune has no fixed Christmas holiday; weekend holidays not substituted; Kochi & Coimbatore Tier C in 2025, Tier B from 2026; car parking 80/40/30 |
| IT docs must include | IT-001/002/003 | IT-001: Information Security Awareness training within 7 days of joining + annual refresher; MFA mandatory; no local admin by default; support tiers (Tier 1/2/3) for NexDesk. IT-002: data handling module every 2 years; Confidential/Restricted transferred not deleted at exit. IT-003: laptop request ≥10 working days before DOJ; NexDesk asset acknowledgement; recovery value for unreturned assets defined |
| Parental-leave rating treatment | HR-005 | Absent on parental leave >50% of cycle → previous cycle's rating carried forward, or "Meets" if no previous rating |

## 5. Shared vocabulary

- **Company:** Nexora Technologies Private Limited; founded 2011; privately held; HQ Hyderabad (HITEC City); offices in Bengaluru (Whitefield) and Pune (Hinjewadi); ~500 employees.
- **Email domain:** `nexora-tech.example` (reserved fictional domain).
- **Systems:** NexPeople (HRMS) · NexDesk (IT service desk) · NexClaim (expenses) · NexLearn (LMS) · NexHub (intranet & Policy Library).
- **Bodies:** Policy & Compliance Office (PCO) · Ethics Committee · Grievance Redressal Committee (GRC) · Internal Committee (IC, POSH) · Business Continuity Team (BCT).
- **Roles, never names:** CEO, CFO, Head of HR, Head of Compliance, Finance Controller, Department Head (DH), HR Business Partner (HRBP), Reporting Manager (RM).

## 6. Keyword collisions

| Term | Context A | Context B |
|---|---|---|
| Restricted | Data class (IT-002) | Restricted holiday (OPS-002, HR-002) |
| Level | Job level L1–L8 (HR-001) | Grievance escalation Level 1–3 (GOV-003) |
| Tier | City tier (OPS-002, FIN-001) | IT support tier (IT-001) |
| Notice | Resignation notice period (HR-008) | Leave application notice (HR-002) |
| Probation | New-hire probation (HR-001) | PIP period (HR-005) |
| Severity | Incident Sev-1 to Sev-4 (OPS-001) | Conduct violation Low/Medium/High (GOV-002) |
| Committee | Ethics Committee (GOV-002) | Grievance Redressal Committee (GOV-003) |

## 7. Deliberate gaps

Must not be answered anywhere in the corpus: salary bands or compensation figures by level; employee stock options; a Chennai office (Chennai exists only as a Tier A travel city); gym or wellness reimbursement; international relocation support (may be named only as "governed by a separate policy"); sabbatical leave; pet policy; sponsorship of degree programmes such as an MBA.

## 8. Retrieval rules (for the RAG application)

1. Filter to `status = current` by default.
2. Include superseded versions only when the question is explicitly historical ("what was the rule in 2025?", "what did v2.0 say?") **or** concerns an event dated inside that version's validity window (GOV-001 §7.4 says a superseded version still governs matters that occurred while it was in force).
3. When a base document has `amended_by`, retrieve the amendment alongside it; the amendment wins only for the clauses it names (GOV-001 §9.1 rule 3).
4. When a fact appears in several documents, prefer the canonical owner in GOV-001 §10.
5. Every answer cites document ID, version and section.

## 9. Evaluation schema

```json
{
  "question_id": "Q001",
  "question": "…",
  "expected_answer": "…",
  "expected_document_ids": ["NX-HR-002"],
  "expected_versions": ["NX-HR-002 v3.0"],
  "expected_sections": ["NX-HR-002 v3.0 §4.2"],
  "question_type": "factual | multi_passage | multi_document | numerical | exception_eligibility | unanswerable | superseded | keyword_ambiguity | amendment_combination",
  "difficulty": "easy | medium | hard",
  "answerable": true,
  "grading_notes": "Which wrong answer indicates which retrieval failure"
}
```

Include at least four `amendment_combination` questions (FIN-001 + A1), plus at least one question on the HR-002 transition rule.

## 10. Section ID rules

- Top-level sections `## N.`, subsections `### N.M`, sub-subsections `#### N.M.K`.
- Tables are titled `Table N.M` after the subsection they sit in.
- Section numbers in GOV-001 §10 are binding on documents not yet written.
- Evaluation answers cite sections as `§N.M`.
