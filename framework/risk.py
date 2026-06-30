from statistics import mean


CPU_HIGH_THRESHOLD = 80
MEMORY_HIGH_THRESHOLD = 85
CPU_CRITICAL_THRESHOLD = 92
MEMORY_CRITICAL_THRESHOLD = 94
RECENT_WINDOW_SIZE = 12
DEVIATION_WINDOW_SIZE = 36
MEANINGFUL_MEMORY_GROWTH_DELTA = 1.0
SCORE_STABILIZATION_WINDOW = 5
FACTOR_STABILIZATION_WINDOW = 18


def _normalize(value, maximum):
    if maximum <= 0:
        return 0
    return max(0, min(100, round((value / maximum) * 100, 2)))


def _max_consecutive(values, threshold):
    longest = 0
    current = 0

    for value in values:
        if value >= threshold:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return longest


def _memory_growth_streak(values, minimum_delta=MEANINGFUL_MEMORY_GROWTH_DELTA):
    if len(values) < 2:
        return 0

    longest = 0
    current = 0

    for index in range(1, len(values)):
        if values[index] - values[index - 1] >= minimum_delta:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return longest


def _recent_values(values, size=RECENT_WINDOW_SIZE):
    return values[-size:] if len(values) > size else values


def _average_step_change(values):
    deltas = _step_changes(values)
    if not deltas:
        return 0

    return round(mean(deltas), 2)


def _step_changes(values):
    if len(values) < 2:
        return []

    return [abs(values[index] - values[index - 1]) for index in range(1, len(values))]


def _deviation_factor(cpu_values, memory_values):
    cpu_deltas = _step_changes(cpu_values)
    memory_deltas = _step_changes(memory_values)

    if not cpu_deltas and not memory_deltas:
        return 0

    cpu_average = mean(cpu_deltas) if cpu_deltas else 0
    memory_average = mean(memory_deltas) if memory_deltas else 0
    cpu_recent_average = mean(cpu_deltas[-6:]) if cpu_deltas else 0
    memory_recent_average = mean(memory_deltas[-6:]) if memory_deltas else 0
    cpu_peak = max(cpu_deltas) if cpu_deltas else 0
    memory_peak = max(memory_deltas) if memory_deltas else 0
    confidence = min(1, (max(len(cpu_values), len(memory_values)) - 1) / 6)

    deviation = (
        cpu_average * 1.2
        + cpu_recent_average * 1.0
        + cpu_peak * 0.45
        + memory_average * 0.8
        + memory_recent_average * 0.7
        + memory_peak * 0.30
    ) * confidence

    large_swings = sum(1 for delta in cpu_deltas if delta >= 25)
    large_swings += sum(1 for delta in memory_deltas if delta >= 6)

    if large_swings <= 1:
        deviation_cap = 70
    elif large_swings <= 2:
        deviation_cap = 75
    elif large_swings <= 3:
        deviation_cap = 88
    else:
        deviation_cap = 100

    return round(min(deviation_cap, deviation), 2)


def _stabilized_factor(samples, factor_name, current_value):
    if len(samples) < 2:
        return current_value

    recent_prefixes = [
        samples[:index]
        for index in range(
            max(1, len(samples) - FACTOR_STABILIZATION_WINDOW + 1),
            len(samples) + 1,
        )
    ]
    factor_values = [
        _calculate_current_risk_score(prefix)["factors"][factor_name]
        for prefix in recent_prefixes
    ]
    weights = list(range(1, len(factor_values) + 1))
    weighted_value = sum(value * weight for value, weight in zip(factor_values, weights)) / sum(weights)

    return round(max(current_value, weighted_value), 2)


def _calculate_current_risk_score(samples):
    if not samples:
        return {
            "score": 0,
            "level": "Low",
            "factors": {
                "intensity": 0,
                "duration": 0,
                "deviation": 0,
                "process_pressure": 0,
            },
            "metrics": {
                "avg_cpu": 0,
                "avg_memory": 0,
                "cpu_deviation": 0,
                "memory_deviation": 0,
                "cpu_streak": 0,
                "memory_streak": 0,
                "memory_growth_streak": 0,
            },
        }

    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    high_cpu_counts = [int(sample["high_cpu_processes"]) for sample in samples]
    high_memory_counts = [int(sample["high_memory_processes"]) for sample in samples]

    recent_cpu_values = _recent_values(cpu_values)
    recent_memory_values = _recent_values(memory_values)
    deviation_cpu_values = _recent_values(cpu_values, DEVIATION_WINDOW_SIZE)
    deviation_memory_values = _recent_values(memory_values, DEVIATION_WINDOW_SIZE)
    recent_high_cpu_counts = _recent_values(high_cpu_counts)
    recent_high_memory_counts = _recent_values(high_memory_counts)

    avg_cpu = round(mean(recent_cpu_values), 2)
    avg_memory = round(mean(recent_memory_values), 2)
    cpu_deviation = round(_average_step_change(recent_cpu_values), 2)
    memory_deviation = round(_average_step_change(recent_memory_values), 2)

    cpu_streak = _max_consecutive(recent_cpu_values, CPU_HIGH_THRESHOLD)
    memory_streak = _max_consecutive(recent_memory_values, MEMORY_HIGH_THRESHOLD)
    memory_growth_streak = _memory_growth_streak(recent_memory_values)

    intensity = round(avg_cpu * 0.45 + avg_memory * 0.25, 2)
    duration_raw = cpu_streak * 14 + memory_streak * 16 + memory_growth_streak * 6
    duration = _normalize(duration_raw, 100)
    deviation = _deviation_factor(deviation_cpu_values, deviation_memory_values)
    process_pressure_raw = mean(recent_high_cpu_counts) * 15 + mean(recent_high_memory_counts) * 10
    process_pressure = _normalize(process_pressure_raw, 100)

    critical_boost = 0
    if max(recent_cpu_values) >= CPU_CRITICAL_THRESHOLD:
        critical_boost += 8
    if max(recent_memory_values) >= MEMORY_CRITICAL_THRESHOLD:
        critical_boost += 8

    score = round(
        min(
            100,
            intensity * 0.45
            + duration * 0.25
            + deviation * 0.15
            + process_pressure * 0.15
            + critical_boost,
        ),
        2,
    )

    if score >= 80:
        level = "Critical"
    elif score >= 60:
        level = "High"
    elif score >= 20:
        level = "Medium"
    else:
        level = "Low"

    return {
        "score": score,
        "level": level,
        "factors": {
            "intensity": round(intensity, 2),
            "duration": round(duration, 2),
            "deviation": round(deviation, 2),
            "process_pressure": round(process_pressure, 2),
        },
        "metrics": {
            "avg_cpu": avg_cpu,
            "avg_memory": avg_memory,
            "cpu_deviation": cpu_deviation,
            "memory_deviation": memory_deviation,
            "cpu_streak": cpu_streak,
            "memory_streak": memory_streak,
            "memory_growth_streak": memory_growth_streak,
        },
    }


def _stabilized_score(samples, current_score):
    if len(samples) < 2:
        return current_score

    recent_prefixes = [
        samples[:index]
        for index in range(
            max(1, len(samples) - SCORE_STABILIZATION_WINDOW + 1),
            len(samples) + 1,
        )
    ]
    raw_scores = [_calculate_current_risk_score(prefix)["score"] for prefix in recent_prefixes]
    weights = list(range(1, len(raw_scores) + 1))
    weighted_score = sum(score * weight for score, weight in zip(raw_scores, weights)) / sum(weights)

    return round(max(current_score, weighted_score), 2)


def calculate_risk_score(samples):
    risk = _calculate_current_risk_score(samples)
    risk["score"] = _stabilized_score(samples, risk["score"])
    risk["factors"]["deviation"] = _stabilized_factor(samples, "deviation", risk["factors"]["deviation"])

    if risk["score"] >= 80:
        risk["level"] = "Critical"
    elif risk["score"] >= 60:
        risk["level"] = "High"
    elif risk["score"] >= 20:
        risk["level"] = "Medium"
    else:
        risk["level"] = "Low"

    return risk
