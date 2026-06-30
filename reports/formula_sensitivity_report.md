# Comprehensive Formula and Threshold Sensitivity Analysis

This report studies the major scoring formulas and threshold families used in the project without changing the running dashboard.

Method used:
- the same simulated scenario timelines were replayed for every candidate setting
- candidates were compared on normal stability, abnormal separation, volatility, and progression behavior
- a research score was used to rank settings within each formula family

Scenarios used:
Normal, CPU Stress, Memory Leak, Sudden Spikes, Critical Instability

## Family Winners

| Formula Family | Best Candidate | Research Score | Normal | Critical |
| --- | --- | --- | --- | --- |
| Health Fusion Weights | alpha 0.70 / beta 0.30 | 32.38 | 18.45 | 55.33 |
| Risk Factor Weights | intensity-heavy 0.45/0.25/0.15/0.15 | 16.31 | 22.29 | 46.28 |
| CPU and Memory Threshold Profiles | conservative 80/85/92/94 | 17.53 | 21.39 | 45.07 |
| Process Count Threshold Profiles | sensitive 60/15 | 19.80 | 21.39 | 47.51 |
| Memory Growth Delta | delta 1.0 | 8.85 | 21.39 | 45.07 |
| Health Classification Cutoffs | loose 20/40/60/80 | 8.85 | 21.39 | 45.07 |
| Anomaly Smoothing Weights | latest-heavy 0.60/0.20/0.12/0.08 | 12.52 | 21.92 | 44.88 |
| Process Suspicion Weights | cpu-dominant 0.70/0.20/0.10 | 9.04 | 21.39 | 45.07 |

## Key Conclusions

- A stronger rule-based contribution still works best for this project: higher `alpha` kept the normal scenario lower while preserving abnormal separation.
- The current risk-factor balance is not always the winner; some families show that duration-heavy or threshold-conservative settings can improve realism.
- Very sensitive thresholds usually inflate the normal scenario too much.
- Very anomaly-heavy smoothing increases fluctuation instead of interpretability.

## Health Fusion Weights

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| alpha 0.70 / beta 0.30 | 32.38 | 18.45 | 51.92 | 52.18 | 34.70 | 55.33 |
| alpha 0.60 / beta 0.40 | 23.35 | 20.41 | 47.43 | 51.09 | 33.73 | 48.49 |
| alpha 0.55 / beta 0.45 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| alpha 0.50 / beta 0.50 | 0.35 | 22.37 | 42.95 | 50.00 | 32.77 | 41.64 |
| alpha 0.40 / beta 0.60 | -8.67 | 24.33 | 38.46 | 48.91 | 31.80 | 34.80 |
| alpha 0.30 / beta 0.70 | -17.67 | 26.29 | 33.97 | 47.82 | 30.84 | 27.96 |

Best candidate: `alpha 0.70 / beta 0.30`

It ranked first because it kept `Normal` at `18.45` while still pushing `Critical Instability` to `55.33`.

## Risk Factor Weights

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| intensity-heavy 0.45/0.25/0.15/0.15 | 16.31 | 22.29 | 44.75 | 49.48 | 31.92 | 46.28 |
| duration-heavy 0.25/0.40/0.20/0.15 | 12.76 | 20.36 | 47.44 | 53.87 | 32.32 | 46.26 |
| current 0.35/0.30/0.20/0.15 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| deviation-aware 0.30/0.25/0.30/0.15 | 4.01 | 21.14 | 42.67 | 47.69 | 37.30 | 40.84 |
| balanced 0.25/0.25/0.25/0.25 | 3.81 | 20.16 | 40.12 | 46.11 | 33.58 | 38.35 |

Best candidate: `intensity-heavy 0.45/0.25/0.15/0.15`

It ranked first because it kept `Normal` at `22.29` while still pushing `Critical Instability` to `46.28`.

## CPU and Memory Threshold Profiles

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| conservative 80/85/92/94 | 17.53 | 21.39 | 39.91 | 50.54 | 33.25 | 45.07 |
| aggressive 70/75/88/90 | 9.43 | 21.39 | 45.19 | 50.54 | 35.56 | 45.07 |
| current 75/80/90/92 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |

Best candidate: `conservative 80/85/92/94`

It ranked first because it kept `Normal` at `21.39` while still pushing `Critical Instability` to `45.07`.

## Process Count Threshold Profiles

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| sensitive 60/15 | 19.80 | 21.39 | 45.19 | 51.88 | 33.25 | 47.51 |
| current 70/20 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| strict 80/25 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |

Best candidate: `sensitive 60/15`

It ranked first because it kept `Normal` at `21.39` while still pushing `Critical Instability` to `47.51`.

## Memory Growth Delta

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| delta 1.0 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| delta 1.5 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| delta 2.0 | 8.60 | 21.39 | 45.19 | 50.54 | 32.26 | 45.07 |
| delta 3.0 | 8.60 | 21.39 | 45.19 | 50.54 | 32.26 | 45.07 |
| delta 0.5 | 6.15 | 22.38 | 45.19 | 50.54 | 33.25 | 45.07 |

Best candidate: `delta 1.0`

It ranked first because it kept `Normal` at `21.39` while still pushing `Critical Instability` to `45.07`.

## Health Classification Cutoffs

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| loose 20/40/60/80 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| current 25/45/65/82 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| strict 30/50/70/85 | 4.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |

Best candidate: `loose 20/40/60/80`

It ranked first because it kept `Normal` at `21.39` while still pushing `Critical Instability` to `45.07`.

## Anomaly Smoothing Weights

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| latest-heavy 0.60/0.20/0.12/0.08 | 12.52 | 21.92 | 44.53 | 51.07 | 32.35 | 44.88 |
| history-aware 0.35/0.30/0.20/0.15 | 10.12 | 21.08 | 45.61 | 50.23 | 33.98 | 45.14 |
| current 0.45/0.25/0.18/0.12 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| balanced 0.40/0.30/0.20/0.10 | 8.65 | 21.57 | 45.48 | 50.62 | 33.96 | 45.02 |

Best candidate: `latest-heavy 0.60/0.20/0.12/0.08`

It ranked first because it kept `Normal` at `21.92` while still pushing `Critical Instability` to `44.88`.

## Process Suspicion Weights

| Candidate | Research Score | Normal | CPU Stress | Memory Leak | Spikes | Critical |
| --- | --- | --- | --- | --- | --- | --- |
| cpu-dominant 0.70/0.20/0.10 | 9.04 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| current 0.55/0.35/0.10 | 8.85 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| balanced 0.50/0.40/0.10 | 8.79 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |
| memory-aware 0.40/0.50/0.10 | 8.68 | 21.39 | 45.19 | 50.54 | 33.25 | 45.07 |

Best candidate: `cpu-dominant 0.70/0.20/0.10`

It ranked first because it kept `Normal` at `21.39` while still pushing `Critical Instability` to `45.07`.
