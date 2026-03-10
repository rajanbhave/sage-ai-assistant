# Claims Processing Workflow

## Overview

This document defines the end-to-end claims processing workflow for the Insurance Suite motor insurance products. Use this knowledge when answering questions about claim filing, status tracking, approval workflows, documentation requirements, and timelines.

---

## Claim Statuses

| Status | Description |
|--------|-------------|
| `submitted` | Claim received and assigned a reference number. Awaiting initial review. |
| `under_review` | Claim is being assessed by a claims handler. Documents may be requested. |
| `approved` | Claim has been approved. Payment is being processed. |
| `rejected` | Claim has been declined. A rejection letter with reasons is issued. |
| `paid` | Payment has been disbursed to the policyholder or repair facility. |

---

## Claim Filing Procedure

### Step 1 — Notify the Insurer
- Contact the claims team within **24 hours** of the incident (motor collision) or **48 hours** for theft.
- Provide: policy number, date/time of incident, brief description of what happened.
- A claim reference number (e.g., `CLM-XXXXX`) is issued immediately upon notification.

### Step 2 — Submit Documentation
- Upload or post all required documents within **7 calendar days** of notification.
- Incomplete submissions pause the SLA clock until documents are received.

### Step 3 — Assessment
- A claims handler reviews the submission and may request additional information.
- For claims above **€5,000**, a field assessor or independent expert is assigned.

### Step 4 — Decision
- Approval or rejection decision issued within the SLA window (see Timelines below).
- Policyholders are notified by email and in-app notification.

### Step 5 — Payment / Repair
- Approved claims: payment transferred within **3 business days** of approval, or repair authorisation sent directly to the approved garage.

---

## Documentation Requirements by Claim Type

### Motor Collision (`motor_collision`)
- Completed claim form (online or paper)
- Police report (if third party involved or damage exceeds €1,000)
- Photos of vehicle damage (minimum 4 angles)
- Repair estimate from an approved repairer
- Driver's licence copy
- Vehicle registration document

### Motor Theft (`motor_theft`)
- Completed claim form
- Police report (mandatory — filed within 24 hours of discovery)
- All vehicle keys (original + spare)
- Vehicle registration document
- Proof of ownership (purchase invoice or V5C)
- Finance agreement (if vehicle is on finance)

### Windscreen / Glass (`motor_glass`)
- Completed claim form
- Photo of damage
- Repair or replacement invoice from approved glazing supplier
- No police report required unless vandalism suspected

### Third-Party Liability (`motor_tpl`)
- Completed claim form
- Police report
- Third-party contact details and insurer information
- Witness statements (if available)
- Photos of scene and damage

---

## Approval Workflow

```
Submitted → Initial Triage (1 business day)
         → Document Check (1–2 business days)
         → Assessment (3–5 business days for standard; 7–10 for complex)
         → Decision (Approved / Rejected)
         → Payment Processing (3 business days after approval)
```

### Escalation Paths
- **Claim value > €10,000**: Automatically escalated to Senior Claims Handler.
- **Disputed liability**: Referred to Legal & Recoveries team.
- **Fraud indicators**: Flagged to Special Investigations Unit (SIU); SLA paused.
- **Policyholder complaint**: Escalated to Customer Relations within 2 business days.

---

## Service Level Agreements (SLAs)

| Claim Type | Acknowledgement | Decision | Payment |
|------------|----------------|----------|---------|
| Motor Collision (standard) | 1 business day | 10 business days | 3 business days after approval |
| Motor Collision (complex) | 1 business day | 20 business days | 3 business days after approval |
| Motor Theft | 1 business day | 15 business days | 3 business days after approval |
| Windscreen / Glass | Same day | 2 business days | Same day as approval |
| Third-Party Liability | 1 business day | 30 business days | Subject to liability agreement |

---

## Claim Reference Format

All claims follow the format `CLM-NNNNN` (e.g., `CLM-12345`). Use this reference in all correspondence and when querying claim status via the data tools.

---

## Frequently Asked Questions

**Q: Can I track my claim online?**
A: Yes. Log in to the policyholder portal and navigate to "My Claims". Real-time status updates are shown.

**Q: What happens if I miss the documentation deadline?**
A: The claim is placed on hold. You have a further 14 days to submit before the claim is closed. A closed claim can be re-opened within 30 days with manager approval.

**Q: Can I use any repair garage?**
A: For approved claims, we recommend using our network of approved repairers for a guaranteed repair warranty. You may use a non-network garage, but you will need to obtain prior authorisation.

**Q: How do I appeal a rejection?**
A: Submit a written appeal within 28 days of the rejection letter. Appeals are reviewed by a Senior Claims Handler not involved in the original decision.
