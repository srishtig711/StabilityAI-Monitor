import os
import subprocess

from flask import Flask, jsonify, render_template, request

from framework.analyzer import build_dashboard_payload
from framework.collector import snapshot_system
from framework.database import ensure_database
from framework.labels import get_label_details, set_current_label
from framework.modes import get_mode_details, set_current_mode
from framework.reporting import export_report
from framework.scheduler import start_background_monitor


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard():
    incident_filter = request.args.get("incident_filter", "all")
    return jsonify(build_dashboard_payload(incident_filter=incident_filter))


@app.route("/api/collect", methods=["POST"])
def collect_now():
    record = snapshot_system()
    return jsonify({"status": "ok", "recorded_at": record["created_at"]})


@app.route("/api/mode", methods=["POST"])
def change_mode():
    payload = request.get_json(silent=True) or {}
    selected_mode = payload.get("mode", "live")
    details = set_current_mode(selected_mode)
    record = snapshot_system()
    return jsonify(
        {
            "status": "ok",
            "mode": {"key": selected_mode, **details},
            "recorded_at": record["created_at"],
        }
    )


@app.route("/api/mode", methods=["GET"])
def current_mode():
    return jsonify(get_mode_details())


@app.route("/api/label", methods=["GET"])
def current_label():
    return jsonify(get_label_details())


@app.route("/api/label", methods=["POST"])
def change_label():
    payload = request.get_json(silent=True) or {}
    selected_label = payload.get("label", "unlabeled")
    try:
        details = set_current_label(selected_label)
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    return jsonify({"status": "ok", "collection_label": details})


@app.route("/api/process/open", methods=["POST"])
def open_process_location():
    payload = request.get_json(silent=True) or {}
    executable_path = payload.get("path", "")

    if not executable_path:
        return jsonify({"status": "error", "message": "No executable path provided."}), 400

    if not os.path.exists(executable_path):
        return jsonify({"status": "error", "message": "Executable path not found on this system."}), 404

    normalized_path = os.path.normpath(executable_path)
    subprocess.Popen(["explorer.exe", "/select,", normalized_path])
    return jsonify({"status": "ok"})


@app.route("/api/report/export", methods=["POST"])
def export_monitoring_report():
    payload = request.get_json(silent=True) or {}
    incident_filter = payload.get("incident_filter", "all")
    dashboard_payload = build_dashboard_payload(incident_filter=incident_filter)
    report_path = export_report(dashboard_payload)
    return jsonify({"status": "ok", "path": str(report_path)})


if __name__ == "__main__":
    ensure_database()
    start_background_monitor()
    app.run(debug=False, use_reloader=False)
