#!/usr/bin/env python3
"""Generate JSON Schema for the chargeback rebuttal contract.

Writes ``api/schemas/chargeback_json_schema.json`` from the Pydantic
``ChargebackRebuttalDocument`` model so downstream consumers (merchant SDKs,
Razorpay test fixtures) can validate rebuttals without importing Python.

Usage: python scripts/generate_chargeback_schemas.py
"""

import json
import sys
from pathlib import Path


def main() -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from api.schemas.chargeback import ChargebackRebuttalDocument

    schema = ChargebackRebuttalDocument.model_json_schema()
    schema["title"] = "ChargebackRebuttalDocument"
    schema["description"] = "Complete chargeback rebuttal contract (PayShield -> Razorpay/NPCI)"

    out = Path("api/schemas/chargeback_json_schema.json")
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(json.dumps(schema))} chars)")
    return out


if __name__ == "__main__":
    main()
