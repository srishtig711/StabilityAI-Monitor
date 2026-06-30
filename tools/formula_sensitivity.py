from __future__ import annotations

import random
import sys
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean, pstdev


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from framework.simulator import simulator


REPORTS_DIR = ROOT_DIR / "reports"
SCENARIO_STEPS = 24
SCENARIO_SEED = 20260429
SCENARIOS = [
    "demo_normal",
    "demo_cpu_stress",
    "demo_memory_leak",
    "demo_spike",
    "demo_critical",
]
SCENARIO_LABELS = {
    "demo_normal": "Normal",
    "demo_cpu_stress": "CPU Stress",
    "demo_memory_leak": "Memory Leak",
    "demo_spike": "Sudden Spikes",
    "demo_critical": "Critical Instability",
}


@dataclass(frozen=True)
class CalibrationConfig:
    collector_high_cpu: float = 70
    collector_high_memory: float = 20
    risk_cpu_high: float = 75
    risk_memory_high: float = 80
    risk_cpu_critical: float = 90
    risk_memory_critical: float = 92
    recent_window_size: int = 12
    meaningful_memory_growth_delta: float = 1.5
    intensity_cpu_weight: float = 0.62
    intensity_memory_weight: float = 0.22
    duration_cpu_factor: float = 14
    duration_memory_factor: float = 16
    duration_growth_factor: float = 6
    deviation_cpu_factor: float = 4.5
    deviation_memory_factor: float = 3.0
    process_pressure_cpu_factor: float = 15
    process_pressure_memory_factor: float = 10
    final_intensity_weight: float = 0.35
    final_duration_weight: float = 0.30
    final_deviation_weight: float = 0.20
    final_process_pressure_weight: float = 0.15
    critical_boost_value: float = 8
    risk_level_medium: float = 35
    risk_level_high: float = 60
    risk_level_critical: float = 80
    live_min_baseline_samples: int = 18
    live_current_window: int = 4
    live_baseline_window: int = 32
    demo_current_window: int = 3
    demo_baseline_window: int = 12
    sigma_floor_live: float = 8
    sigma_floor_demo: float = 5
    anomaly_cpu_sigma_live: float = 5
    anomaly_memory_sigma_live: float = 4
    anomaly_cpu_gap_live: float = 0.10
    anomaly_memory_gap_live: float = 0.08
    anomaly_cpu_gap_start_live: float = 6
    anomaly_memory_gap_start_live: float = 5
    anomaly_pressure_weight_live: float = 0.05
    anomaly_bootstrap_cap_live: float = 22
    anomaly_cpu_sigma_demo: float = 11
    anomaly_memory_sigma_demo: float = 11
    anomaly_cpu_gap_demo: float = 0.28
    anomaly_memory_gap_demo: float = 0.28
    anomaly_pressure_weight_demo: float = 0.16
    anomaly_smoothing_weights: tuple[float, float, float, float] = (0.45, 0.25, 0.18, 0.12)
    health_alpha: float = 0.55
    health_beta: float = 0.45
    health_watchlist: float = 25
    health_degrading: float = 45
    health_unstable: float = 65
    health_critical: float = 82
    process_score_cpu_weight: float = 0.55
    process_score_memory_weight: float = 0.35
    process_score_runtime_weight: float = 0.10
    process_driver_bonus_cpu: float = 0.25
    process_driver_bonus_memory: float = 0.25
    process_driver_bonus_fluctuation: float = 0.15


@dataclass
class ScenarioMetrics:
    final_score: float
    average_score: float
    volatility: float
    upward_ratio: float
    anomaly_final: float
    risk_final: float
    classification: str


BASE_CONFIG = CalibrationConfig()


def _safe_mean(values):
    return round(mean(values), 2) if values else 0


def _safe_stdev(values):
    if len(values) < 2:
        return 0
    return round(pstdev(values), 2)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _normalize(value, maximum):
    if maximum <= 0:
        return 0
    return max(0, min(100, round((value / maximum) * 100, 2)))


def _percentage_gap(current, baseline):
    if baseline <= 0:
        return 0
    return round(((current - baseline) / baseline) * 100, 2)


def _recent_values(values, size):
    return values[-size:] if len(values) > size else values


def _average_step_change(values):
    if len(values) < 2:
        return 0
    return round(mean(abs(values[index] - values[index - 1]) for index in range(1, len(values))), 2)


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


def _memory_growth_streak(values, minimum_delta):
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


def _rebuild_sample(snapshot, cfg: CalibrationConfig):
    top_processes = deepcopy(snapshot["top_processes"])
    high_cpu_processes = sum(1 for process in top_processes if float(process["cpu_percent"]) >= cfg.collector_high_cpu)
    high_memory_processes = sum(1 for process in top_processes if float(process["memory_percent"]) >= cfg.collector_high_memory)
    rebuilt = deepcopy(snapshot)
    rebuilt["high_cpu_processes"] = high_cpu_processes
    rebuilt["high_memory_processes"] = high_memory_processes
    rebuilt["top_processes"] = top_processes
    return rebuilt


def build_scenario_timelines(steps: int = SCENARIO_STEPS):
    timelines = {}
    for index, mode in enumerate(SCENARIOS):
        random.seed(SCENARIO_SEED + index)
        simulator.reset(mode)
        timelines[mode] = [simulator.generate_snapshot(mode) for _ in range(steps)]
    return timelines


def calculate_risk_score(samples, cfg: CalibrationConfig):
    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    high_cpu_counts = [int(sample["high_cpu_processes"]) for sample in samples]
    high_memory_counts = [int(sample["high_memory_processes"]) for sample in samples]

    recent_cpu_values = _recent_values(cpu_values, cfg.recent_window_size)
    recent_memory_values = _recent_values(memory_values, cfg.recent_window_size)
    recent_high_cpu_counts = _recent_values(high_cpu_counts, cfg.recent_window_size)
    recent_high_memory_counts = _recent_values(high_memory_counts, cfg.recent_window_size)

    avg_cpu = round(mean(recent_cpu_values), 2)
    avg_memory = round(mean(recent_memory_values), 2)
    cpu_deviation = round(_average_step_change(recent_cpu_values), 2)
    memory_deviation = round(_average_step_change(recent_memory_values), 2)

    cpu_streak = _max_consecutive(recent_cpu_values, cfg.risk_cpu_high)
    memory_streak = _max_consecutive(recent_memory_values, cfg.risk_memory_high)
    memory_growth_streak = _memory_growth_streak(recent_memory_values, cfg.meaningful_memory_growth_delta)

    intensity = round(avg_cpu * cfg.intensity_cpu_weight + avg_memory * cfg.intensity_memory_weight, 2)
    duration_raw = (
        cpu_streak * cfg.duration_cpu_factor
        + memory_streak * cfg.duration_memory_factor
        + memory_growth_streak * cfg.duration_growth_factor
    )
    duration = _normalize(duration_raw, 100)
    deviation = round(min(100, cpu_deviation * cfg.deviation_cpu_factor + memory_deviation * cfg.deviation_memory_factor), 2)
    process_pressure_raw = mean(recent_high_cpu_counts) * cfg.process_pressure_cpu_factor + mean(recent_high_memory_counts) * cfg.process_pressure_memory_factor
    process_pressure = _normalize(process_pressure_raw, 100)

    critical_boost = 0
    if max(recent_cpu_values) >= cfg.risk_cpu_critical:
        critical_boost += cfg.critical_boost_value
    if max(recent_memory_values) >= cfg.risk_memory_critical:
        critical_boost += cfg.critical_boost_value

    score = round(
        min(
            100,
            intensity * cfg.final_intensity_weight
            + duration * cfg.final_duration_weight
            + deviation * cfg.final_deviation_weight
            + process_pressure * cfg.final_process_pressure_weight
            + critical_boost,
        ),
        2,
    )

    if score >= cfg.risk_level_critical:
        level = "Critical"
    elif score >= cfg.risk_level_high:
        level = "High"
    elif score >= cfg.risk_level_medium:
        level = "Medium"
    else:
        level = "Low"

    return {
        "score": score,
        "level": level,
        "factors": {
            "intensity": intensity,
            "duration": duration,
            "deviation": deviation,
            "process_pressure": process_pressure,
        },
    }


def _compute_raw_anomaly(samples, cfg: CalibrationConfig, mode: str):
    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    high_cpu_counts = [int(sample["high_cpu_processes"]) for sample in samples]
    high_memory_counts = [int(sample["high_memory_processes"]) for sample in samples]

    if mode == "live" and len(samples) >= cfg.live_min_baseline_samples:
        current_window = samples[-cfg.live_current_window:]
        baseline_window = samples[-(cfg.live_current_window + cfg.live_baseline_window):-cfg.live_current_window] or samples[:-cfg.live_current_window] or samples
    elif len(samples) >= 8:
        current_window = samples[-cfg.demo_current_window:]
        baseline_window = samples[-(cfg.demo_current_window + cfg.demo_baseline_window):-cfg.demo_current_window] or samples[:-cfg.demo_current_window] or samples
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

    sigma_floor = cfg.sigma_floor_live if mode == "live" else cfg.sigma_floor_demo
    cpu_sigma_score = 0 if cpu_stddev == 0 else cpu_difference / max(cpu_stddev, sigma_floor)
    memory_sigma_score = 0 if memory_stddev == 0 else memory_difference / max(memory_stddev, sigma_floor)
    process_pressure_score = _clamp(_safe_mean(_recent_values(high_cpu_counts, 4)) * 7 + _safe_mean(_recent_values(high_memory_counts, 4)) * 6, 0, 100)

    if mode == "live":
        score = round(
            _clamp(
                cpu_sigma_score * cfg.anomaly_cpu_sigma_live
                + memory_sigma_score * cfg.anomaly_memory_sigma_live
                + max(0, cpu_gap - cfg.anomaly_cpu_gap_start_live) * cfg.anomaly_cpu_gap_live
                + max(0, memory_gap - cfg.anomaly_memory_gap_start_live) * cfg.anomaly_memory_gap_live
                + process_pressure_score * cfg.anomaly_pressure_weight_live,
                0,
                100,
            ),
            2,
        )
        if len(samples) < cfg.live_min_baseline_samples:
            score = round(min(score, cfg.anomaly_bootstrap_cap_live), 2)
    else:
        score = round(
            _clamp(
                cpu_sigma_score * cfg.anomaly_cpu_sigma_demo
                + memory_sigma_score * cfg.anomaly_memory_sigma_demo
                + max(0, cpu_gap) * cfg.anomaly_cpu_gap_demo
                + max(0, memory_gap) * cfg.anomaly_memory_gap_demo
                + process_pressure_score * cfg.anomaly_pressure_weight_demo,
                0,
                100,
            ),
            2,
        )

    return {
        "score": score,
        "cpu_gap": cpu_gap,
        "memory_gap": memory_gap,
    }


def calculate_anomaly_score(samples, cfg: CalibrationConfig, mode: str):
    anomalies = [
        _compute_raw_anomaly(samples[: len(samples) - offset], cfg, mode)
        if len(samples) - offset > 0
        else {"score": 0, "cpu_gap": 0, "memory_gap": 0}
        for offset in range(0, 4)
    ]
    weights = cfg.anomaly_smoothing_weights
    score = round(
        _clamp(sum(item["score"] * weight for item, weight in zip(anomalies, weights)), 0, 100),
        2,
    )
    return {
        "score": score,
        "cpu_gap": anomalies[0]["cpu_gap"],
        "memory_gap": anomalies[0]["memory_gap"],
    }


def classify_health(risk_score: float, anomaly_score: float, cfg: CalibrationConfig):
    combined = cfg.health_alpha * risk_score + cfg.health_beta * anomaly_score
    if combined >= cfg.health_critical:
        return "Critical", round(combined, 2)
    if combined >= cfg.health_unstable:
        return "Unstable", round(combined, 2)
    if combined >= cfg.health_degrading:
        return "Degrading", round(combined, 2)
    if combined >= cfg.health_watchlist:
        return "Watchlist", round(combined, 2)
    return "Stable", round(combined, 2)


def score_processes(processes, driver: str, cfg: CalibrationConfig):
    scored = []
    for process in processes:
        cpu = float(process.get("cpu_percent") or 0)
        memory = float(process.get("memory_percent") or 0)
        runtime = float(process.get("runtime_seconds") or 0)
        runtime_component = min(runtime / 600, 12) * cfg.process_score_runtime_weight
        score = cpu * cfg.process_score_cpu_weight + memory * cfg.process_score_memory_weight + runtime_component
        if driver == "CPU-driven instability":
            score += cpu * cfg.process_driver_bonus_cpu
        elif driver == "Memory-driven instability":
            score += memory * cfg.process_driver_bonus_memory
        elif driver == "Fluctuation-driven instability":
            score += max(cpu, memory) * cfg.process_driver_bonus_fluctuation
        scored.append(round(_clamp(score, 0, 100), 2))

    scored.sort(reverse=True)
    if not scored:
        return 0, 0
    gap = scored[0] - scored[1] if len(scored) > 1 else scored[0]
    return scored[0], round(gap, 2)


def infer_driver(samples, risk_factors, anomaly_cpu_gap, anomaly_memory_gap):
    cpu_values = [float(sample["cpu_percent"]) for sample in samples]
    memory_values = [float(sample["memory_percent"]) for sample in samples]
    cpu_pressure = cpu_values[-1] - _safe_mean(cpu_values[:-1] or cpu_values)
    memory_pressure = memory_values[-1] - _safe_mean(memory_values[:-1] or memory_values)
    if memory_pressure > cpu_pressure and anomaly_memory_gap > 6:
        return "Memory-driven instability"
    if cpu_pressure >= memory_pressure and anomaly_cpu_gap > 6:
        return "CPU-driven instability"
    if risk_factors["deviation"] >= 45:
        return "Fluctuation-driven instability"
    return "Balanced system behavior"


def evaluate_config(name: str, cfg: CalibrationConfig, scenario_timelines):
    per_scenario = {}
    process_gap_scores = []

    for mode, raw_snapshots in scenario_timelines.items():
        combined_scores = []
        risk_scores = []
        anomaly_scores = []

        for index in range(1, len(raw_snapshots) + 1):
            window = [_rebuild_sample(snapshot, cfg) for snapshot in raw_snapshots[:index]]
            risk = calculate_risk_score(window, cfg)
            anomaly = calculate_anomaly_score(window, cfg, mode)
            driver = infer_driver(window, risk["factors"], anomaly["cpu_gap"], anomaly["memory_gap"])
            _, gap = score_processes(window[-1]["top_processes"], driver, cfg)
            process_gap_scores.append(gap)
            classification, combined = classify_health(risk["score"], anomaly["score"], cfg)
            combined_scores.append(combined)
            risk_scores.append(risk["score"])
            anomaly_scores.append(anomaly["score"])

        deltas = [abs(combined_scores[index] - combined_scores[index - 1]) for index in range(1, len(combined_scores))]
        upward_steps = sum(1 for index in range(1, len(combined_scores)) if combined_scores[index] >= combined_scores[index - 1])
        final_classification, final_score = classify_health(risk_scores[-1], anomaly_scores[-1], cfg)

        per_scenario[mode] = ScenarioMetrics(
            final_score=final_score,
            average_score=round(mean(combined_scores), 2),
            volatility=round(mean(deltas), 2) if deltas else 0,
            upward_ratio=round(upward_steps / max(1, len(combined_scores) - 1), 2),
            anomaly_final=anomaly_scores[-1],
            risk_final=risk_scores[-1],
            classification=final_classification,
        )

    normal = per_scenario["demo_normal"]
    cpu_stress = per_scenario["demo_cpu_stress"]
    memory_leak = per_scenario["demo_memory_leak"]
    spike = per_scenario["demo_spike"]
    critical = per_scenario["demo_critical"]
    abnormal_mean = mean([cpu_stress.final_score, memory_leak.final_score, spike.final_score, critical.final_score])
    separation = abnormal_mean - normal.final_score
    stable_penalty = normal.final_score * 1.4 + normal.volatility * 2.5
    ordering_bonus = 0
    if critical.final_score > cpu_stress.final_score > normal.final_score:
        ordering_bonus += 10
    if memory_leak.final_score > normal.final_score:
        ordering_bonus += 6
    if spike.final_score > normal.final_score:
        ordering_bonus += 4
    if memory_leak.upward_ratio >= 0.65:
        ordering_bonus += 5
    if critical.classification in {"Critical", "Unstable", "Degrading"}:
        ordering_bonus += 4
    process_bonus = min(6, round(mean(process_gap_scores), 2))
    research_score = round(separation - stable_penalty + ordering_bonus + process_bonus, 2)
    return {
        "name": name,
        "config": cfg,
        "research_score": research_score,
        "scenarios": per_scenario,
    }


def run_family(label: str, variants, scenario_timelines):
    results = [evaluate_config(name, cfg, scenario_timelines) for name, cfg in variants]
    results.sort(key=lambda item: item["research_score"], reverse=True)
    return label, results


def build_variant_families():
    return [
        (
            "Health Fusion Weights",
            [
                ("alpha 0.30 / beta 0.70", replace(BASE_CONFIG, health_alpha=0.30, health_beta=0.70)),
                ("alpha 0.40 / beta 0.60", replace(BASE_CONFIG, health_alpha=0.40, health_beta=0.60)),
                ("alpha 0.50 / beta 0.50", replace(BASE_CONFIG, health_alpha=0.50, health_beta=0.50)),
                ("alpha 0.55 / beta 0.45", replace(BASE_CONFIG, health_alpha=0.55, health_beta=0.45)),
                ("alpha 0.60 / beta 0.40", replace(BASE_CONFIG, health_alpha=0.60, health_beta=0.40)),
                ("alpha 0.70 / beta 0.30", replace(BASE_CONFIG, health_alpha=0.70, health_beta=0.30)),
            ],
        ),
        (
            "Risk Factor Weights",
            [
                ("balanced 0.25/0.25/0.25/0.25", replace(BASE_CONFIG, final_intensity_weight=0.25, final_duration_weight=0.25, final_deviation_weight=0.25, final_process_pressure_weight=0.25)),
                ("current 0.35/0.30/0.20/0.15", BASE_CONFIG),
                ("duration-heavy 0.25/0.40/0.20/0.15", replace(BASE_CONFIG, final_intensity_weight=0.25, final_duration_weight=0.40, final_deviation_weight=0.20, final_process_pressure_weight=0.15)),
                ("intensity-heavy 0.45/0.25/0.15/0.15", replace(BASE_CONFIG, final_intensity_weight=0.45, final_duration_weight=0.25, final_deviation_weight=0.15, final_process_pressure_weight=0.15)),
                ("deviation-aware 0.30/0.25/0.30/0.15", replace(BASE_CONFIG, final_intensity_weight=0.30, final_duration_weight=0.25, final_deviation_weight=0.30, final_process_pressure_weight=0.15)),
            ],
        ),
        (
            "CPU and Memory Threshold Profiles",
            [
                ("aggressive 70/75/88/90", replace(BASE_CONFIG, risk_cpu_high=70, risk_memory_high=75, risk_cpu_critical=88, risk_memory_critical=90)),
                ("current 75/80/90/92", BASE_CONFIG),
                ("conservative 80/85/92/94", replace(BASE_CONFIG, risk_cpu_high=80, risk_memory_high=85, risk_cpu_critical=92, risk_memory_critical=94)),
            ],
        ),
        (
            "Process Count Threshold Profiles",
            [
                ("sensitive 60/15", replace(BASE_CONFIG, collector_high_cpu=60, collector_high_memory=15)),
                ("current 70/20", BASE_CONFIG),
                ("strict 80/25", replace(BASE_CONFIG, collector_high_cpu=80, collector_high_memory=25)),
            ],
        ),
        (
            "Memory Growth Delta",
            [
                ("delta 0.5", replace(BASE_CONFIG, meaningful_memory_growth_delta=0.5)),
                ("delta 1.0", replace(BASE_CONFIG, meaningful_memory_growth_delta=1.0)),
                ("delta 1.5", BASE_CONFIG),
                ("delta 2.0", replace(BASE_CONFIG, meaningful_memory_growth_delta=2.0)),
                ("delta 3.0", replace(BASE_CONFIG, meaningful_memory_growth_delta=3.0)),
            ],
        ),
        (
            "Health Classification Cutoffs",
            [
                ("loose 20/40/60/80", replace(BASE_CONFIG, health_watchlist=20, health_degrading=40, health_unstable=60, health_critical=80)),
                ("current 25/45/65/82", BASE_CONFIG),
                ("strict 30/50/70/85", replace(BASE_CONFIG, health_watchlist=30, health_degrading=50, health_unstable=70, health_critical=85)),
            ],
        ),
        (
            "Anomaly Smoothing Weights",
            [
                ("latest-heavy 0.60/0.20/0.12/0.08", replace(BASE_CONFIG, anomaly_smoothing_weights=(0.60, 0.20, 0.12, 0.08))),
                ("current 0.45/0.25/0.18/0.12", BASE_CONFIG),
                ("balanced 0.40/0.30/0.20/0.10", replace(BASE_CONFIG, anomaly_smoothing_weights=(0.40, 0.30, 0.20, 0.10))),
                ("history-aware 0.35/0.30/0.20/0.15", replace(BASE_CONFIG, anomaly_smoothing_weights=(0.35, 0.30, 0.20, 0.15))),
            ],
        ),
        (
            "Process Suspicion Weights",
            [
                ("cpu-dominant 0.70/0.20/0.10", replace(BASE_CONFIG, process_score_cpu_weight=0.70, process_score_memory_weight=0.20, process_score_runtime_weight=0.10)),
                ("current 0.55/0.35/0.10", BASE_CONFIG),
                ("balanced 0.50/0.40/0.10", replace(BASE_CONFIG, process_score_cpu_weight=0.50, process_score_memory_weight=0.40, process_score_runtime_weight=0.10)),
                ("memory-aware 0.40/0.50/0.10", replace(BASE_CONFIG, process_score_cpu_weight=0.40, process_score_memory_weight=0.50, process_score_runtime_weight=0.10)),
            ],
        ),
    ]


def build_report():
    scenario_timelines = build_scenario_timelines()
    families = [run_family(label, variants, scenario_timelines) for label, variants in build_variant_families()]

    lines = [
        "# Comprehensive Formula and Threshold Sensitivity Analysis",
        "",
        "This report studies the major scoring formulas and threshold families used in the project without changing the running dashboard.",
        "",
        "Method used:",
        "- the same simulated scenario timelines were replayed for every candidate setting",
        "- candidates were compared on normal stability, abnormal separation, volatility, and progression behavior",
        "- a research score was used to rank settings within each formula family",
        "",
        "Scenarios used:",
        ", ".join(SCENARIO_LABELS[mode] for mode in SCENARIOS),
        "",
        "## Family Winners",
        "",
        "| Formula Family | Best Candidate | Research Score | Normal | Critical |",
        "| --- | --- | --- | --- | --- |",
    ]

    for label, results in families:
        best = results[0]
        lines.append(
            f"| {label} | {best['name']} | {best['research_score']:.2f} | "
            f"{best['scenarios']['demo_normal'].final_score:.2f} | {best['scenarios']['demo_critical'].final_score:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Key Conclusions",
            "",
            "- A stronger rule-based contribution still works best for this project: higher `alpha` kept the normal scenario lower while preserving abnormal separation.",
            "- The current risk-factor balance is not always the winner; some families show that duration-heavy or threshold-conservative settings can improve realism.",
            "- Very sensitive thresholds usually inflate the normal scenario too much.",
            "- Very anomaly-heavy smoothing increases fluctuation instead of interpretability.",
            "",
        ]
    )

    for label, results in families:
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for item in results:
            lines.append(
                f"| {item['name']} | {item['research_score']:.2f} | "
                f"{item['scenarios']['demo_normal'].final_score:.2f} | "
                f"{item['scenarios']['demo_cpu_stress'].final_score:.2f} | "
                f"{item['scenarios']['demo_memory_leak'].final_score:.2f} | "
                f"{item['scenarios']['demo_spike'].final_score:.2f} | "
                f"{item['scenarios']['demo_critical'].final_score:.2f} |"
            )
        lines.append("")
        best = results[0]
        lines.append(f"Best candidate: `{best['name']}`")
        lines.append("")
        lines.append(
            f"It ranked first because it kept `Normal` at `{best['scenarios']['demo_normal'].final_score:.2f}` "
            f"while still pushing `Critical Instability` to `{best['scenarios']['demo_critical'].final_score:.2f}`."
        )
        lines.append("")

    return "\n".join(lines)


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "formula_sensitivity_report.md"
    report_path.write_text(build_report(), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
