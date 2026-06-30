from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from framework.intelligence import analyze_intelligence
from framework.risk import calculate_risk_score
from framework.simulator import simulator


REPORTS_DIR = ROOT_DIR / "reports"
SCENARIO_STEPS = 24
SCENARIO_SEED = 20260428
WEIGHT_PAIRS = [
    (0.30, 0.70),
    (0.40, 0.60),
    (0.50, 0.50),
    (0.55, 0.45),
    (0.60, 0.40),
    (0.70, 0.30),
]
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


@dataclass
class ScenarioMetrics:
    final_score: float
    average_score: float
    volatility: float
    upward_ratio: float


def combined_score(risk_score: float, anomaly_score: float, alpha: float, beta: float) -> float:
    return round(alpha * risk_score + beta * anomaly_score, 2)


def classify_combined_score(score: float) -> str:
    if score >= 82:
        return "Critical"
    if score >= 65:
        return "Unstable"
    if score >= 45:
        return "Degrading"
    if score >= 25:
        return "Watchlist"
    return "Stable"


def build_scenario_timelines(steps: int = SCENARIO_STEPS) -> dict[str, list[dict]]:
    scenario_timelines: dict[str, list[dict]] = {}

    for index, mode in enumerate(SCENARIOS):
        random.seed(SCENARIO_SEED + index)
        simulator.reset(mode)

        snapshots = []
        for _ in range(steps):
            snapshots.append(simulator.generate_snapshot(mode))

        scenario_timelines[mode] = snapshots

    return scenario_timelines


def analyze_weight_pair(
    scenario_timelines: dict[str, list[dict]],
    alpha: float,
    beta: float,
) -> tuple[dict[str, ScenarioMetrics], float]:
    per_scenario: dict[str, ScenarioMetrics] = {}

    for mode, snapshots in scenario_timelines.items():
        combined_series = []

        for index in range(1, len(snapshots) + 1):
            window = snapshots[:index]
            risk = calculate_risk_score(window)
            intelligence = analyze_intelligence(window, risk, window[-1]["top_processes"], mode)
            combined = combined_score(risk["score"], intelligence["anomaly"]["score"], alpha, beta)
            combined_series.append(combined)

        deltas = [
            abs(combined_series[index] - combined_series[index - 1])
            for index in range(1, len(combined_series))
        ]
        upward_steps = sum(
            1 for index in range(1, len(combined_series))
            if combined_series[index] >= combined_series[index - 1]
        )

        per_scenario[mode] = ScenarioMetrics(
            final_score=combined_series[-1],
            average_score=round(mean(combined_series), 2),
            volatility=round(mean(deltas), 2) if deltas else 0,
            upward_ratio=round(upward_steps / max(1, len(combined_series) - 1), 2),
        )

    normal = per_scenario["demo_normal"]
    cpu_stress = per_scenario["demo_cpu_stress"]
    memory_leak = per_scenario["demo_memory_leak"]
    spike = per_scenario["demo_spike"]
    critical = per_scenario["demo_critical"]

    abnormal_mean = mean(
        [
            cpu_stress.final_score,
            memory_leak.final_score,
            spike.final_score,
            critical.final_score,
        ]
    )
    separation = abnormal_mean - normal.final_score
    stable_penalty = normal.final_score * 1.2 + normal.volatility * 2.0
    ordering_bonus = 0

    if critical.final_score > cpu_stress.final_score:
        ordering_bonus += 6
    if cpu_stress.final_score > normal.final_score:
        ordering_bonus += 6
    if memory_leak.final_score > normal.final_score:
        ordering_bonus += 6
    if spike.final_score > normal.final_score:
        ordering_bonus += 4
    if memory_leak.upward_ratio >= 0.65:
        ordering_bonus += 4

    research_score = round(separation - stable_penalty + ordering_bonus, 2)
    return per_scenario, research_score


def build_report() -> str:
    scenario_timelines = build_scenario_timelines()
    evaluations = []

    for alpha, beta in WEIGHT_PAIRS:
        per_scenario, research_score = analyze_weight_pair(scenario_timelines, alpha, beta)
        evaluations.append(
            {
                "alpha": alpha,
                "beta": beta,
                "research_score": research_score,
                "scenarios": per_scenario,
            }
        )

    evaluations.sort(key=lambda item: item["research_score"], reverse=True)
    best = evaluations[0]

    lines = [
        "# Weight Sensitivity Analysis",
        "",
        "This report compares multiple `(alpha, beta)` combinations for the combined health score:",
        "",
        "`CombinedScore = alpha * RiskScore + beta * AnomalyScore`",
        "",
        "The same simulated scenario timelines were reused for every weight pair so the comparison stays fair.",
        "",
        "## Compared Weight Pairs",
        "",
        ", ".join(f"({item['alpha']:.2f}, {item['beta']:.2f})" for item in evaluations),
        "",
        "## Scenario Results",
        "",
        "| Alpha | Beta | Research Score | Normal | CPU Stress | Memory Leak | Sudden Spikes | Critical |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in evaluations:
        lines.append(
            "| "
            f"{item['alpha']:.2f} | {item['beta']:.2f} | {item['research_score']:.2f} | "
            f"{item['scenarios']['demo_normal'].final_score:.2f} | "
            f"{item['scenarios']['demo_cpu_stress'].final_score:.2f} | "
            f"{item['scenarios']['demo_memory_leak'].final_score:.2f} | "
            f"{item['scenarios']['demo_spike'].final_score:.2f} | "
            f"{item['scenarios']['demo_critical'].final_score:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Best Weight Pair",
            "",
            f"Selected pair: `alpha = {best['alpha']:.2f}`, `beta = {best['beta']:.2f}`",
            "",
            "Why it ranked best in this study:",
            "",
            f"- It achieved the highest research score of `{best['research_score']:.2f}`.",
            f"- It kept the `Normal` scenario at `{best['scenarios']['demo_normal'].final_score:.2f}`, avoiding unnecessary inflation under stable behavior.",
            f"- It still separated abnormal scenarios clearly, with `Critical Instability` reaching `{best['scenarios']['demo_critical'].final_score:.2f}`.",
            f"- `Memory Leak` preserved an upward progression ratio of `{best['scenarios']['demo_memory_leak'].upward_ratio:.2f}`, which is useful for a proactive monitoring story.",
            "",
            "## Interpretation Notes",
            "",
            "- Higher `alpha` means more trust in rule-based risk scoring.",
            "- Higher `beta` means more trust in anomaly detection behavior.",
            "- The research score rewards strong separation between normal and abnormal scenarios while penalizing an inflated normal score and unstable normal volatility.",
            "",
            "## Scenario Details",
            "",
        ]
    )

    for item in evaluations:
        lines.append(f"### Alpha {item['alpha']:.2f}, Beta {item['beta']:.2f}")
        lines.append("")
        lines.append("| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |")
        lines.append("| --- | --- | --- | --- | --- | --- |")

        for mode in SCENARIOS:
            metrics = item["scenarios"][mode]
            lines.append(
                "| "
                f"{SCENARIO_LABELS[mode]} | "
                f"{metrics.final_score:.2f} | "
                f"{metrics.average_score:.2f} | "
                f"{metrics.volatility:.2f} | "
                f"{metrics.upward_ratio:.2f} | "
                f"{classify_combined_score(metrics.final_score)} |"
            )

        lines.append("")

    return "\n".join(lines)


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "weight_sensitivity_report.md"
    report_path.write_text(build_report(), encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
