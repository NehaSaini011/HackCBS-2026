import json
from pathlib import Path

from detection.checks.missing_index import check_missing_index
from detection.adapters.finding_adapter import normalize_findings


SKIP = {
    item.strip()
    for item in __import__("os").getenv("SKIP_TESTS", "").split(",")
    if item.strip()
}


def main():
    findings = []

    if "missing_index" not in SKIP:
        findings.extend(check_missing_index())

    normalized = normalize_findings(findings)

    output_dir = Path("detection/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "findings.json"
    output_file.write_text(
        json.dumps(normalized, indent=2),
        encoding="utf-8",
    )

    print(f"Detection complete. Findings: {len(normalized)}")
    print(json.dumps(normalized, indent=2))


if __name__ == "__main__":
    main()