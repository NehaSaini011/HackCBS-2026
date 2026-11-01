from datetime import datetime, timezone


def normalize_findings(findings):
    normalized = []

    for finding in findings:
        normalized.append({
            "shop": finding["shop"],
            "source": finding["source"],
            "test": finding["test"],
            "severity": finding["severity"],
            "summary": finding["summary"],
            "raw": finding["raw"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })

    return normalized