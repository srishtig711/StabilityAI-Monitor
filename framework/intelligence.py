from statistics import mean, pstdev


IGNORED_PROCESS_NAMES = {
    "idle",
    "system idle process",
    "system_idle",
}
LIVE_MIN_BASELINE_SAMPLES = 18
LIVE_FULL_CONFIDENCE_SAMPLES = 30
ANOMALY_STABILIZATION_WINDOW = 6


def _safe_mean(values):
    return round(mean(values), 2) if values else 0


def _safe_stdev(values):
    if len(values) < 2:
        return 0
    return round(pstdev(values), 2)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _percentage_gap(current, baseline):
    if baseline <= 0:
        return 0
    return round(((current - baseline) / baseline) * 100, 2)


def _project_next_value(values):
    if len(values) < 3:
        return round(values[-1], 2) if values else 0

    recent_values = values[-5:]
    weights = list(range(1, len(recent_values) + 1))
    weighted_average = sum(value * weight for value, weight in zip(recent_values, weights)) / sum(weights)
    recent_deltas = [recent_values[index] - recent_values[index - 1] for index in range(1, len(recent_values))]
    smoothed_trend = mean(recent_deltas[-3:]) if recent_deltas else 0
    projected = weighted_average + smoothed_trend * 0.55
    return round(_clamp(projected, 0, 100), 2)


def _window_mean(values, size):
    if not values:
        return 0
    return _safe_mean(values[-size:])


def _compute_raw_anomaly(samples, mode="live"):
    if not samples:
        return {
            "score": 0,
            "confidence": "Low",
            "cpu_gap": 0,
            "memory_gap": 0,
            "baseline_cpu": 0,
            "baseline_memory": 0,
            "cpu_stddev": 0,
            "memory_stddev": 0,
            "current_cpu": 0,
            "current_memory": 0,
        }

    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    high_cpu_counts = [int(sample["high_cpu_processes"]) for sample in samples]
    high_memory_counts = [int(sample["high_memory_processes"]) for sample in samples]

    if mode == "live" and len(samples) >= 18:
        current_window = samples[-4:]
        baseline_window = samples[-36:-4] or samples[:-4] or samples
    elif len(samples) >= 8:
        current_window = samples[-3:]
        baseline_window = samples[-15:-3] or samples[:-3] or samples
    elif len(samples) >= 4:
        current_window = samples[-2:]
        baseline_window = samples[:-2] or samples
    else:
        current_window = samples[-1:]
        baseline_window = samples

    current_cpu = _safe_mean([float(sample["cpu_percent"]) for sample in current_window])
    current_memory = _safe_mean([float(sample["memory_percent"]) for sample in current_window])
    baseline_cpu_values = [float(sample["cpu_percent"]) for sample in baseline_window] or cpu_values
    baseline_memory_values = [float(sample["memory_percent"]) for sample in baseline_window] or memory_values

    baseline_cpu = _safe_mean(baseline_cpu_values)
    baseline_memory = _safe_mean(baseline_memory_values)
    cpu_stddev = _safe_stdev(baseline_cpu_values)
    memory_stddev = _safe_stdev(baseline_memory_values)

    cpu_difference = abs(current_cpu - baseline_cpu)
    memory_difference = abs(current_memory - baseline_memory)
    cpu_gap = _percentage_gap(baseline_cpu + cpu_difference, baseline_cpu)
    memory_gap = _percentage_gap(baseline_memory + memory_difference, baseline_memory)

    sigma_floor = 8 if mode == "live" else 5
    cpu_sigma_score = 0 if cpu_stddev == 0 else cpu_difference / max(cpu_stddev, sigma_floor)
    memory_sigma_score = 0 if memory_stddev == 0 else memory_difference / max(memory_stddev, sigma_floor)
    process_pressure_score = _clamp(_window_mean(high_cpu_counts, 4) * 7 + _window_mean(high_memory_counts, 4) * 6, 0, 100)

    if mode == "live":
        cpu_component = cpu_sigma_score * 5 + max(0, cpu_gap - 6) * 0.10
        memory_component = memory_sigma_score * 4 + max(0, memory_gap - 5) * 0.08
        pressure_component = process_pressure_score * 0.05
        anomaly_score = round(_clamp(cpu_component + memory_component + pressure_component, 0, 100), 2)

        if len(samples) < LIVE_MIN_BASELINE_SAMPLES:
            anomaly_score = round(min(anomaly_score, 22), 2)
        else:
            live_cap = 85
            if current_cpu >= 92 or current_memory >= 94:
                live_cap = 94
            if current_cpu >= 92 and current_memory >= 94 and process_pressure_score >= 35:
                live_cap = 98

            baseline_confidence = _clamp(
                (len(samples) - LIVE_MIN_BASELINE_SAMPLES)
                / (LIVE_FULL_CONFIDENCE_SAMPLES - LIVE_MIN_BASELINE_SAMPLES),
                0,
                1,
            )
            early_cap = 45 + baseline_confidence * (live_cap - 45)
            anomaly_score = round(min(anomaly_score, early_cap, live_cap), 2)
    else:
        anomaly_score = round(
            _clamp(
                cpu_sigma_score * 11
                + memory_sigma_score * 11
                + max(0, cpu_gap) * 0.28
                + max(0, memory_gap) * 0.28
                + process_pressure_score * 0.16,
                0,
                100,
            ),
            2,
        )

    if anomaly_score >= 70:
        confidence = "High"
    elif anomaly_score >= 40:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "score": anomaly_score,
        "confidence": confidence,
        "cpu_gap": cpu_gap,
        "memory_gap": memory_gap,
        "baseline_cpu": baseline_cpu,
        "baseline_memory": baseline_memory,
        "cpu_stddev": cpu_stddev,
        "memory_stddev": memory_stddev,
        "current_cpu": current_cpu,
        "current_memory": current_memory,
    }


def _stabilize_anomaly_score(samples, mode, current_score):
    if mode != "live" or len(samples) < 2:
        return current_score

    recent_prefixes = [
        samples[:index]
        for index in range(
            max(1, len(samples) - ANOMALY_STABILIZATION_WINDOW + 1),
            len(samples) + 1,
        )
    ]
    raw_scores = [_compute_raw_anomaly(prefix, mode)["score"] for prefix in recent_prefixes]
    weights = list(range(1, len(raw_scores) + 1))
    weighted_score = sum(score * weight for score, weight in zip(raw_scores, weights)) / sum(weights)

    return round(max(current_score, weighted_score), 2)


def _health_classification(risk_score, anomaly_score):
    combined = risk_score * 0.70 + anomaly_score * 0.30

    if combined >= 80:
        return "Critical"
    if combined >= 60:
        return "Unstable"
    if combined >= 40:
        return "Degrading"
    if combined >= 20:
        return "Watchlist"
    return "Stable"


def _classify_process_concern(process):
    cpu = float(process.get("cpu_percent") or 0)
    memory = float(process.get("memory_percent") or 0)
    runtime = float(process.get("runtime_seconds") or 0)

    if memory >= cpu and memory >= 12:
        return "Memory-heavy", "This process is consuming unusually high memory relative to the current system state."
    if cpu > memory and cpu >= 18:
        return "CPU-heavy", "This process is contributing strongly to the current CPU load pattern."
    if runtime >= 3600 and (cpu >= 8 or memory >= 6):
        return "Long-running load", "This long-running process is still consuming noticeable resources."
    return "Watch process", "This process is currently the strongest contributor among the visible active processes."


def analyze_process_intelligence(processes, driver):
    filtered_processes = [
        process
        for process in processes
        if (process.get("display_name") or process.get("name") or "").strip().lower() not in IGNORED_PROCESS_NAMES
    ]

    if not filtered_processes:
        return {
            "top_suspect": {
                "display_name": "None",
                "pid": "-",
                "score": 0,
                "label": "No process data",
                "reason": "No process-level data is available yet.",
                "details": "",
            },
            "summary": "Waiting for process samples to identify likely contributors.",
        }

    scored_processes = []
    for process in filtered_processes:
        cpu = float(process.get("cpu_percent") or 0)
        memory = float(process.get("memory_percent") or 0)
        runtime = float(process.get("runtime_seconds") or 0)

        score = cpu * 0.70 + memory * 0.20 + min(runtime / 600, 12) * 0.10
        if driver == "CPU-driven instability":
            score += cpu * 0.25
        elif driver == "Memory-driven instability":
            score += memory * 0.25
        elif driver == "Fluctuation-driven instability":
            score += max(cpu, memory) * 0.15

        normalized_score = round(_clamp(score, 0, 100), 2)
        label, reason = _classify_process_concern(process)
        scored_processes.append(
            {
                "score": normalized_score,
                "process": process,
                "label": label,
                "reason": reason,
            }
        )

    scored_processes.sort(key=lambda item: item["score"], reverse=True)
    top_entry = scored_processes[0]
    top_score = top_entry["score"]
    suspect = top_entry["process"]
    label = top_entry["label"]
    reason = top_entry["reason"]
    display_name = suspect.get("display_name") or suspect.get("name") or "Unknown"

    if driver != "Balanced system behavior":
        summary = f"{display_name} (PID {suspect['pid']}) is the strongest contributor to the detected {driver.lower()} pattern."
    else:
        summary = f"{display_name} (PID {suspect['pid']}) is currently the heaviest visible process in the monitoring window."

    ranked_processes = [
        {
            "display_name": entry["process"].get("display_name") or entry["process"].get("name") or "Unknown",
            "pid": entry["process"]["pid"],
            "score": entry["score"],
            "label": entry["label"],
            "reason": entry["reason"],
            "details": entry["process"].get("details") or entry["process"].get("name") or "",
        }
        for entry in scored_processes[:4]
    ]

    return {
        "top_suspect": {
            "display_name": display_name,
            "pid": suspect["pid"],
            "score": top_score,
            "label": label,
            "reason": reason,
            "details": suspect.get("details") or suspect.get("name") or "",
        },
        "ranked_processes": ranked_processes,
        "summary": summary,
    }


def analyze_intelligence(samples, risk, processes=None, mode="live"):
    if not samples:
        return {
            "baseline": {
                "cpu": 0,
                "memory": 0,
                "cpu_stddev": 0,
                "memory_stddev": 0,
            },
            "anomaly": {
                "score": 0,
                "confidence": "Low",
                "cpu_gap": 0,
                "memory_gap": 0,
            },
            "health": {
                "classification": "Stable",
                "driver": "None",
            },
            "prediction": {
                "cpu_next": 0,
                "memory_next": 0,
                "message": "Not enough data for prediction.",
            },
            "process": {
                "top_suspect": {
                    "display_name": "None",
                    "pid": "-",
                    "score": 0,
                    "label": "No process data",
                    "reason": "No process-level data is available yet.",
                    "details": "",
                },
                "ranked_processes": [],
                "summary": "Waiting for process samples to identify likely contributors.",
            },
            "explanation": "Waiting for enough data to learn a system baseline.",
        }

    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]

    anomaly_now = _compute_raw_anomaly(samples, mode)
    anomaly_prev = _compute_raw_anomaly(samples[:-1], mode) if len(samples) > 1 else anomaly_now
    anomaly_prev2 = _compute_raw_anomaly(samples[:-2], mode) if len(samples) > 2 else anomaly_prev
    anomaly_prev3 = _compute_raw_anomaly(samples[:-3], mode) if len(samples) > 3 else anomaly_prev2

    anomaly_score = round(
        _clamp(
            anomaly_now["score"] * 0.60
            + anomaly_prev["score"] * 0.20
            + anomaly_prev2["score"] * 0.12
            + anomaly_prev3["score"] * 0.08,
            0,
            100,
        ),
        2,
    )
    anomaly_score = _stabilize_anomaly_score(samples, mode, anomaly_score)
    confidence = anomaly_now["confidence"] if mode != "live" else ("High" if anomaly_score >= 65 else "Medium" if anomaly_score >= 35 else "Low")

    latest_cpu = cpu_values[-1]
    latest_memory = memory_values[-1]
    baseline_cpu = anomaly_now["baseline_cpu"]
    baseline_memory = anomaly_now["baseline_memory"]
    cpu_stddev = anomaly_now["cpu_stddev"]
    memory_stddev = anomaly_now["memory_stddev"]
    cpu_gap = anomaly_now["cpu_gap"]
    memory_gap = anomaly_now["memory_gap"]

    cpu_pressure = anomaly_now["current_cpu"] - baseline_cpu
    memory_pressure = anomaly_now["current_memory"] - baseline_memory
    deviation_pressure = risk["factors"]["deviation"]

    if memory_pressure > cpu_pressure and memory_pressure > 6:
        driver = "Memory-driven instability"
    elif cpu_pressure >= memory_pressure and cpu_pressure > 6:
        driver = "CPU-driven instability"
    elif deviation_pressure >= 45:
        driver = "Fluctuation-driven instability"
    else:
        driver = "Balanced system behavior"

    classification = _health_classification(risk["score"], anomaly_score)
    predicted_cpu = _project_next_value(cpu_values)
    predicted_memory = _project_next_value(memory_values)

    if predicted_memory - latest_memory >= 4:
        prediction_message = "The smoothed short-term memory forecast suggests continued upward pressure in the next monitoring window."
    elif predicted_cpu - latest_cpu >= 5:
        prediction_message = "The smoothed short-term CPU forecast suggests that load may remain elevated or rise further soon."
    elif anomaly_score >= 55:
        prediction_message = "Recent behavior suggests the system may move toward a higher risk state if the pattern continues."
    else:
        prediction_message = "The smoothed short-term forecast suggests the next few samples should remain close to the recent baseline."

    explanation = (
        f"The learned baseline is {baseline_cpu}% CPU and {baseline_memory}% memory. "
        f"Current behavior differs by {cpu_gap}% on CPU and {memory_gap}% on memory, "
        f"so the system is classified as {classification.lower()} with {confidence.lower()} anomaly confidence."
    )
    process_intelligence = analyze_process_intelligence(processes or [], driver)

    return {
        "baseline": {
            "cpu": baseline_cpu,
            "memory": baseline_memory,
            "cpu_stddev": cpu_stddev,
            "memory_stddev": memory_stddev,
        },
        "anomaly": {
            "score": anomaly_score,
            "confidence": confidence,
            "cpu_gap": cpu_gap,
            "memory_gap": memory_gap,
        },
        "health": {
            "classification": classification,
            "driver": driver,
        },
        "prediction": {
            "cpu_next": predicted_cpu,
            "memory_next": predicted_memory,
            "message": prediction_message,
        },
        "process": process_intelligence,
        "explanation": explanation,
    }
