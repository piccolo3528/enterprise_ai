---
document_id: NX-GOV-001
title: Policy Governance and Document Control Standard
version: "1.2"
status: current
effective_date: 2025-07-01
superseded_date: null
last_reviewed: 2026-06-15
next_review_due: 2027-06-15
department_owner: Governance – Policy & Compliance Office
approved_by: Chief Executive Officer
supersedes: "1.1"
superseded_by: null
amends: null
amended_by: []
classification: Internal
related_documents: [NX-HR-001, NX-GOV-002, NX-GOV-003, NX-FIN-003]
---

# Policy Governance and Document Control Standard

| Document Control | |
|---|---|
| Document ID | NX-GOV-001 |
| Version | 1.2 |
| Status | **CURRENT** |
| Effective date | 1 July 2025 |
| Last reviewed | 15 June 2026 |
| Next review due | 15 June 2027 |
| Department owner | Governance – Policy & Compliance Office (PCO) |
| Approved by | Chief Executive Officer |
| Supersedes | Version 1.1 |
| Classification | Internal |

---

## 1. Purpose

This Standard defines how Nexora Technologies Private Limited ("Nexora") creates, identifies, versions, approves, publishes, amends and retires its internal policies and procedures. It also sets the rules for deciding which document is authoritative when two documents appear to say different things.

## 2. Scope

### 2.1 Documents covered

This Standard applies to every policy, procedure, standard, guide and amendment published in the Nexora Policy Library on NexHub, regardless of the owning department.

### 2.2 Documents not covered

This Standard does not govern client contracts, statements of work, project documentation, marketing material, or individual employment letters. Where an employment letter contains a term that differs from a policy, the employment letter prevails for that employee only.

## 3. Definitions

| Term | Meaning |
|---|---|
| Policy | A document setting out mandatory rules, entitlements and obligations. |
| Procedure | A document describing the steps for carrying out a policy. |
| Standard | A document setting technical or governance requirements that other documents must follow. |
| Guide | A document providing explanation and practical help; it creates no new entitlements. |
| Amendment | A short document that changes named clauses of a base document without republishing it. |
| Document owner | The department accountable for a document's accuracy and review. |
| Canonical definition | The single authoritative statement of a shared fact, recorded in Section 10. |
| Current | The version in force today. |
| Superseded | A version replaced by a later version. |
| Withdrawn | A document retired without replacement. |
| Draft | A document under preparation; it has no effect. |

## 4. Document Hierarchy

Nexora documents rank in the following order:

1. Code of Conduct (NX-GOV-002)
2. Standards (including this document)
3. Policies
4. Procedures
5. Guides

A lower-ranked document may add detail to a higher-ranked document but may not contradict it. For example, the Employee Onboarding Guide (NX-HR-004) may explain how a new joiner completes Code of Conduct training, but it cannot change the training deadline set in NX-GOV-002.

## 5. Document Identification

### 5.1 Document ID format

Every document has a permanent ID in the format `NX-<DEPT>-<NNN>`, where `<NNN>` is a three-digit sequence number. The ID does not change between versions.

**Table 5.1 – Department codes**

| Code | Department |
|---|---|
| GOV | Governance (Policy & Compliance Office) |
| HR | Human Resources |
| FIN | Finance |
| IT | Information Technology |
| OPS | Operations |
| ENG | Engineering (reserved; no documents published) |
| SAL | Sales (reserved; no documents published) |

Engineering- and Sales-specific procedures are currently published under the OPS code.

### 5.2 Amendment IDs

An amendment takes the base document's ID followed by `-A` and a sequence number. The first amendment to NX-FIN-001 is NX-FIN-001-A1, the second would be NX-FIN-001-A2. Amendments carry their own version number.

### 5.3 File naming

Files in the Policy Library are named `<DocID>_<Title>_v<Version>`. Superseded files add the suffix `_ARCHIVED`.

## 6. Versioning

### 6.1 Major and minor versions

- A **major version** (e.g. 2.0 → 3.0) is issued for any substantive change: a change to an entitlement, limit, eligibility condition, approval authority or obligation.
- A **minor version** (e.g. 3.0 → 3.1) is issued for clarifications, corrected cross-references, formatting or wording changes that do not alter any rule.
- Calendar documents, such as the annual holiday calendar in NX-OPS-002, use the format `YYYY.N`.

### 6.2 Review without change

When a scheduled review results in no change, only the `last_reviewed` and `next_review_due` dates are updated. The version number does not change.

### 6.3 Section number stability

Within a major version, section numbers are never reused or renumbered. A section removed in a minor version remains as a heading marked "Removed in version X.Y". A new major version may renumber sections, provided its revision history records the change.

## 7. Document Status and Lifecycle

### 7.1 Status values

Every document carries one of four statuses: Draft, Current, Superseded or Withdrawn.

### 7.2 One current version

Only one version of a document ID may be Current at any time.

### 7.3 Status transition

When a new version becomes effective, the previous version becomes Superseded automatically. Its superseded date is the day before the new version's effective date. For example, if version 3.0 of a policy is effective from 1 April 2026, version 2.0 is superseded with effect from 31 March 2026.

### 7.4 Use of superseded versions

Superseded versions are retained in the Policy Library archive for seven years and carry a "SUPERSEDED" banner on their first page. A superseded version:

- must not be used to decide any matter arising after its superseded date;
- continues to govern matters that arose while it was in force, unless the new version contains a transition provision stating otherwise.

*Example:* A reimbursement claim for travel completed in May 2025 is assessed under the travel rules in force in May 2025, even if the claim is reviewed after a later amendment takes effect. A claim for travel completed after the amendment's effective date is assessed under the amended rules.

### 7.5 Withdrawal

A withdrawn document has no effect from its withdrawal date. The PCO publishes a withdrawal notice stating the reason and any replacement guidance.

## 8. Mandatory Document Metadata

Every document must display a Document Control table containing the following fields.

**Table 8.1 – Mandatory metadata**

| Field | Requirement |
|---|---|
| Document ID | Permanent ID per Section 5 |
| Title | Full title |
| Version | Per Section 6 |
| Status | Draft, Current, Superseded or Withdrawn |
| Effective date | Date from which the version applies |
| Superseded date | For superseded versions only |
| Last reviewed | Date of most recent review |
| Next review due | No later than 12 months after the last review |
| Department owner | Accountable department |
| Approved by | Approving role |
| Supersedes / Superseded by | Linked versions |
| Amends / Amended by | Linked amendments, where applicable |
| Classification | Per NX-IT-002; all policies are classified Internal |

## 9. Precedence and Conflict Resolution

### 9.1 Order of precedence

Where two documents, or two versions of a document, appear to conflict, apply the following rules in order. The first rule that resolves the conflict decides it.

1. **Applicable law** prevails over any Nexora document.
2. **Current over superseded.** A current version prevails over any superseded version, subject to Section 7.4.
3. **Amendment over base, for named clauses only.** An amendment prevails over its base document only for the sections, tables or values it explicitly identifies. Every clause the amendment does not identify remains in force exactly as written in the base document.
4. **Canonical owner over restatement.** Where a shared fact is restated in a document other than its canonical owner (Section 10), the canonical owner prevails.
5. **Specific over general.** A document dealing specifically with a subject prevails over a general document. For example, the Parental Leave Policy (NX-HR-007) prevails over the Annual Leave and Leave Management Policy (NX-HR-002) on parental leave.
6. **Code of Conduct on ethics.** On matters of ethical conduct, NX-GOV-002 prevails over any other policy.
7. **PCO interpretation.** Any conflict not resolved by rules 1–6 is referred to the PCO, which issues a written interpretation within 10 working days. Until then, the interpretation more favourable to the employee applies, unless it would create a legal, security or client-contract risk.

### 9.2 Requirements for amendments

Every amendment must state:

- the base document ID and version it amends;
- each section, table, row or value it replaces, adds or deletes;
- whether it replaces an entire table or only specific rows or values;
- the sections of the base document that remain unchanged;
- its effective date;
- whether it applies to matters already in progress on the effective date.

The base document's Document Control table is updated to list the amendment under "Amended by". The base document's version number does not change.

### 9.3 Worked examples

*Example 1 – Partial table replacement.* An amendment states that it replaces the Tier A row of a table in a base policy. The Tier B and Tier C rows of that table remain in force exactly as written in the base policy.

*Example 2 – Restated fact.* A department procedure restates a notice period that differs from the value in the canonical owner. Under rule 4, the canonical owner's value applies, and the procedure's owner must correct the restatement at its next review.

*Example 3 – Two versions retrieved.* An employee finds both version 2.0 and version 3.0 of a policy in the archive and the Policy Library. Under rule 2, version 3.0 applies to matters arising on or after its effective date.

## 10. Canonical Definitions Register

The following register identifies the single authoritative source for facts used across several documents. Other documents should refer to these sections rather than restate the values.

**Table 10.1 – Canonical owners**

| Shared fact | Canonical owner | Section |
|---|---|---|
| Document versioning, status and precedence | NX-GOV-001 | §6, §7, §9 |
| Employment categories | NX-HR-001 Employee Handbook | §3 |
| Job levels L1–L8 and level bands | NX-HR-001 Employee Handbook | §4 |
| Probation | NX-HR-001 Employee Handbook | §5 |
| Working hours and core hours | NX-HR-001 Employee Handbook | §6 |
| Leave year, leave types and entitlements | NX-HR-002 Annual Leave and Leave Management Policy | §3, §4 |
| Remote and hybrid attendance requirements | NX-HR-003 Remote and Hybrid Work Policy | §4 |
| Performance rating scale | NX-HR-005 Performance Review and Promotion Policy | §4 |
| Notice periods | NX-HR-008 Employee Exit and Offboarding Policy | §4 |
| Travel city tiers | NX-OPS-002 Office Locations, Facilities and Holiday Calendar | §4 |
| Public and restricted holidays | NX-OPS-002 Office Locations, Facilities and Holiday Calendar | §6 |
| Data classification levels | NX-IT-002 Information Classification and Data Handling Policy | §3 |
| Incident severity levels | NX-OPS-001 Business Continuity Policy | §4 |
| Code of Conduct violation severity | NX-GOV-002 Code of Conduct | §13 |
| Grievance escalation levels | NX-GOV-003 Employee Grievance and Escalation Procedure | §5 |
| Approval authority roles and financial limits | NX-FIN-003 Delegation of Authority and Approval Matrix | §3, §4 |

## 11. Review Cycle

### 11.1 Scheduled review

Every document is reviewed at least once every 12 months by its owner.

### 11.2 Triggered review

A document must be reviewed within 30 calendar days of:

- a change in applicable law;
- a change to a canonical definition it relies on;
- an internal audit finding against it.

### 11.3 Overdue documents

A document past its next review date remains in force. The PCO reports overdue documents to the CEO each quarter.

## 12. Policy Exceptions

### 12.1 Approval

An exception to any policy requires prior written approval from the authority specified in NX-FIN-003 §4. Where NX-FIN-003 does not specify an authority for the type of exception, the Department Head and the Head of HR must jointly approve it.

### 12.2 Exception register

The PCO maintains an exception register. Each entry records the policy and section, the reason, the approver and the expiry date.

### 12.3 Duration

An exception is valid for a maximum of six months unless the approval states a shorter period. It may be renewed once for up to a further six months.

### 12.4 Exceptions that cannot be granted

No exception may be granted to applicable law, to NX-GOV-002 §6 (Gifts, Hospitality and Anti-Bribery), or to any requirement in NX-IT-001 that the IT Security team classifies as mandatory.

## 13. Publication, Communication and Acknowledgement

### 13.1 Publication

Approved documents are published in the Policy Library on NexHub on or before their effective date.

### 13.2 Communication

New documents and major versions are announced by email to all affected employees and on the NexHub home page. Minor versions are listed in the monthly policy digest.

### 13.3 Acknowledgement

Employees must acknowledge new documents and major versions in NexPeople within 15 calendar days of publication. Acknowledgement status is visible to the employee's Reporting Manager and HR Business Partner.

## 14. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| Policy & Compliance Office | Maintains this Standard, the Policy Library, the canonical register and the exception register; issues interpretations |
| Document owner | Drafts, reviews and keeps documents accurate; corrects restatements of canonical facts |
| Approving authority | Approves new documents, major versions and amendments |
| Employees | Read and acknowledge documents; use the current version |

## 15. Related Documents

- NX-GOV-002 Code of Conduct
- NX-GOV-003 Employee Grievance and Escalation Procedure
- NX-HR-001 Employee Handbook
- NX-FIN-003 Delegation of Authority and Approval Matrix
- NX-IT-002 Information Classification and Data Handling Policy

## 16. Revision History

| Version | Effective date | Summary of changes |
|---|---|---|
| 1.0 | 2023-04-01 | Initial Standard: document IDs, hierarchy and review cycle. |
| 1.1 | 2024-05-01 | Added amendment numbering (Section 5.2) and the rule that superseded versions govern matters arising while in force (Section 7.4). |
| 1.2 | 2025-07-01 | Added mandatory metadata (Section 8), precedence rules (Section 9), canonical definitions register (Section 10) and exception duration limits (Section 12.3). |
