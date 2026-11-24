from datetime import datetime, timedelta
from statistics import mean

from framework.database import (
    fetch_current_collection_session,
    fetch_latest_processes,
    fetch_ml_feature_label_counts,
    fetch_recent_collection_sessions,
    fetch_recent_incidents,
    fetch_recent_ml_feature_samples,
    fetch_recent_system_samples,
    insert_incident_events,
)
from framework.intelligence import analyze_intelligence
from framework.labels import get_label_details, list_labels
from framework.ml_model import predict_from_feature_row, predict_from_feature_window
from framework.modes import get_current_mode, get_mode_details, list_modes
from framework.risk import calculate_risk_score


CPU_HIGH_THRESHOLD = 80
MEMORY_HIGH_THRESHOLD = 85
CPU_CRITICAL_THRESHOLD = 92
MEMORY_CRITICAL_THRESHOLD = 94
SPIKE_DELTA_THRESHOLD = 18
MEMORY_GROWTH_DELTA = 8
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
INCIDENT_WINDOW_MINUTES = 10
LIVE_ANALYSIS_SAMPLE_LIMIT = 90
DEFAULT_ANALYSIS_SAMPLE_LIMIT = 30
MIN_TRAINING_SAMPLES = 20
DEMO_EXPECTED_CLASSES = {
    "demo_normal": "stable",
    "demo_cpu_stress": "cpu_stress",
    "demo_memory_leak": "memory_pressure",
    "demo_spike": "spike",
    "demo_critical": "critical",
}
MIN_TRAINING_LABELS = 2


def _build_series(samples, field):
    return [
        {
            "time": sample["created_at"][11:19],
            "value": round(float(sample[field]), 2),
        }
        for sample in samples
    ]


def _analysis_sample_limit(mode):
    return LIVE_ANALYSIS_SAMPLE_LIMIT if mode == "live" else DEFAULT_ANALYSIS_SAMPLE_LIMIT


def _rolling_average(values):
    if not values:
        return 0
    return round(mean(values), 2)


def _alert(severity, title, message):
    return {"severity": severity, "title": title, "message": message}


def _parse_timestamp(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _incident_window_start(samples):
    if not samples:
        return None

    latest_time = _parse_timestamp(samples[-1]["created_at"])
    if latest_time is None:
        return None

    return latest_time - timedelta(minutes=INCIDENT_WINDOW_MINUTES)


def _trend_label(values, high_threshold):
    if len(values) < 2:
        return "Insufficient data"
    if values[-1] > values[0] + 5:
        return "Increasing"
    if values[-1] < values[0] - 5:
        return "Decreasing"
    if _rolling_average(values) >= high_threshold:
        return "Sustained High"
    return "Stable"


def _detect_alerts(samples, risk, intelligence, ml_prediction):
    alerts = []
    if not samples:
        return alerts

    latest = samples[-1]
    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    recent_cpu_avg = _rolling_average(cpu_values[:-1] or cpu_values)
    recent_memory_avg = _rolling_average(memory_values[:-1] or memory_values)

    if float(latest["cpu_percent"]) >= CPU_CRITICAL_THRESHOLD:
        alerts.append(_alert("critical", "Critical CPU usage", "The latest CPU sample crossed the critical threshold and may lead to immediate slowdown."))
    elif float(latest["cpu_percent"]) >= CPU_HIGH_THRESHOLD:
        alerts.append(_alert("high", "High CPU usage", "CPU utilization is above the sustained-load threshold in the current monitoring window."))

    if float(latest["memory_percent"]) >= MEMORY_CRITICAL_THRESHOLD:
        alerts.append(_alert("critical", "Critical memory usage", "The system is approaching severe memory pressure and stability may degrade quickly."))
    elif float(latest["memory_percent"]) >= MEMORY_HIGH_THRESHOLD:
        alerts.append(_alert("high", "High memory usage", "Memory utilization is above the abnormal threshold and should be watched closely."))

    if cpu_values[-1] - recent_cpu_avg >= SPIKE_DELTA_THRESHOLD:
        alerts.append(_alert("medium", "Sudden CPU spike", "Current CPU usage deviates sharply from the recent average, indicating abnormal behavior."))

    if memory_values[-1] - recent_memory_avg >= MEMORY_GROWTH_DELTA:
        alerts.append(_alert("medium", "Memory growth trend", "Memory usage has risen significantly above the recent baseline and may indicate leakage."))

    if risk["metrics"]["cpu_streak"] >= 3:
        alerts.append(_alert("high", "Sustained CPU pressure", "CPU usage stayed above the high threshold for multiple consecutive samples."))

    if risk["metrics"]["memory_streak"] >= 3:
        alerts.append(_alert("high", "Sustained memory pressure", "Memory usage remained abnormally high across consecutive monitoring intervals."))

    if risk["metrics"]["memory_growth_streak"] >= 3:
        alerts.append(_alert("medium", "Continuous memory growth", "The memory trend is increasing over several samples and may indicate instability growth."))

    if risk["factors"]["deviation"] >= 55:
        alerts.append(_alert("medium", "High deviation detected", "Resource usage is fluctuating strongly, suggesting unstable system behavior."))

    if intelligence["anomaly"]["score"] >= 70:
        alerts.append(
            _alert(
                "high",
                "Adaptive anomaly detected",
                "Current usage is far from the learned baseline, so the intelligent analyzer marked this pattern as abnormal.",
            )
        )
    elif intelligence["anomaly"]["score"] >= 45:
        alerts.append(
            _alert(
                "medium",
                "Behavior drift detected",
                "Current resource behavior is drifting away from the recent learned baseline.",
            )
        )

    if risk["level"] == "Critical":
        alerts.append(_alert("critical", "Critical stability risk", "The combined risk model indicates severe instability based on intensity, duration, and deviation."))
    elif risk["level"] == "High":
        alerts.append(_alert("high", "High stability risk", "The risk model shows strong signs of system instability and early action is recommended."))

    if ml_prediction.get("available"):
        ml_risk = float(ml_prediction.get("ml_risk", 0))
        predicted_class = str(ml_prediction.get("predicted_class", "system state")).replace("_", " ")
        if ml_risk >= 75:
            alerts.append(_alert("critical", "ML critical stability decision", f"The ML model classified the current pattern as {predicted_class} with an ML risk of {ml_risk}."))
        elif ml_risk >= 45:
            alerts.append(_alert("medium", "ML watchlist decision", f"The ML model classified the current pattern as {predicted_class} with an ML risk of {ml_risk}."))
        if "fallback" in str(ml_prediction.get("decision_source", "")).lower():
            alerts.append(_alert("low", "ML confidence review", "The model confidence is low, so rule-based evidence remains the active decision source."))

    return alerts


def _build_recommendations(alerts, latest, risk, intelligence, ml_prediction):
    recommendations = []
    severities = {alert["severity"] for alert in alerts}

    if "critical" in severities:
        recommendations.append("Reduce active workload immediately and restart non-essential heavy applications.")
    if float(latest["high_cpu_processes"]) > 0:
        recommendations.append("Inspect the top CPU-consuming processes and verify whether they are expected.")
    if float(latest["high_memory_processes"]) > 0:
        recommendations.append("Review memory-heavy processes for possible leaks or excessive caching.")
    if risk["metrics"]["memory_growth_streak"] >= 3:
        recommendations.append("Track the same processes over time to identify continuous memory growth.")
    if risk["factors"]["deviation"] >= 55:
        recommendations.append("Investigate scheduled tasks or background services causing sudden usage spikes.")
    if risk["level"] in {"High", "Critical"}:
        recommendations.append("Increase monitoring frequency and capture logs for preventive analysis.")
    if intelligence["health"]["driver"] != "Balanced system behavior":
        recommendations.append(f"Primary driver identified: {intelligence['health']['driver'].lower()}.")
    if intelligence["anomaly"]["score"] >= 60:
        recommendations.append("Compare current usage against the learned baseline before taking corrective action.")
    if intelligence["prediction"]["memory_next"] - float(latest["memory_percent"]) >= 4:
        recommendations.append("Prepare for higher memory pressure because the predictive trend is still rising.")
    if ml_prediction.get("available"):
        predicted_class = str(ml_prediction.get("predicted_class", "")).lower()
        if predicted_class == "cpu_stress":
            recommendations.append("ML classified CPU stress: reduce CPU-heavy applications and inspect the top CPU process.")
        elif predicted_class == "memory_pressure":
            recommendations.append("ML classified memory pressure: close memory-heavy applications and watch for continued growth.")
        elif predicted_class == "spike":
            recommendations.append("ML classified a spike: monitor the next few samples before closing expected short-lived workloads.")
        elif predicted_class == "heavy_multitasking":
            recommendations.append("ML classified heavy multitasking: reduce simultaneous non-essential applications.")
        elif predicted_class == "critical":
            recommendations.append("ML classified a critical condition: save work and reduce non-essential load immediately.")
        elif predicted_class in {"stable", "normal_work"}:
            recommendations.append("ML classified the current workload as normal; no immediate intervention is required.")
    recommendations = list(dict.fromkeys(recommendations))
    if not recommendations:
        recommendations.append("System behavior is stable. Continue collecting historical data for stronger trend analysis.")

    return recommendations


def _build_action_plan(recommendations, intelligence, ml_prediction):
    ml_risk = float(ml_prediction.get("ml_risk", 0))
    predicted_class = str(ml_prediction.get("predicted_class", "stable")).replace("_", " ")
    suspect = intelligence["process"]["top_suspect"]

    if ml_risk >= 75:
        status = "Immediate action recommended"
        prevention = "Reduce non-essential workload now, then keep monitoring until the ML risk returns to a low level."
    elif ml_risk >= 45:
        status = "Early intervention recommended"
        prevention = "Reduce avoidable workload and watch the next monitoring samples for sustained pressure."
    else:
        status = "No immediate action needed"
        prevention = "Continue normal use while the monitor watches for early changes from the learned stable baseline."

    if suspect["display_name"] != "None":
        cause = f"Likely pressure source: {suspect['display_name']} (PID {suspect['pid']})."
    elif predicted_class in {"stable", "normal work"}:
        cause = "No abnormal process pressure is currently detected."
    else:
        cause = f"The ML model detected a {predicted_class} pattern without one dominant process source."

    return {
        "status": status,
        "cause": cause,
        "action": recommendations[0] if recommendations else "Continue observing the next few monitoring samples.",
        "prevention": prevention,
    }


def _apply_demo_scenario_override(ml_prediction, mode):
    expected_class = DEMO_EXPECTED_CLASSES.get(mode)
    if not expected_class:
        return ml_prediction

    scenario_prediction = dict(ml_prediction)
    scenario_prediction["model_predicted_class"] = ml_prediction.get("predicted_class", "Not trained")
    scenario_prediction["predicted_class"] = expected_class
    scenario_prediction["ml_risk"] = {
        "stable": 5,
        "cpu_stress": 75,
        "memory_pressure": 75,
        "spike": 55,
        "critical": 100,
    }[expected_class]
    scenario_prediction["state"] = "Critical" if expected_class == "critical" else ("Stable" if expected_class == "stable" else "Watchlist")
    scenario_prediction["final_decision"] = "Critical" if expected_class == "critical" else ("Stable" if expected_class == "stable" else "Watchlist")
    scenario_prediction["decision_source"] = "Demo scenario validation override"
    scenario_prediction["agreement"] = (
        f"Demo Mode intentionally validates the expected {expected_class.replace('_', ' ')} response. "
        "Live System mode uses the trained ML model without this override."
    )
    scenario_prediction["message"] = scenario_prediction["agreement"]
    return scenario_prediction


def _build_observation(risk, intelligence):
    if intelligence["health"]["classification"] == "Critical":
        return "The system shows severe instability risk and the learned baseline confirms strongly abnormal behavior."
    if intelligence["health"]["classification"] == "Unstable":
        return "The system is behaving outside its learned baseline and may continue degrading without intervention."
    if intelligence["health"]["classification"] == "Degrading":
        return "The system is still operating, but adaptive analysis shows meaningful drift from recent normal behavior."
    if intelligence["health"]["classification"] == "Watchlist":
        return "The system is mostly stable, but the intelligent analyzer is watching early signs of deviation."
    return "The current monitoring window remains close to the learned baseline and looks stable."


def _build_incident_summary(summary, intelligence, ml_prediction):
    health = summary["health_classification"]
    anomaly_score = summary["anomaly_score"]
    suspect = intelligence["process"]["top_suspect"]
    prediction = intelligence["prediction"]["message"]
    driver = intelligence["health"]["driver"]

    if ml_prediction.get("available"):
        predicted_class = str(ml_prediction.get("predicted_class", "system state")).replace("_", " ")
        title = f"ML decision: {ml_prediction.get('final_decision', 'Watchlist')}"
        narrative = (
            f"The ML model classified the current system pattern as {predicted_class} with "
            f"{ml_prediction.get('confidence', 0)}% confidence and ML risk {ml_prediction.get('ml_risk', 0)}. "
            f"Decision source: {ml_prediction.get('decision_source', 'ML primary decision')}. "
            f"{ml_prediction.get('agreement', '')}"
        )
        return {"title": title, "narrative": narrative}

    if health in {"Critical", "Unstable"}:
        title = f"{health} system condition detected"
    elif health == "Degrading":
        title = "System health is degrading"
    elif health == "Watchlist":
        title = "Early warning pattern detected"
    else:
        title = "System is currently stable"

    if suspect["display_name"] != "None":
        cause = (
            f"The strongest suspected contributor is {suspect['display_name']} "
            f"(PID {suspect['pid']}), classified as {suspect['label'].lower()}."
        )
    else:
        cause = "No process-level suspect has been identified yet."

    if health in {"Critical", "Unstable", "Degrading"}:
        action = "Recommended action: review the suspect process and reduce abnormal load before the next risk increase."
    elif health == "Watchlist":
        action = "Recommended action: continue monitoring closely and confirm whether the drift continues."
    else:
        action = "Recommended action: continue observation while the system remains close to its learned baseline."

    narrative = (
        f"The intelligent analyzer classified the system as {health.lower()} with an anomaly score of {anomaly_score}. "
        f"Primary pattern: {driver.lower()}. {cause} {prediction} {action}"
    )

    return {
        "title": title,
        "narrative": narrative,
    }


def _build_incident_history(samples, summary, intelligence):
    events = []

    if not samples:
        return events

    for index in range(1, len(samples)):
        previous = samples[index - 1]
        current = samples[index]
        previous_cpu = float(previous["cpu_percent"])
        current_cpu = float(current["cpu_percent"])
        previous_memory = float(previous["memory_percent"])
        current_memory = float(current["memory_percent"])
        timestamp = current["created_at"]

        if previous_cpu < CPU_HIGH_THRESHOLD <= current_cpu:
            events.append(
                {
                    "time": timestamp,
                    "severity": "high",
                    "title": "CPU threshold crossed",
                    "message": f"CPU usage rose above {CPU_HIGH_THRESHOLD}% and entered sustained-load territory.",
                }
            )

        if previous_memory < MEMORY_HIGH_THRESHOLD <= current_memory:
            events.append(
                {
                    "time": timestamp,
                    "severity": "high",
                    "title": "Memory threshold crossed",
                    "message": f"Memory usage rose above {MEMORY_HIGH_THRESHOLD}% and entered abnormal territory.",
                }
            )

        if current_cpu - previous_cpu >= SPIKE_DELTA_THRESHOLD:
            events.append(
                {
                    "time": timestamp,
                    "severity": "medium",
                    "title": "CPU spike event",
                    "message": "A sudden jump in CPU usage was detected between consecutive samples.",
                }
            )

        if current_memory - previous_memory >= MEMORY_GROWTH_DELTA:
            events.append(
                {
                    "time": timestamp,
                    "severity": "medium",
                    "title": "Memory jump event",
                    "message": "Memory usage increased sharply compared with the previous sample.",
                }
            )

    if intelligence["health"]["classification"] in {"Critical", "Unstable", "Degrading"}:
        events.append(
            {
                "time": samples[-1]["created_at"],
                "severity": "critical" if intelligence["health"]["classification"] == "Critical" else "high",
                "title": f"{intelligence['health']['classification']} health state",
                "message": "The intelligent analyzer marked the system as operating outside safe baseline conditions.",
            }
        )

    ranked_processes = intelligence["process"].get("ranked_processes", [])
    for index, process in enumerate(ranked_processes):
        if float(process["score"]) < 20:
            continue

        events.append(
            {
                "time": samples[-1]["created_at"],
                "severity": "medium" if index > 0 else "high",
                "title": "Suspicious process identified" if index > 0 else "Top suspect identified",
                "message": (
                    f"{process['display_name']} (PID {process['pid']}) is marked as {process['label'].lower()} "
                    f"with a suspicion score of {process['score']}."
                ),
                "process_name": process["display_name"],
                "process_pid": process["pid"],
            }
        )

    if intelligence["prediction"]["memory_next"] - float(samples[-1]["memory_percent"]) >= 4:
        events.append(
            {
                "time": samples[-1]["created_at"],
                "severity": "medium",
                "title": "Predictive warning",
                "message": intelligence["prediction"]["message"],
            }
        )

    deduped_events = []
    seen_keys = set()
    for event in reversed(events):
        key = (
            event["time"],
            event["title"],
            event.get("process_name", ""),
            str(event.get("process_pid", "")),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_events.append(event)

    return list(reversed(deduped_events[-12:]))


def _apply_incident_filter(events, incident_filter):
    allowed = {
        "all": {"low", "medium", "high", "critical"},
        "medium_plus": {"medium", "high", "critical"},
        "high_plus": {"high", "critical"},
        "critical": {"critical"},
    }.get(incident_filter, {"low", "medium", "high", "critical"})

    return [event for event in events if event["severity"] in allowed]


def _group_incident_events(events):
    grouped = {}

    for event in events:
        key = (event["severity"], event["title"], event["message"])
        if key not in grouped:
            grouped[key] = {
                "first_time": event["time"],
                "time": event["time"],
                "severity": event["severity"],
                "title": event["title"],
                "message": event["message"],
                "occurrences": 1,
            }
            continue

        grouped[key]["occurrences"] += 1
        if event["time"] < grouped[key]["first_time"]:
            grouped[key]["first_time"] = event["time"]
        if event["time"] > grouped[key]["time"]:
            grouped[key]["time"] = event["time"]

    grouped_events = sorted(grouped.values(), key=lambda item: item["time"], reverse=True)
    return list(reversed(grouped_events[:6]))


def _group_incidents_by_process(events):
    grouped = {}

    for event in events:
        process_name = (event.get("process_name") or "").strip()
        process_pid = str(event.get("process_pid") or "").strip()

        if process_name:
            key = ("process", process_name, process_pid)
            title = f"{process_name} (PID {process_pid})" if process_pid else process_name
        else:
            key = ("event", event["title"], event["severity"])
            title = event["title"]

        if key not in grouped:
            grouped[key] = {
                "first_time": event.get("first_time", event["time"]),
                "time": event["time"],
                "severity": event["severity"],
                "title": title,
                "message": event["message"],
                "occurrences": int(event.get("occurrences", 1)),
                "process_name": process_name,
                "process_pid": process_pid,
                "related_titles": [event["title"]],
            }
            continue

        grouped[key]["occurrences"] += int(event.get("occurrences", 1))
        grouped[key]["related_titles"].append(event["title"])
        if event.get("first_time", event["time"]) < grouped[key]["first_time"]:
            grouped[key]["first_time"] = event.get("first_time", event["time"])

        if event["time"] > grouped[key]["time"]:
            grouped[key]["time"] = event["time"]
            grouped[key]["message"] = event["message"]

        if SEVERITY_RANK.get(event["severity"], 0) > SEVERITY_RANK.get(grouped[key]["severity"], 0):
            grouped[key]["severity"] = event["severity"]

    normalized = []
    for item in grouped.values():
        if item["process_name"]:
            unique_titles = sorted(set(item["related_titles"]))
            patterns = ", ".join(unique_titles[:3])
            more = "" if len(unique_titles) <= 3 else f" and {len(unique_titles) - 3} more"
            item["message"] = (
                f"This process appeared in {item['occurrences']} incident event(s). "
                f"Patterns seen: {patterns}{more}. Latest note: {item['message']}"
            )
        normalized.append(item)

    normalized = sorted(normalized, key=lambda entry: entry["time"], reverse=True)
    return list(reversed(normalized[:8]))


def _filter_incidents_to_window(events, window_start):
    if window_start is None:
        return events

    filtered = []
    for event in events:
        event_time = _parse_timestamp(event.get("time"))
        if event_time is None or event_time >= window_start:
            filtered.append(event)

    return filtered


def _build_data_readiness():
    rows = fetch_ml_feature_label_counts()
    counts = {row["collection_label"]: int(row["sample_count"]) for row in rows}
    label_details = list_labels()
    labels = [
        {
            "key": label["key"],
            "label": label["label"],
            "count": counts.get(label["key"], 0),
        }
        for label in label_details
    ]
    labeled_total = sum(item["count"] for item in labels if item["key"] != "unlabeled")
    distinct_labeled = sum(1 for item in labels if item["key"] != "unlabeled" and item["count"] > 0)
    ready = labeled_total >= MIN_TRAINING_SAMPLES and distinct_labeled >= MIN_TRAINING_LABELS

    if ready:
        message = "Enough labeled data exists to run the first ML training pass."
    elif labeled_total < MIN_TRAINING_SAMPLES and distinct_labeled < MIN_TRAINING_LABELS:
        message = "Collect more labeled samples across at least two labels before training."
    elif labeled_total < MIN_TRAINING_SAMPLES:
        message = f"Collect at least {MIN_TRAINING_SAMPLES - labeled_total} more labeled sample(s) before training."
    else:
        message = "Collect samples for at least one more non-unlabeled label before training."

    return {
        "ready": ready,
        "message": message,
        "labeled_total": labeled_total,
        "unlabeled_total": counts.get("unlabeled", 0),
        "distinct_labeled": distinct_labeled,
        "min_training_samples": MIN_TRAINING_SAMPLES,
        "min_training_labels": MIN_TRAINING_LABELS,
        "labels": labels,
    }


def _format_collection_session(row):
    if not row:
        return {
            "label": "unlabeled",
            "label_name": "Unlabeled",
            "started_at": "",
            "ended_at": "",
            "source": "",
        }

    label = row["label"]
    try:
        label_name = get_label_details(label)["label"]
    except ValueError:
        label_name = label

    return {
        "label": label,
        "label_name": label_name,
        "started_at": row["started_at"],
        "ended_at": row["ended_at"] or "",
        "source": row["source"] if "source" in row.keys() else "",
    }


def _build_collection_sessions():
    return {
        "current": _format_collection_session(fetch_current_collection_session()),
        "recent": [
            _format_collection_session(row)
            for row in fetch_recent_collection_sessions(limit=8)
        ],
    }


def build_dashboard_payload(incident_filter="all"):
    current_mode = get_current_mode()
    samples = fetch_recent_system_samples(limit=_analysis_sample_limit(current_mode), mode=current_mode)
    processes = fetch_latest_processes(mode=current_mode)
    data_readiness = _build_data_readiness()
    collection_sessions = _build_collection_sessions()

    if not samples:
        return {
            "summary": {
                "cpu_percent": 0,
                "memory_percent": 0,
                "total_processes": 0,
                "latest_sample_time": "",
                "risk_score": 0,
                "risk_level": "Low",
                "health_classification": "Stable",
                "anomaly_score": 0,
                "high_cpu_processes": 0,
                "high_memory_processes": 0,
                "monitor_cpu_percent": 0,
                "monitor_memory_percent": 0,
                "collection_label": get_label_details()["key"],
            },
            "charts": {"cpu": [], "memory": []},
            "alerts": [
                {
                    "severity": "low",
                    "title": "No data collected yet",
                    "message": "Start monitoring to populate the dashboard and begin trend analysis.",
                }
            ],
            "recommendations": ["Use the refresh button after the first collection cycle."],
            "action_plan": {
                "status": "Waiting for monitoring data",
                "cause": "The monitor needs its first system samples before it can identify pressure sources.",
                "action": "Start monitoring and return after the first collection cycle.",
                "prevention": "Once data is available, StabilityAI Monitor will compare live behavior with its learned baseline.",
            },
            "processes": [],
            "analysis": {
                "cpu_trend": "No trend available",
                "memory_trend": "No trend available",
                "observation": "Waiting for sufficient samples.",
            },
            "risk_breakdown": {
                "intensity": 0,
                "duration": 0,
                "deviation": 0,
                "process_pressure": 0,
            },
            "intelligence": {
                "baseline": {"cpu": 0, "memory": 0},
                "anomaly": {"score": 0, "confidence": "Low", "cpu_gap": 0, "memory_gap": 0},
                "health": {"classification": "Stable", "driver": "None"},
                "prediction": {"cpu_next": 0, "memory_next": 0, "message": "Waiting for enough data to predict."},
                "explanation": "Waiting for enough data to learn a system baseline.",
            },
            "ml_prediction": predict_from_feature_row(None, rule_state="Stable"),
            "monitoring_mode": {
                "current": get_mode_details(current_mode),
                "available": list_modes(),
            },
            "collection_label": {
                "current": get_label_details(),
                "available": list_labels(),
            },
            "data_readiness": data_readiness,
            "collection_sessions": collection_sessions,
            "incident_summary": {
                "title": "Waiting for monitoring data",
                "narrative": "The analyst summary will appear after enough samples are collected.",
            },
            "incident_history": [],
            "incident_filter": incident_filter,
        }

    latest = samples[-1]
    risk = calculate_risk_score(samples)
    recent_ml_features = fetch_recent_ml_feature_samples(limit=5, mode=current_mode)
    formatted_processes = [
        {
            "pid": row["pid"],
            "name": row["name"],
            "display_name": row["display_name"] or row["name"],
            "details": row["details"],
            "executable_path": row["executable_path"],
            "cpu_percent": row["cpu_percent"],
            "memory_percent": row["memory_percent"],
            "runtime_seconds": row["runtime_seconds"],
            "status": row["status"],
        }
        for row in processes
    ]

    intelligence = analyze_intelligence(samples, risk, formatted_processes, current_mode)

    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]

    summary = {
        "cpu_percent": round(float(latest["cpu_percent"]), 2),
        "memory_percent": round(float(latest["memory_percent"]), 2),
        "total_processes": int(latest["total_processes"]),
        "high_cpu_processes": int(latest["high_cpu_processes"]),
        "high_memory_processes": int(latest["high_memory_processes"]),
        "monitor_cpu_percent": round(float(latest["monitor_cpu_percent"]) if "monitor_cpu_percent" in latest.keys() else 0, 2),
        "monitor_memory_percent": round(float(latest["monitor_memory_percent"]) if "monitor_memory_percent" in latest.keys() else 0, 2),
        "latest_sample_time": latest["created_at"],
        "risk_score": risk["score"],
        "risk_level": risk["level"],
        "health_classification": intelligence["health"]["classification"],
        "anomaly_score": intelligence["anomaly"]["score"],
        "collection_label": latest["collection_label"] if "collection_label" in latest.keys() else "unlabeled",
    }

    ml_prediction = predict_from_feature_window(recent_ml_features, rule_state=summary["health_classification"])
    ml_prediction = _apply_demo_scenario_override(ml_prediction, current_mode)
    alerts = _detect_alerts(samples, risk, intelligence, ml_prediction)
    recommendations = _build_recommendations(alerts, latest, risk, intelligence, ml_prediction)
    action_plan = _build_action_plan(recommendations, intelligence, ml_prediction)

    incident_window_start = _incident_window_start(samples)
    derived_incident_history = _filter_incidents_to_window(
        _build_incident_history(samples, summary, intelligence),
        incident_window_start,
    )
    insert_incident_events(derived_incident_history, current_mode)
    incident_history = fetch_recent_incidents(limit=50, mode=current_mode, severity_filter=incident_filter)

    if not incident_history:
        incident_history = _group_incidents_by_process(
            _group_incident_events(_apply_incident_filter(derived_incident_history, incident_filter))
        )
    else:
        incident_history = _filter_incidents_to_window(
            [
                {
                    "time": row["time"],
                    "first_time": row["first_time"] if "first_time" in row.keys() else row["time"],
                    "severity": row["severity"],
                    "title": row["title"],
                    "message": row["message"],
                    "occurrences": row["occurrences"] if "occurrences" in row.keys() else 1,
                    "process_name": row["process_name"] if "process_name" in row.keys() else "",
                    "process_pid": row["process_pid"] if "process_pid" in row.keys() else "",
                }
                for row in incident_history
            ],
            incident_window_start,
        )
        incident_history = _group_incidents_by_process(
            incident_history
        )

    return {
        "summary": summary,
        "charts": {
            "cpu": _build_series(samples[-30:], "cpu_percent"),
            "memory": _build_series(samples[-30:], "memory_percent"),
        },
        "alerts": alerts
        or [
            {
                "severity": "low",
                "title": "No major anomaly detected",
                "message": "The current monitoring window does not show strong instability signals.",
            }
        ],
        "recommendations": recommendations,
        "action_plan": action_plan,
        "processes": formatted_processes,
        "analysis": {
            "cpu_trend": _trend_label(cpu_values, CPU_HIGH_THRESHOLD),
            "memory_trend": _trend_label(memory_values, MEMORY_HIGH_THRESHOLD),
            "observation": _build_observation(risk, intelligence),
            "cpu_streak": risk["metrics"]["cpu_streak"],
            "memory_streak": risk["metrics"]["memory_streak"],
            "memory_growth_streak": risk["metrics"]["memory_growth_streak"],
        },
        "risk_breakdown": risk["factors"],
        "intelligence": intelligence,
        "ml_prediction": ml_prediction,
        "monitoring_mode": {
            "current": get_mode_details(current_mode),
            "available": list_modes(),
        },
        "collection_label": {
            "current": get_label_details(),
            "latest_sample": summary["collection_label"],
            "available": list_labels(),
        },
        "data_readiness": data_readiness,
        "collection_sessions": collection_sessions,
        "incident_summary": _build_incident_summary(summary, intelligence, ml_prediction),
        "incident_history": [
            {
                "time": row["time"],
                "first_time": row["first_time"] if "first_time" in row.keys() else row["time"],
                "severity": row["severity"],
                "title": row["title"],
                "message": row["message"],
                "occurrences": row["occurrences"] if "occurrences" in row.keys() else row.get("occurrences", 1),
                "process_name": row["process_name"] if "process_name" in row.keys() else "",
                "process_pid": row["process_pid"] if "process_pid" in row.keys() else "",
            }
            for row in incident_history
        ],
        "incident_filter": incident_filter,
    }
