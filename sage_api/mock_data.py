"""In-memory demo data owned by the shared Sage API boundary.

Only the Sage API HTTP boundary imports this store. Tenant selection comes from
an independently verified access-token claim before any lookup.
"""

MOCK_DATA: dict[str, dict[str, list[dict[str, object]]]] = {
    "Tenant_A": {
        "products": [
            {
                "product_id": "AXA-MOT-001",
                "name": "AXA Drive Protect",
                "type": "motor",
                "base_premium": 850.00,
                "coverage": {
                    "third_party_liability": 5_000_000,
                    "own_damage": True,
                    "theft": True,
                    "roadside_assistance": True,
                },
                "discounts": [
                    {"name": "No-Claims Bonus", "rate": 0.15},
                    {"name": "Multi-Policy", "rate": 0.10},
                    {"name": "Telematics", "rate": 0.08},
                ],
                "currency": "EUR",
            }
        ],
        "claims": [
            {
                "claim_reference": "CLM-12345",
                "policy_id": "AXA-MOT-001-POL-9981",
                "status": "approved",
                "amount": 3_200.00,
                "currency": "EUR",
                "incident_date": "2025-11-14",
                "description": "Rear-end collision on motorway — third-party at fault.",
                "documents_required": [],
                "notes": "Payment scheduled for 2025-11-28.",
            },
            {
                "claim_reference": "CLM-12346",
                "policy_id": "AXA-MOT-001-POL-9982",
                "status": "pending_documents",
                "amount": 1_500.00,
                "currency": "EUR",
                "incident_date": "2025-12-01",
                "description": "Windscreen replacement after stone chip damage.",
                "documents_required": ["repair_invoice", "photos"],
                "notes": "Awaiting repair invoice from approved repairer.",
            },
        ],
    },
    "Tenant_B": {
        "products": [
            {
                "product_id": "ALZ-MOT-001",
                "name": "Allianz AutoGuard Plus",
                "type": "motor",
                "base_premium": 920.00,
                "coverage": {
                    "third_party_liability": 10_000_000,
                    "own_damage": True,
                    "theft": True,
                    "roadside_assistance": True,
                    "legal_protection": True,
                },
                "discounts": [
                    {"name": "No-Claims Bonus", "rate": 0.20},
                    {"name": "Fleet Discount", "rate": 0.12},
                    {"name": "Annual Payment", "rate": 0.05},
                ],
                "currency": "EUR",
            }
        ],
        "claims": [
            {
                "claim_reference": "CLM-5454",
                "policy_id": "ALZ-MOT-001-POL-4421",
                "status": "under_review",
                "amount": 8_750.00,
                "currency": "EUR",
                "incident_date": "2025-10-22",
                "description": "Vehicle total loss following flood damage.",
                "documents_required": ["police_report", "valuation_report"],
                "notes": "Assessor visit scheduled for 2025-11-05.",
            },
            {
                "claim_reference": "CLM-12345",
                "policy_id": "ALZ-MOT-001-POL-6666",
                "status": "approved",
                "amount": 9_700.00,
                "currency": "EUR",
                "incident_date": "2022-11-25",
                "description": "Front-end collision on motorway.",
                "documents_required": [],
                "notes": "Payment scheduled for 2022-12-31.",
            },
            {
                "claim_reference": "CLM-5455",
                "policy_id": "ALZ-MOT-001-POL-4422",
                "status": "closed",
                "amount": 450.00,
                "currency": "EUR",
                "incident_date": "2025-09-10",
                "description": "Minor parking lot scrape — own damage.",
                "documents_required": [],
                "notes": "Settled and closed.",
            },
        ],
    },
}
