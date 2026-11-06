---
document_id: NX-OPS-001
title: Business Continuity Policy
version: "1.5"
status: current
effective_date: 2026-06-01
superseded_date: null
last_reviewed: 2026-06-01
next_review_due: 2027-06-01
department_owner: Operations
approved_by: Chief Executive Officer
supersedes: "1.4"
superseded_by: null
amends: null
amended_by: []
classification: Internal
related_documents: [NX-GOV-001, NX-HR-001, NX-HR-002, NX-HR-003, NX-IT-001, NX-IT-002, NX-FIN-001, NX-FIN-003, NX-OPS-002]
---

# Business Continuity Policy

| Document Control | |
|---|---|
| Document ID | NX-OPS-001 |
| Version | 1.5 |
| Status | **CURRENT** |
| Effective date | 1 June 2026 |
| Last reviewed | 1 June 2026 |
| Next review due | 1 June 2027 |
| Department owner | Operations |
| Approved by | Chief Executive Officer |
| Supersedes | Version 1.4 |
| Classification | Internal |

---

## 1. Purpose

This Policy sets out how Nexora protects its people, keeps critical services running and serves its clients when a disruptive event occurs. It is the canonical source for incident severity levels (NX-GOV-001 §10).

## 2. Scope

This Policy applies to all Nexora offices (Hyderabad, Bengaluru and Pune), all employees wherever they work, employees on business travel, and the systems and vendors Nexora relies on to deliver client services.

## 3. Business Continuity Team

### 3.1 Composition

The Business Continuity Team (BCT) consists of:

- Head of Operations (BCT lead);
- Head of IT;
- Head of IT Security;
- Head of HR;
- Finance Controller;
- the Facilities Manager at each office, acting as location coordinator.

### 3.2 Responsibilities

The BCT assesses disruptive events, recommends or declares severity, activates continuity arrangements, communicates with employees and clients, and leads recovery.

## 4. Incident Severity Levels

### 4.1 Severity levels

**Table 4.1 – Incident severity levels**

| Severity | Definition | Examples | Declared by | Update frequency |
|---|---|---|---|---|
| Sev-1 Critical | A threat to life or safety; all offices unavailable; a company-wide outage of critical systems expected to last more than 4 hours; or a cyber incident affecting Restricted information or several clients' services | Major flood or earthquake affecting a city; ransomware attack on core systems | CEO, on the recommendation of the Head of Operations | Every 2 hours |
| Sev-2 High | One office unavailable for more than one working day; outage of a critical system affecting a whole department for more than 2 hours; a confirmed security breach of limited scope | Office closed by a prolonged power failure; email outage for a department | Head of Operations | Every 4 hours |
| Sev-3 Moderate | Partial disruption with a workaround available | One floor without air conditioning; a non-critical application unavailable | Facilities Manager or IT, with the BCT informed | Daily |
| Sev-4 Low | Minor disruption with no material business impact | A single meeting room unavailable; short local network interruption | Handled through normal NexDesk or Facilities processes | As needed |

### 4.2 Change of severity

The BCT lead may raise or lower a severity as an event develops. Raising an event to Sev-1 requires the CEO's declaration. Approval authorities for declarations are also listed in NX-FIN-003 §4.

### 4.3 Relationship with IT ticket priority

Severity levels are separate from NexDesk ticket priorities (P1–P4) in NX-IT-001 §13.2. Every Sev-1 or Sev-2 incident is handled as a P1 ticket.

## 5. Declaring an Incident and Activating the Plan

1. Any employee who becomes aware of a potentially disruptive event reports it to Facilities, NexDesk or a BCT member.
2. The BCT lead convenes the BCT within one hour for a potential Sev-1 or Sev-2 event.
3. The BCT assesses the event against Table 4.1 and the appropriate authority declares the severity.
4. Employees affected are notified by SMS and email within 30 minutes of the declaration.
5. The BCT activates the relevant continuity arrangements in Section 7.
6. The BCT issues updates at the frequency in Table 4.1 until the incident is closed.

## 6. Recovery Objectives

**Table 6.1 – Recovery objectives by system category**

| System category | Examples | Recovery time objective (RTO) | Recovery point objective (RPO) |
|---|---|---|---|
| Critical | Email and collaboration, VPN, identity and MFA, client delivery platforms, payroll processing in NexPeople | 4 hours | 1 hour |
| Essential | NexClaim, NexDesk, NexLearn | 24 hours | 24 hours |
| Standard | NexHub intranet | 72 hours | 24 hours |

Backups of repositories holding Confidential and Restricted information are encrypted and stored in a second cloud region (NX-IT-002 §8). Disaster recovery for Critical systems is tested at least once a year.

## 7. Continuity Arrangements

**Table 7.1 – Scenarios and primary responses**

| Scenario | Primary response |
|---|---|
| One office unavailable | Affected employees work remotely; teams with client obligations requiring office facilities may relocate to another Nexora office |
| All offices unavailable in a city, or several cities | Mandatory remote working for affected employees |
| Critical IT system outage | IT recovery to the RTO in Table 6.1; manual workarounds for payroll and client communication |
| Cyber incident | Containment led by the Head of IT Security under NX-IT-001 §12; affected systems isolated |
| Epidemic or pandemic | Mandatory remote working; business travel restricted; office access limited to approved staff |
| Failure of a key vendor | Switch to the alternate vendor named in the vendor continuity register |

### 7.1 Mandatory remote working

When the BCT requires employees to work remotely, that requirement overrides the minimum office attendance in NX-HR-003 §4 for the period declared. Mandatory remote working for one office is approved by the Head of Operations; for all offices, by the CEO.

### 7.2 Office closures and leave

Days on which an office is closed are not deducted from employees' leave balances, unless the declaration requires employees to work remotely (NX-HR-002 §9.4). Employees receive full pay during closures.

### 7.3 Recall from leave

During a declared Sev-1 incident only, the CEO may recall employees with critical roles from Annual Leave. Recalled days are re-credited (NX-HR-002 §5.5).

## 8. Employee Responsibilities

Every employee must:

- take their laptop and charger home at the end of each working day, unless they use an assigned locker (NX-IT-001 §6.6);
- keep their mobile number and emergency contact up to date in NexPeople (NX-HR-001 §13.1);
- respond to a safety check-in message within 2 hours during a Sev-1 or Sev-2 incident;
- know the evacuation route and assembly point for their office and follow the instructions of floor wardens.

## 9. Travellers

The Travel Desk's records of travellers' locations (NX-FIN-001 §14.2) are used by the BCT to contact employees on business travel during a Sev-1 or Sev-2 incident. Travellers must respond to a safety check-in within 2 hours and follow the BCT's instructions, which may include returning early at Nexora's cost.

## 10. Testing and Maintenance

**Table 10.1 – Testing schedule**

| Test | Frequency |
|---|---|
| Evacuation drill at each office | Twice a year |
| BCT tabletop exercise | Twice a year |
| Disaster recovery test for Critical systems | Once a year |
| Review of the vendor continuity register | Once a year |

Test results and improvement actions are reported to the CEO within 15 working days of each test.

## 11. Post-Incident Review

The BCT completes a post-incident review within 10 working days of closing any Sev-1 or Sev-2 incident. The review records the timeline, impact, what worked, what did not and the actions agreed, with owners and deadlines.

## 12. Related Documents

- NX-GOV-001 Policy Governance and Document Control Standard
- NX-HR-001 Employee Handbook
- NX-HR-002 Annual Leave and Leave Management Policy
- NX-HR-003 Remote and Hybrid Work Policy
- NX-IT-001 IT Security and Acceptable Use Policy
- NX-IT-002 Information Classification and Data Handling Policy
- NX-FIN-001 Travel and Accommodation Policy
- NX-FIN-003 Delegation of Authority and Approval Matrix
- NX-OPS-002 Office Locations, Facilities and Holiday Calendar

## 13. Revision History

| Version | Effective date | Summary of changes |
|---|---|---|
| 1.0 | 2023-06-01 | Initial policy. |
| 1.4 | 2025-06-01 | Minor version: BCT membership updated to include the Head of IT Security. |
| 1.5 | 2026-06-01 | Minor version: references updated to NX-HR-003 version 2.0 (mandatory remote working overrides minimum office days), NX-HR-002 version 3.0 (office closures and recall from leave) and NX-FIN-003 version 2.0 (declaration authorities). No change to severity levels or recovery objectives. |
