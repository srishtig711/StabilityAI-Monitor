# Proactive System Stability Monitoring Framework

This project implements a proactive system monitoring framework using Python, Flask, SQLite, `psutil`, HTML, CSS, and JavaScript.

## Features

- Real-time CPU and memory monitoring
- Process-level tracking
- Historical storage in SQLite
- Rule-based anomaly detection
- Stability risk score calculation
- Dashboard with charts, alerts, and recommendations

## How to Run

### One command

From the project folder, run:

```powershell
.\run.bat
```

This will create `.venv` if needed, install dependencies, and start the Flask app.

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

## Synopsis Mapping

- Data Collection: `framework/collector.py`
- Data Storage: `framework/database.py`
- Trend Analysis: `framework/analyzer.py`
- Anomaly Detection: `framework/analyzer.py`
- Risk Scoring: `framework/risk.py`
- Visualization: `templates/index.html`, `static/app.js`
