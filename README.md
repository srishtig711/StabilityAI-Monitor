# Proactive System Stability Monitoring Framework

This project implements a proactive system monitoring framework using Python, Flask, SQLite, `psutil`, HTML, CSS, JavaScript, and Chart.js.

The 6th-semester version was primarily rule-based. The 7th-semester upgrade keeps that rule-based system as a baseline and adds supervised ML classification beside it, using labeled samples collected from real system usage and controlled workload sessions.

## Current Features

- Real-time CPU and memory monitoring
- Process-level tracking with monitor-process filtering
- Historical storage in SQLite
- Rule-based trend, threshold, incident, and risk analysis
- Adaptive baseline and anomaly scoring
- Dashboard with charts, alerts, recommendations, incident history, and report export
- Active collection labels for supervised ML data collection
- Monitor overhead tracking for the Flask monitoring process
- Controlled workload scripts for CPU stress, memory pressure, and spike sessions
- Labeled dataset export for supervised learning
- Dependency-free nearest-centroid ML baseline classifier
- Rule-based vs ML dashboard comparison

## Architecture

| Area | Main files |
| --- | --- |
| Flask app and API routes | `app.py` |
| System/process collection | `framework/collector.py` |
| SQLite schema and persistence | `framework/database.py` |
| Rule-based dashboard analysis | `framework/analyzer.py`, `framework/risk.py` |
| Adaptive baseline intelligence | `framework/intelligence.py` |
| Collection labels | `framework/labels.py` |
| ML prediction runtime | `framework/ml_model.py` |
| Dashboard UI | `templates/index.html`, `static/app.js`, `static/styles.css` |
| Workload scripts | `tools/workload_cpu_stress.py`, `tools/workload_memory_pressure.py`, `tools/workload_spike.py` |
| Dataset/training tools | `tools/export_labeled_dataset.py`, `tools/train_ml_model.py` |

## How to Run

### One command

From the project folder, run:

```powershell
.\run.bat
```

This creates `.venv` if needed, installs dependencies, and starts the Flask app.

### Manual setup

1. Create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   python app.py
   ```

4. Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Labeled Data Collection

Use the dashboard's **Collection Label** selector before and during each data collection session.

Available labels:

- `unlabeled`
- `stable`
- `normal_work`
- `cpu_stress`
- `memory_pressure`
- `spike`
- `heavy_multitasking`
- `critical`

Recommended collection approach:

1. Start the dashboard with `python app.py` or `.\run.bat`.
2. Set the correct collection label in the dashboard.
3. Let the monitor collect samples while the real workload is happening.
4. Change the label when the workload type changes.
5. Return the label to `unlabeled` when you are not intentionally collecting training data.

The model uses numeric resource and process-summary features. It does not train on exact process names, so workload scripts are safe to use as controlled load sources without making the model depend on `python.exe`.

## Controlled Workloads

These scripts generate real system load and should only be used during labeled collection sessions.

CPU stress:

```powershell
python tools\workload_cpu_stress.py --duration 120 --workers 4 --duty-cycle 90
```

Memory pressure:

```powershell
python tools\workload_memory_pressure.py --duration 120 --target-mb 512 --step-mb 32
```

Spike workload:

```powershell
python tools\workload_spike.py --duration 120 --workers 4 --burst 3 --rest 4
```

Start with smaller values if the system feels slow, especially for memory pressure.

## Dataset Export

Export supervised-learning rows after collecting labeled samples:

```powershell
python tools\export_labeled_dataset.py
```

By default, this excludes `unlabeled` rows and writes:

```text
reports\labeled_stability_dataset.csv
```

Useful options:

```powershell
python tools\export_labeled_dataset.py --features-only
python tools\export_labeled_dataset.py --include-unlabeled
```

## Training the ML Baseline

Train after enough labeled samples exist across at least two labels:

```powershell
python tools\train_ml_model.py
```

Outputs:

- `models\stability_model.pkl`
- `reports\ml_evaluation_report.md`

The current baseline is a standard-scaled nearest-centroid classifier. It was chosen because it is supervised, explainable, and does not require extra dependencies beyond the current project setup.

If no trained model exists yet, the dashboard shows **Not trained** in the ML Classification section while the rule-based system continues working normally.

## 7th-Semester Roadmap

- Keep rule-based analysis as the baseline.
- Collect real labeled samples from normal usage, app workloads, and controlled workloads.
- Train and evaluate the ML classifier on numeric resource/process-summary features.
- Compare ML classification against the rule-based health state.
- Improve the classifier after enough balanced labeled data is available.
- Use reports and dashboard screenshots for project evaluation and presentation.
