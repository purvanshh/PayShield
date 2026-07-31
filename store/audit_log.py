"""Tamper-evident, PII-masked audit log (PCI-DSS 10.x).

Append-only JSONL with SHA-256 hash chaining. Every entry references the
hash of the previous entry, making retroactive modification detectable.
PII (PANs, UPI identifiers, device fingerprints) is masked before write.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AUDIT_LOG_DIR = os.getenv("AUDIT_LOG_DIR", "store/audit_logs")
HASH_CHAIN_KEY = "audit:chain:last_hash"

_PAN_PATTERNS = [
    re.compile(r"\b\d{16}\b"),
    re.compile(r"pan[\"']?\s*[:=]\s*[\"']?\d{10,19}"),
    re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
]
_UPI_PATTERN = re.compile(r"\b[\w.\-]{3,}@(?:ybl|paytm|oksbi|okhdfcbank|okicici|okaxis|upi|apl|axl|ibl|jio|mobikwik|pingpay|yono|slice)\b", re.IGNORECASE)
_DEVICE_PATTERN = re.compile(r"\b(?:DEV[-_A-Z0-9]{4,}|fp_[a-zA-Z0-9]+)\b", re.IGNORECASE)


class PIIMasker:
    @staticmethod
    def mask(value: object) -> str:
        text = str(value)
        for pattern in _PAN_PATTERNS:
            text = pattern.sub(lambda m: m.group(0)[:6] + "*" * (len(m.group(0)) - 10) + m.group(0)[-4:], text)
        text = _UPI_PATTERN.sub(lambda m: m.group(0)[:4] + "*" * 4 + "@" + m.group(0).split("@")[1], text)
        text = _DEVICE_PATTERN.sub(lambda m: m.group(0)[:4] + "*" * (len(m.group(0)) - 4), text)
        return text

    @staticmethod
    def mask_dict(data: dict) -> dict:
        SENSITIVE_KEYS = {"pan", "upi", "upi_id", "card_number", "card_no", "account_number",
                          "device_fingerprint", "device_id", "phone", "phone_number", "mobile"}
        masked = {}
        for k, v in data.items():
            if k.lower() in SENSITIVE_KEYS and isinstance(v, (str, int, float)):
                masked[k] = PIIMasker.mask(v)
            elif isinstance(v, dict):
                masked[k] = PIIMasker.mask_dict(v)
            elif isinstance(v, list):
                masked[k] = [PIIMasker.mask_dict(i) if isinstance(i, dict) else i for i in v]
            else:
                masked[k] = v
        return masked


class AuditLogWriter:
    def __init__(self, log_dir: str = AUDIT_LOG_DIR, max_entries_per_file: int = 5000):
        self.log_dir = log_dir
        self.max_entries_per_file = max_entries_per_file
        os.makedirs(self.log_dir, exist_ok=True)
        self._current_file = None
        self._entry_count = 0

    def _today_file(self) -> str:
        return os.path.join(self.log_dir, f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl")

    def _last_hash(self) -> str:
        last_file = self._latest_file()
        if not last_file:
            return "0" * 64
        try:
            with open(last_file) as f:
                lines = [l for l in f if l.strip()]
            if not lines:
                return "0" * 64
            return json.loads(lines[-1])["hash"]
        except Exception:
            return "0" * 64

    def _latest_file(self) -> str | None:
        try:
            files = [f for f in os.listdir(self.log_dir) if f.endswith(".jsonl")]
            if not files:
                return None
            return os.path.join(self.log_dir, sorted(files)[-1])
        except Exception:
            return None

    def append(self, event_type: str, actor: str, decision: str, payload: dict) -> str:
        ts = datetime.now(timezone.utc)
        entry = {
            "timestamp": ts.isoformat(),
            "event_type": event_type,
            "actor": PIIMasker.mask(actor),
            "decision": decision,
            "payload": PIIMasker.mask_dict(payload),
        }
        entry["prev_hash"] = self._last_hash()
        canonical = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        entry["hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        entry["entry_id"] = f"{ts.strftime('%Y%m%d%H%M%S%f')}_{entry['hash'][:8]}"

        filepath = self._today_file()
        if self._current_file != filepath:
            self._current_file = filepath
            self._entry_count = 0
        if self._entry_count >= self.max_entries_per_file:
            self._current_file = filepath.replace(".jsonl", f"_{ts.strftime('%H%M%S')}.jsonl")
            self._entry_count = 0

        with open(self._current_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._entry_count += 1
        return entry["entry_id"]

    def verify_chain(self) -> tuple[bool, int]:
        """Re-verify hash chain integrity across all audit files."""
        files = sorted(f for f in os.listdir(self.log_dir) if f.endswith(".jsonl"))
        if not files:
            return True, 0
        prev_hash = "0" * 64
        count = 0
        for fname in files:
            with open(os.path.join(self.log_dir, fname)) as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if entry["prev_hash"] != prev_hash:
                        return False, count
                    canonical = json.dumps(
                        {k: v for k, v in entry.items() if k != "hash"},
                        sort_keys=True, separators=(",", ":"),
                    )
                    if hashlib.sha256(canonical.encode()).hexdigest() != entry["hash"]:
                        return False, count
                    prev_hash = entry["hash"]
                    count += 1
        return True, count

    @property
    def entry_count(self) -> int:
        return self._entry_count
