# Weight Sensitivity Analysis

This report compares multiple `(alpha, beta)` combinations for the combined health score:

`CombinedScore = alpha * RiskScore + beta * AnomalyScore`

The same simulated scenario timelines were reused for every weight pair so the comparison stays fair.

## Compared Weight Pairs

(0.70, 0.30), (0.60, 0.40), (0.55, 0.45), (0.50, 0.50), (0.40, 0.60), (0.30, 0.70)

## Scenario Results

| Alpha | Beta | Research Score | Normal | CPU Stress | Memory Leak | Sudden Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.70 | 0.30 | 24.86 | 18.91 | 42.93 | 47.81 | 29.24 | 52.27 |
| 0.60 | 0.40 | 17.13 | 20.73 | 39.30 | 46.55 | 29.06 | 45.48 |
| 0.55 | 0.45 | 13.27 | 21.64 | 37.49 | 45.92 | 28.97 | 42.08 |
| 0.50 | 0.50 | 9.40 | 22.55 | 35.67 | 45.29 | 28.88 | 38.68 |
| 0.40 | 0.60 | -4.29 | 24.36 | 32.04 | 44.03 | 28.69 | 31.88 |
| 0.30 | 0.70 | -12.02 | 26.18 | 28.41 | 42.77 | 28.50 | 25.09 |

## Best Weight Pair

Selected pair: `alpha = 0.70`, `beta = 0.30`

Why it ranked best in this study:

- It achieved the highest research score of `24.86`.
- It kept the `Normal` scenario at `18.91`, avoiding unnecessary inflation under stable behavior.
- It still separated abnormal scenarios clearly, with `Critical Instability` reaching `52.27`.
- `Memory Leak` preserved an upward progression ratio of `0.78`, which is useful for a proactive monitoring story.

## Interpretation Notes

- Higher `alpha` means more trust in rule-based risk scoring.
- Higher `beta` means more trust in anomaly detection behavior.
- The research score rewards strong separation between normal and abnormal scenarios while penalizing an inflated normal score and unstable normal volatility.

## Scenario Details

### Alpha 0.70, Beta 0.30

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 18.91 | 16.00 | 1.30 | 0.65 | Stable |
| CPU Stress | 42.93 | 38.97 | 2.39 | 0.48 | Watchlist |
| Memory Leak | 47.81 | 31.51 | 1.86 | 0.78 | Degrading |
| Sudden Spikes | 29.24 | 25.97 | 2.41 | 0.57 | Watchlist |
| Critical Instability | 52.27 | 52.57 | 2.18 | 0.48 | Degrading |

### Alpha 0.60, Beta 0.40

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 20.73 | 16.46 | 1.68 | 0.65 | Stable |
| CPU Stress | 39.30 | 36.40 | 2.75 | 0.48 | Watchlist |
| Memory Leak | 46.55 | 31.58 | 2.02 | 0.74 | Degrading |
| Sudden Spikes | 29.06 | 26.02 | 3.02 | 0.52 | Watchlist |
| Critical Instability | 45.48 | 47.41 | 2.34 | 0.48 | Degrading |

### Alpha 0.55, Beta 0.45

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 21.64 | 16.69 | 1.87 | 0.65 | Stable |
| CPU Stress | 37.49 | 35.11 | 2.93 | 0.43 | Watchlist |
| Memory Leak | 45.92 | 31.61 | 2.16 | 0.70 | Degrading |
| Sudden Spikes | 28.97 | 26.05 | 3.34 | 0.52 | Watchlist |
| Critical Instability | 42.08 | 44.84 | 2.42 | 0.48 | Watchlist |

### Alpha 0.50, Beta 0.50

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 22.55 | 16.91 | 2.06 | 0.65 | Stable |
| CPU Stress | 35.67 | 33.82 | 3.13 | 0.43 | Watchlist |
| Memory Leak | 45.29 | 31.64 | 2.32 | 0.70 | Degrading |
| Sudden Spikes | 28.88 | 26.07 | 3.66 | 0.52 | Watchlist |
| Critical Instability | 38.68 | 42.26 | 2.50 | 0.48 | Watchlist |

### Alpha 0.40, Beta 0.60

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 24.36 | 17.37 | 2.43 | 0.65 | Stable |
| CPU Stress | 32.04 | 31.24 | 3.52 | 0.43 | Watchlist |
| Memory Leak | 44.03 | 31.71 | 2.63 | 0.65 | Watchlist |
| Sudden Spikes | 28.69 | 26.12 | 4.33 | 0.48 | Watchlist |
| Critical Instability | 31.88 | 37.10 | 2.65 | 0.48 | Watchlist |

### Alpha 0.30, Beta 0.70

| Scenario | Final Score | Average Score | Volatility | Upward Ratio | Classification |
| --- | --- | --- | --- | --- | --- |
| Normal | 26.18 | 17.83 | 2.81 | 0.65 | Watchlist |
| CPU Stress | 28.41 | 28.67 | 3.90 | 0.43 | Watchlist |
| Memory Leak | 42.77 | 31.77 | 2.94 | 0.65 | Watchlist |
| Sudden Spikes | 28.50 | 26.16 | 5.01 | 0.48 | Watchlist |
| Critical Instability | 25.09 | 31.95 | 2.81 | 0.48 | Watchlist |
