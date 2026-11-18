StabilityAI Monitor
Project Progress Summary

This file tracks what has been completed in the project so far.
New changes can be appended in short form under the update log.

1. Core System Built
- Flask-based web dashboard created.
- SQLite database added for system and process sample storage.
- Background monitoring scheduler added.
- One-command startup support added through run.bat.

2. Monitoring Features
- Real-time CPU and memory monitoring added.
- Running process collection added.
- Top process listing added.
- Historical sampling and trend storage added.

3. Analysis Features
- Rule-based threshold analysis added.
- Trend analysis for CPU and memory added.
- Memory growth detection added.
- Sudden spike detection added.
- Stability risk score calculation added.
- Risk breakdown into intensity, duration, deviation, and process pressure added.

4. Intelligent Features
- Adaptive baseline learning added.
- Anomaly score calculation added.
- Health classification added.
- Forecast/prediction for CPU and memory added.
- Top suspect process identification added.
- Analyst-style incident summary added.

5. Dashboard Features
- Live dashboard cards and charts added.
- Alerts and recommendations sections added.
- Incident history timeline added.
- Incident filtering added.
- Export report button added.
- Pause/resume live update control added.
- Forecast labels updated to CPU Forecast and Memory Forecast.

6. Demo and Testing Features
- Demo mode switch added to dashboard.
- Demo: Normal scenario added.
- Demo: CPU Stress scenario added.
- Demo: Memory Leak scenario added.
- Demo: Sudden Spikes scenario added.
- Demo: Critical Instability scenario added.

7. Process Handling Improvements
- Idle process removed from meaningful process consideration.
- Internal project Python process filtered from top/high CPU process analysis.
- Process details improved for better identification.
- Open process location feature added.
- Suspicion score normalized to 0-100.

8. Reporting and Research Support
- Markdown report export added.
- Weight sensitivity research script added.
- Formula and threshold sensitivity research script added.
- Research reports generated for weight and formula comparison.
- Research-backed parameter tuning applied to the project.

9. 7th Semester ML Upgrade
- Rule-based system kept as baseline instead of being removed.
- Collection label support added for supervised ML data collection.
- Dashboard collection label selector added.
- Samples now store collection_label for system, process, and ML feature rows.
- Monitor overhead tracking added separately from suspect process analysis.
- Monitor app filtering refined so workload scripts remain visible.
- Controlled workload scripts added for CPU stress, memory pressure, and spike sessions.
- Labeled dataset export script added.
- Dependency-free supervised nearest-centroid classifier added.
- ML Classification dashboard section added for predicted class, confidence, ML state, and rule-vs-ML comparison.

10. Update Log
- Initial monitoring framework created.
- Dashboard and database integration completed.
- Rule-based and intelligent analysis added.
- Demo scenarios and incident history added.
- Report export and research calibration support added.
- Forecast smoothing and live update pause/resume added.
- Dashboard labels and layout refinements applied.
- Stability and anomaly score smoothing improved to prevent startup spikes, sudden drops, and unrealistic live anomaly max values.
- Weight and formula sensitivity reports regenerated after score calibration.
- Deviation scoring recalibrated so spike-and-recovery patterns no longer reach maximum severity or drop abruptly.
- Refresh button feedback improved with no-cache dashboard reload, loading state, and visible last refreshed time.
- Manual refresh button removed because automatic live updates already collect and refresh dashboard data.
- Deviation decay slowed with a longer analysis window, and last refreshed time display/cache refresh fixed.
- Deployment preparation removed for now; project remains focused on local run.bat execution.
- 7th-semester ML migration started with labels, controlled workload scripts, labeled export, and first supervised ML baseline.
