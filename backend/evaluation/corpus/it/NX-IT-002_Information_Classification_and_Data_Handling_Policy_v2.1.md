---
document_id: NX-IT-002
title: Information Classification and Data Handling Policy
version: "2.1"
status: current
effective_date: 2026-05-20
superseded_date: null
last_reviewed: 2026-05-20
next_review_due: 2027-05-20
department_owner: IT – Information Security
approved_by: Head of IT Security
supersedes: "2.0"
superseded_by: null
amends: null
amended_by: []
classification: Internal
related_documents: [NX-GOV-001, NX-GOV-002, NX-GOV-003, NX-HR-008, NX-IT-001, NX-IT-003, NX-OPS-001]
---

# Information Classification and Data Handling Policy

| Document Control | |
|---|---|
| Document ID | NX-IT-002 |
| Version | 2.1 |
| Status | **CURRENT** |
| Effective date | 20 May 2026 |
| Last reviewed | 20 May 2026 |
| Next review due | 20 May 2027 |
| Department owner | IT – Information Security |
| Approved by | Head of IT Security |
| Supersedes | Version 2.0 |
| Classification | Internal |

---

## 1. Purpose

This Policy defines how Nexora classifies information according to its sensitivity and how each class of information must be labelled, stored, shared, retained and disposed of. It is the canonical source for data classification levels (NX-GOV-001 §10).

## 2. Scope

This Policy applies to all information created, received or held by Nexora, in any form (electronic, paper or verbal), including information Nexora holds on behalf of clients. It applies to all employees, interns, contractors and consultants.

## 3. Classification Levels

### 3.1 The four levels

**Table 3.1 – Classification levels**

| Level | Definition | Examples |
|---|---|---|
| Public | Approved for release to anyone outside Nexora | Website content, published case studies, job advertisements, press releases |
| Internal | For use within Nexora; disclosure would cause minor harm | Policies in the Policy Library, organisation charts, internal announcements, training material |
| Confidential | For people who need it for their work; disclosure would cause significant harm to Nexora, a client or an individual | Client project documents and source code, contracts and statements of work, internal financial reports, grievance and investigation records, employee contact details |
| Restricted | For named individuals only; disclosure would cause severe harm or breach a legal obligation | Client production data containing personal data; passwords, encryption keys and access tokens; individual employee compensation and bank details; government ID numbers; health information; merger or acquisition plans |

### 3.2 Default classification

Information that has not been classified is treated as Internal until its owner classifies it.

### 3.3 Who classifies

The information owner (Section 11) assigns the classification when information is created or received. Client information is classified according to the client contract; where the contract is silent, client project information is Confidential and client personal data is Restricted.

### 3.4 Aggregation

A collection of information takes the highest classification of any item in it. For example, a spreadsheet combining employee names (Confidential) with bank account numbers (Restricted) is Restricted.

### 3.5 Reclassification

The information owner may reclassify information when its sensitivity changes. Information may be reclassified as Public only with the approval of Corporate Communications.

## 4. Labelling

| Level | Labelling requirement |
|---|---|
| Public | No label required |
| Internal | Label "Internal" in the document footer; not required on emails |
| Confidential | Label "Confidential" in the header and footer; email subject begins with [CONFIDENTIAL] |
| Restricted | Label "Restricted" in the header and footer and on every page; email subject begins with [RESTRICTED] |

## 5. Handling Rules

**Table 5.1 – Handling rules by classification**

| Activity | Internal | Confidential | Restricted |
|---|---|---|---|
| Storage | Approved Nexora repositories | Approved Nexora repositories with access limited to the team or project | Approved encrypted repositories with access logging only |
| Internal sharing | Any Nexora employee | Only people who need it for their work | Only named individuals approved by the information owner and the Head of IT Security |
| External sharing | Under a signed non-disclosure agreement (NDA) | Under an NDA, with Department Head approval | Only with the written approval of the information owner (or client), using encrypted transfer |
| Email | Permitted | Permitted to approved recipients | Only as an encrypted attachment, with the password sent through a different channel |
| Printing | Permitted | Secure print release only; collect immediately | Not permitted without Head of IT Security approval |
| Generative AI tools | Approved tools only (NX-IT-001 §8.2) | Nexora's approved enterprise AI assistant only | Never |
| Access from public or shared networks | Permitted with VPN | Permitted with VPN | Not permitted |
| Removable media | Not permitted (USB storage is blocked under NX-IT-001 §6.5) | Not permitted | Not permitted |
| Disposal | Normal deletion; paper in recycling bins | Secure deletion; paper shredded | Secure deletion verified by IT; paper cross-shredded |

Public information may be handled without restriction once approved for release.

## 6. Personal Data

### 6.1 Classification of personal data

Personal data about employees, candidates and client end-users is classified as follows:

- names, work contact details and job titles: Confidential;
- government ID numbers, bank details, compensation, health information and background verification results: Restricted.

### 6.2 Purpose limitation

Personal data may be used only for the purpose for which it was collected and in accordance with applicable data protection law.

### 6.3 Requests from individuals

Requests from individuals to access or correct their personal data are forwarded to the HRBP (for employee data) or the client engagement lead (for client data) within two working days.

## 7. Retention

**Table 7.1 – Retention periods**

| Record | Retention period |
|---|---|
| Employee records | 7 years after the employee's last working day |
| Grievance records | 5 years after closure (NX-GOV-003 §9) |
| Expense and travel claims | 8 years after the end of the financial year |
| Client project information | As specified in the client contract; otherwise deleted or returned within 30 calendar days of the engagement ending |
| Security logs | 12 months (NX-IT-001 §10) |
| Superseded policies | 7 years after the superseded date (NX-GOV-001 §7.4) |

At the end of the retention period, information is disposed of according to Table 5.1.

## 8. Backup

Repositories holding Confidential and Restricted information are backed up in line with the recovery objectives in NX-OPS-001. Backups are encrypted and inherit the classification of the information they contain.

## 9. Incidents Involving Information

Any actual or suspected loss, theft or unauthorised disclosure of Confidential or Restricted information, including information sent to the wrong recipient, must be reported as a security incident within one hour of discovery under NX-IT-001 §12.

## 10. Data Handover When Leaving or Changing Roles

### 10.1 Handover

Before leaving Nexora or moving to a new role, an employee transfers all Confidential and Restricted information in their custody to a custodian nominated by their Reporting Manager (NX-HR-008 §8.2).

### 10.2 Transfer, not deletion

Confidential and Restricted information must be transferred, not deleted, unless the information owner approves its deletion in writing.

### 10.3 Device wipe

IT wipes returned devices only after the Reporting Manager confirms in NexDesk that the handover is complete (NX-IT-003 §7).

## 11. Roles

| Role | Responsibility |
|---|---|
| Information owner | The person or role accountable for a set of information; classifies it, approves access to Restricted information and approves deletion |
| Custodian | Stores and protects information on the owner's behalf, including IT for systems and repositories |
| User | Handles information according to its classification |
| Head of IT Security | Owns this Policy; approves access to Restricted information jointly with the owner |

## 12. Training

All employees complete the Information Classification and Data Handling module in NexLearn within 30 calendar days of joining and every two years after that.

## 13. Related Documents

- NX-GOV-001 Policy Governance and Document Control Standard
- NX-GOV-002 Code of Conduct
- NX-GOV-003 Employee Grievance and Escalation Procedure
- NX-HR-008 Employee Exit and Offboarding Policy
- NX-IT-001 IT Security and Acceptable Use Policy
- NX-IT-003 IT Asset Issuance and Return Procedure
- NX-OPS-001 Business Continuity Policy

## 14. Revision History

| Version | Effective date | Summary of changes |
|---|---|---|
| 1.2 | 2023-11-01 | Retention table added. |
| 2.0 | 2025-06-01 | The level previously called "Highly Confidential" renamed "Restricted"; handling rules consolidated into Table 5.1; personal data classification added (Section 6); aggregation rule added. |
| 2.1 | 2026-05-20 | Minor version: cross-references added to NX-IT-001 version 3.0 (approved generative AI tools), NX-IT-003 (device wipe) and NX-GOV-003 version 2.0 (grievance record retention). No change to classification levels or handling rules. |
