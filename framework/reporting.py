from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / "reports"


def _sanitize_mode(mode_key):
    return str(mode_key).replace(":", "_").replace(" ", "_")


def _format_incidents(incidents):
    if not incidents:
        return "- No incidents recorded in the current view."

    lines = []
    for incident in incidents:
        lines.append(
            f"- [{incident['severity'].upper()}] {incident['time']} | {incident['title']}: {incident['message']}"
        )
    return "\n".join(lines)


def _format_alerts(alerts):
    if not alerts:
        return "- No alerts in the current view."

    lines = []
    for alert in alerts:
        lines.append(f"- [{alert['severity'].upper()}] {alert['title']}: {alert['message']}")
    return "\n".join(lines)


def _format_list(items, empty_message):
    if not items:
        return f"- {empty_message}"
    return "\n".join(f"- {item}" for item in items)


def build_report_content(payload):
    summary = payload["summary"]
    intelligence = payload["intelligence"]
    suspect = intelligence["process"]["top_suspect"]
    monitoring_mode = payload["monitoring_mode"]["current"]
    incident_summary = payload["incident_summary"]

    return f"""# Proactive System Stability Monitoring Report

Generated at: {datetime.now().isoformat(timespec="seconds")}
Monitoring mode: {monitoring_mode['label']}
Mode description: {monitoring_mode['description']}

## Executive Summary

Title: {incident_summary['title']}

{incident_summary['narrative']}

## Current Snapshot

- CPU usage: {summary['cpu_percent']}%
- Memory usage: {summary['memory_percent']}%
- Running processes: {summary['total_processes']}
- Risk score: {summary['risk_score']} ({summary['risk_level']})
- Health classification: {summary['health_classification']}
- Anomaly score: {summary['anomaly_score']}

## Intelligent Analysis

- Baseline CPU: {intelligence['baseline']['cpu']}%
- Baseline Memory: {intelligence['baseline']['memory']}%
- Anomaly confidence: {intelligence['anomaly']['confidence']}
- Primary driver: {intelligence['health']['driver']}
- Predicted next CPU: {intelligence['prediction']['cpu_next']}%
- Predicted next Memory: {intelligence['prediction']['memory_next']}%

Observation:
{payload['analysis']['observation']}

Explanation:
{intelligence['explanation']}

Prediction:
{intelligence['prediction']['message']}

## Top Suspect Process

- Name: {suspect['display_name']}
- PID: {suspect['pid']}
- Suspicion score: {suspect['score']}
- Type: {suspect['label']}
- Reason: {suspect['reason']}
- Details: {suspect['details']}

## Alerts

{_format_alerts(payload['alerts'])}

## Recommendations

{_format_list(payload['recommendations'], 'No recommendations in the current view.')}

## Incident History

{_format_incidents(payload['incident_history'])}
"""


def export_report(payload):
    REPORTS_DIR.mkdir(exist_ok=True)
    mode_key = _sanitize_mode(payload["monitoring_mode"]["current"]["key"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = REPORTS_DIR / f"monitoring_report_{mode_key}_{timestamp}.md"
    file_path.write_text(build_report_content(payload), encoding="utf-8")
    return file_path
