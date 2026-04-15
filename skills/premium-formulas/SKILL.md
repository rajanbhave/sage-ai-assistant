---
name: premium-formulas
description: Premium calculation formulas, pricing factors, discount rules, and rate tables.
allowed-tools: get_product_info
---
# Premium Calculation Formulas and Rules

## Overview

This document defines the premium calculation methodology for the Insurance Suite motor insurance products. Use this knowledge when answering questions about how premiums are calculated, what factors affect pricing, available discounts, and rate tables.

---

## Base Premium Calculation

The **annual gross premium** is calculated as:

```
Annual Gross Premium = Base Premium × Risk Multiplier × Coverage Factor − Discount Amount
```

Where:

- **Base Premium**: The starting rate for the product type (see Rate Tables below).
- **Risk Multiplier**: A composite factor derived from vehicle age, driver age, location, and claim history.
- **Coverage Factor**: Multiplier based on the selected coverage tier.
- **Discount Amount**: Sum of all applicable discounts (applied after risk adjustment).

### Monthly Premium

```
Monthly Premium = Annual Gross Premium / 12 × Instalment Loading Factor
```

The **Instalment Loading Factor** is `1.05` (5% surcharge for monthly payment). Annual payment avoids this surcharge.

---

## Pricing Factors

### 1. Vehicle Age Factor

| Vehicle Age (years) | Factor |
|---------------------|--------|
| 0–2 (new) | 1.20 |
| 3–5 | 1.00 (base) |
| 6–10 | 0.90 |
| 11–15 | 0.85 |
| 16+ | 0.80 |

> Newer vehicles attract a higher factor due to higher replacement cost and repair complexity.

### 2. Driver Age Factor

| Driver Age (years) | Factor |
|--------------------|--------|
| 17–24 | 1.50 |
| 25–29 | 1.20 |
| 30–49 | 1.00 (base) |
| 50–64 | 0.95 |
| 65–74 | 1.05 |
| 75+ | 1.15 |

> Young drivers (17–24) carry the highest risk factor. Experienced drivers (50–64) receive a slight reduction.

### 3. Location / Postcode Zone Factor

| Zone | Description | Factor |
|------|-------------|--------|
| Zone 1 | Rural / low-density | 0.85 |
| Zone 2 | Suburban | 1.00 (base) |
| Zone 3 | Urban | 1.15 |
| Zone 4 | High-density city centre | 1.30 |

> Zone is determined by the policyholder's registered address postcode.

### 4. Claim History Factor (last 3 years)

| Claims in Last 3 Years | Factor |
|------------------------|--------|
| 0 | 0.85 |
| 1 | 1.00 (base) |
| 2 | 1.25 |
| 3+ | 1.60 |

> Each at-fault claim in the past 3 years increases the risk factor. Non-fault claims do not affect this factor.

### Composite Risk Multiplier

```
Risk Multiplier = Vehicle Age Factor × Driver Age Factor × Location Factor × Claim History Factor
```

**Example:**
- Vehicle age: 4 years → 1.00
- Driver age: 35 → 1.00
- Location: Zone 2 (suburban) → 1.00
- Claims: 0 in last 3 years → 0.85
- **Risk Multiplier = 1.00 × 1.00 × 1.00 × 0.85 = 0.85**

---

## Coverage Tiers and Factors

| Coverage Tier | Included Coverages | Coverage Factor |
|---------------|-------------------|----------------|
| Third-Party Only (TPO) | Liability to third parties | 0.60 |
| Third-Party, Fire & Theft (TPFT) | TPO + fire + theft | 0.80 |
| Comprehensive | TPFT + own damage + windscreen + courtesy car | 1.00 (base) |
| Comprehensive Plus | Comprehensive + legal expenses + key cover + GAP | 1.15 |

---

## Rate Tables — Motor Insurance

### Base Premium by Vehicle Value

| Vehicle Value (€) | Annual Base Premium (€) |
|-------------------|------------------------|
| 0 – 5,000 | 280 |
| 5,001 – 10,000 | 380 |
| 10,001 – 20,000 | 480 |
| 20,001 – 35,000 | 620 |
| 35,001 – 50,000 | 820 |
| 50,001 – 75,000 | 1,100 |
| 75,001+ | 1,400 |

> Vehicle value is the current market value (not purchase price) at policy inception.

---

## Discount Rules

Discounts are applied **after** the risk-adjusted premium is calculated. Multiple discounts stack additively (not multiplicatively), capped at a maximum total discount of **35%**.

### Available Discounts

| Discount Code | Name | Discount % | Eligibility |
|---------------|------|-----------|-------------|
| `no_claims_bonus` | No Claims Bonus (NCB) | Up to 25% | 1 year NCB = 5%; each additional year adds 5%, max 25% |
| `multi_policy` | Multi-Policy Discount | 10% | Policyholder holds 2+ active policies with the same insurer |
| `safe_driver` | Safe Driver Telematics | 5–15% | Enrolled in telematics programme; discount based on driving score |
| `annual_payment` | Annual Payment Discount | 5% | Premium paid in full annually (no instalment loading) |
| `advanced_driver` | Advanced Driver Qualification | 5% | Holds IAM or RoSPA advanced driving qualification |
| `garage_kept` | Garaged Vehicle | 3% | Vehicle kept in a locked garage overnight |

### No Claims Bonus (NCB) Scale

| Years Claim-Free | NCB Discount |
|-----------------|-------------|
| 1 year | 5% |
| 2 years | 10% |
| 3 years | 15% |
| 4 years | 20% |
| 5+ years | 25% (maximum) |

> NCB is transferable between insurers with proof of no-claims history. NCB is lost after an at-fault claim unless NCB Protection is purchased.

### Discount Stacking Example

```
Risk-adjusted premium: €510
Discounts:
  - NCB (4 years): 20% → −€102
  - Multi-policy:  10% → −€51
  - Annual payment: 5% → −€25.50
Total discount: 35% (capped) → −€178.50
Final annual premium: €510 − €178.50 = €331.50
```

---

## Product-Type-Specific Rules

### Standard Motor (Private Car)
- Minimum driver age: 17 years
- Maximum vehicle age for comprehensive cover: 20 years
- Agreed value option available for vehicles over €35,000
- Classic car endorsement available for vehicles 25+ years old (specialist rating applies)

### Commercial Vehicle / Van
- Base premium multiplied by **1.30** (commercial use loading)
- Goods in transit cover available as add-on
- Maximum payload: 3.5 tonnes for standard motor policy

### Motorcycle
- Base premium multiplied by **1.20** (motorcycle loading)
- Engine capacity factor applied additionally:
  - Up to 125cc: ×0.80
  - 126–500cc: ×1.00
  - 501–1000cc: ×1.20
  - 1001cc+: ×1.50

---

## Worked Example — Full Premium Calculation

**Scenario:** 28-year-old driver, 3-year-old vehicle worth €18,000, Zone 3 (urban), 2 years NCB, comprehensive cover, annual payment.

```
1. Base Premium (€10,001–€20,000 band):       €480.00
2. Risk Multiplier:
   - Vehicle age (3–5 years):                  × 1.00
   - Driver age (25–29):                       × 1.20
   - Location (Zone 3 urban):                  × 1.15
   - Claim history (0 claims, 2yr NCB):        × 0.85
   Risk Multiplier = 1.00 × 1.20 × 1.15 × 0.85 = 1.173
3. Coverage Factor (Comprehensive):            × 1.00
4. Risk-Adjusted Premium = €480 × 1.173:      €563.04
5. Discounts:
   - NCB (2 years): 10%                       −€56.30
   - Annual payment: 5%                        −€28.15
   Total discount: 15%                         −€84.45
6. Final Annual Premium:                       €478.59
```

---

## Frequently Asked Questions

**Q: How is my premium affected if I add a named driver?**
A: The youngest or highest-risk named driver's age factor is used if it is higher than the main driver's factor.

**Q: Does my premium change mid-term?**
A: Premiums are fixed for the policy term. Mid-term adjustments (e.g., change of vehicle) trigger a pro-rata recalculation.

**Q: What is NCB Protection?**
A: An optional add-on that preserves your NCB after one at-fault claim per policy year. It does not prevent premium increases at renewal.

**Q: How does the telematics safe driver discount work?**
A: A telematics device or app monitors driving behaviour (speed, braking, cornering, time of day). A driving score is calculated monthly; the discount (5–15%) is applied at renewal based on the average score.
