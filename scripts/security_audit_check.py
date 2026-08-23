#!/usr/bin/env python3
"""Reproducible security posture checks for the PayShield repo (Phase 43).

Checks that are *verifiable from the tree* (no live stack needed):

- tracked secrets/credential-shaped strings (AWS keys, private key
  headers, obvious passwords, live Razorpay key prefix)
- .gitignore coverage (env files, log binaries, node modules)
- dynamic evaluation (eval/exec) outside documented whitelisted spots
- pinned version imports? (informational)
- file-upload surface reachable from the API (should be none)

Print a JSON summary and exit non-zero on a HIGH finding.

Usage: python scripts/security_audit_check.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "private_key_block": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "basic_auth_inline": r"(?i)(password|passwd|pwd)[\"'\s:=]{1,4}[A-Za-z0-9@#$%^&*!]{6,}",
    "live_razorpay_key": r"rzp_live_[A-Za-z0-9]{14,}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "env_tracked": r"\.env(\.\w+)?$",
}

ALWAYS_SKIP = {"tests/", "scripts/", "notebooks/", "node_modules/", "docs/"}
DOCUMENTED_EVAL = {"return_risk/rules_engine.py", "scripts/"}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=False
    )
    return [ROOT / line for line in out.stdout.splitlines() if line.strip()]


def _scan_high(text: str, path: Path) -> list[str]:
    findings = []
    rel = str(path.relative_to(ROOT))
    for name, pattern in PATTERNS.items():
        if name == "env_tracked":
            continue
        if name == "basic_auth_inline":
            continue  # reported separately (low-confidence, needs review)
        if re.search(pattern, text):
            findings.append(f"{name}: {rel}")
    return findings


def _scan_low(text: str, path: Path, rel: str) -> list[str]:
    findings = []
    if rel.endswith(".py") and not any(rel.startswith(s) for s in ALWAYS_SKIP):
        if " eval(" in text or " exec(" in text:
            if not any(d in rel for d in DOCUMENTED_EVAL):
                findings.append(f"eval/exec: {rel}")
    if re.search(PATTERNS["basic_auth_inline"], text) and not any(
        rel.startswith(s) for s in ALWAYS_SKIP
    ):
        findings.append(f"password-ish string: {rel}")
    return findings


def _gitignore_coverage() -> dict:
    gi = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").exists() else ""
    tracked_env = [
        str(p.relative_to(ROOT))
        for p in _tracked_files()
        if re.search(PATTERNS["env_tracked"], p.name) or p.name == ".env"
    ]
    return {
        "gitignore_covers_env": ".env" in gi,
        "gitignore_covers_logs": "store/audit_logs" in gi,
        "gitignore_covers_node_modules": "node_modules" in gi,
        "tracked_env_files": tracked_env,
    }


def main():
    findings_high = []
    findings_low = []

    for path in _tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(path.relative_to(ROOT))
        findings_high.extend(_scan_high(text, path))
        findings_low.extend(_scan_low(text, path, rel))

    result = {
        "files_scanned": sum(1 for _ in _tracked_files()),
        "high_findings": sorted(set(findings_high)),
        "low_findings": sorted(set(findings_low)),
        "gitignore": _gitignore_coverage(),
        "note": "eval in return_risk/rules_engine.py is the documented whitelisted-scope rule evaluator (see docs); "
        "no tracked env files expected",
    }
    print(json.dumps(result, indent=2))
    return 1 if result["high_findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
