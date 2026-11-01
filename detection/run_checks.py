
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from detection.checks.missing_index import check_missing_index
from detection.adapters.finding_adapter import normalize_findings


SKIP = {
    item.strip()
    for item in os.getenv("SKIP_TESTS", "").split(",")
    if item.strip()
}


def post_findings(findings):
    """Send normalized findings to the configured API."""
    api_url = os.getenv("FINDINGS_API_URL")
    api_key = os.getenv("FINDINGS_API_KEY")

    if not api_url or not api_key:
        print("Findings API not configured. Saved findings locally only.")
        return

    payload = json.dumps({"findings": findings}).encode("utf-8")

    request = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            print(f"Findings sent successfully. API status: {response.status}")
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        print(f"WARNING: Could not send findings to API: {error}")


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

    post_findings(normalized)


if __name__ == "__main__":
    main()
