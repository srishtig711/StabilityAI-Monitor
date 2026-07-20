let cpuChart;
let memoryChart;
let availableModes = [];
let availableLabels = [];
let readingPanelsLocked = false;
let lastAlertsSignature = "";
let lastRecommendationsSignature = "";
let currentIncidentFilter = "all";
let liveUpdatesPaused = false;
let dashboardIntervalId;

function createChart(context, label, color) {
    return new Chart(context, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label,
                    data: [],
                    borderColor: color,
                    backgroundColor: `${color}33`,
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    ticks: { color: "#9fb0c7" },
                    grid: { color: "rgba(148, 163, 184, 0.12)" }
                },
                x: {
                    ticks: { color: "#9fb0c7" },
                    grid: { color: "rgba(148, 163, 184, 0.08)" }
                }
            },
            plugins: {
                legend: {
                    labels: { color: "#edf2f7" }
                }
            }
        }
    });
}

function setText(id, value) {
    document.getElementById(id).textContent = value;
}

function formatRefreshTime(value) {
    if (!value) {
        return "--";
    }

    const textValue = String(value);
    const timePart = textValue.includes("T") ? textValue.split("T")[1] : textValue;
    if (/^\d{2}:\d{2}:\d{2}/.test(timePart)) {
        return timePart.slice(0, 8);
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return textValue.replace("T", " ");
    }

    return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    }).format(date);
}

function renderList(id, items) {
    const list = document.getElementById(id);
    list.innerHTML = "";
    list.classList.remove("detailed");

    items.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
    });
}

function renderAlerts(id, alerts) {
    const list = document.getElementById(id);
    list.innerHTML = "";
    list.classList.add("detailed");

    alerts.forEach((alert) => {
        const li = document.createElement("li");
        li.className = `message-item ${alert.severity}`;
        li.innerHTML = `
            <strong>${alert.title}</strong>
            <p>${alert.message}</p>
        `;
        list.appendChild(li);
    });
}

function renderIncidentHistory(events) {
    const list = document.getElementById("incident-history-list");
    list.innerHTML = "";
    list.classList.add("detailed");

    if (!events.length) {
        const li = document.createElement("li");
        li.className = "message-item low";
        li.innerHTML = `
            <strong>No recent incidents</strong>
            <p>The timeline will populate as the system detects meaningful events.</p>
        `;
        list.appendChild(li);
        return;
    }

    events.forEach((event) => {
        const li = document.createElement("li");
        li.className = `message-item ${event.severity}`;
        const occurrenceText = buildOccurrenceText(event);
        const readableTime = formatIncidentTime(event.time);
        li.innerHTML = `
            <strong>${event.title}${occurrenceText}</strong>
            <p>${event.message}</p>
            <p>${readableTime}</p>
        `;
        list.appendChild(li);
    });
}

function buildOccurrenceText(event) {
    const occurrences = Number(event.occurrences || 1);
    const label = occurrences === 1 ? "time" : "times";
    return ` (${occurrences} ${label} in last 10 minutes)`;
}

function formatIncidentTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value).replace("T", " ");
    }

    return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    }).format(date);
}

function buildSignature(value) {
    return JSON.stringify(value);
}

function setPanelLockState(locked) {
    readingPanelsLocked = locked;
}

function updateLiveUpdateUi() {
    const button = document.getElementById("toggle-live-button");
    const status = document.getElementById("live-update-status");

    if (!button || !status) {
        return;
    }

    button.textContent = liveUpdatesPaused ? "Resume Updates" : "Pause Updates";
    status.textContent = liveUpdatesPaused ? "Live updates paused for analysis" : "Live updates active";
    status.className = `live-update-status ${liveUpdatesPaused ? "paused" : "active"}`;
}

function renderProcesses(processes) {
    const tbody = document.getElementById("process-table-body");
    tbody.innerHTML = "";

    processes.forEach((process) => {
        const row = document.createElement("tr");
        const displayName = process.display_name || process.name;
        const details = process.details || process.name;
        const canOpen = Boolean(process.executable_path);
        row.innerHTML = `
            <td>${process.pid}</td>
            <td class="process-name-cell">
                <strong>${displayName}</strong>
                <span>${process.name}</span>
            </td>
            <td class="process-details-cell" title="${details}">${details}</td>
            <td>${Number(process.cpu_percent).toFixed(2)}</td>
            <td>${Number(process.memory_percent).toFixed(2)}</td>
            <td>${Number(process.runtime_seconds).toFixed(0)}</td>
            <td>${process.status}</td>
            <td>
                <button
                    type="button"
                    class="open-process-button"
                    ${canOpen ? "" : "disabled"}
                    data-path="${process.executable_path || ""}"
                >
                    Open
                </button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function openProcessLocation(event) {
    const button = event.target.closest(".open-process-button");
    if (!button || button.disabled) {
        return;
    }

    const path = button.dataset.path;
    const response = await fetch("/api/process/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
    });

    if (!response.ok) {
        const payload = await response.json().catch(() => ({ message: "Unable to open process location." }));
        window.alert(payload.message || "Unable to open process location.");
    }
}

function updateCharts(charts) {
    const cpuLabels = charts.cpu.map((point) => point.time);
    const cpuData = charts.cpu.map((point) => point.value);
    cpuChart.data.labels = cpuLabels;
    cpuChart.data.datasets[0].data = cpuData;
    cpuChart.update();

    const memoryLabels = charts.memory.map((point) => point.time);
    const memoryData = charts.memory.map((point) => point.value);
    memoryChart.data.labels = memoryLabels;
    memoryChart.data.datasets[0].data = memoryData;
    memoryChart.update();
}

function updateRiskLevel(level) {
    const riskLevel = document.getElementById("risk-level");
    riskLevel.textContent = level;
    riskLevel.className = `hero-risk-level ${level.toLowerCase()}`;
}

function renderModeOptions(monitoringMode) {
    const select = document.getElementById("mode-select");
    const currentMode = monitoringMode.current.key;

    if (availableModes.length === 0) {
        availableModes = monitoringMode.available;
        select.innerHTML = "";

        availableModes.forEach((mode) => {
            const option = document.createElement("option");
            option.value = mode.key;
            option.textContent = mode.label;
            select.appendChild(option);
        });
    }

    select.value = currentMode;
    document.getElementById("mode-description").textContent = monitoringMode.current.description;
}

function renderLabelOptions(collectionLabel) {
    const select = document.getElementById("label-select");
    const currentLabel = collectionLabel.current.key;

    if (availableLabels.length === 0) {
        availableLabels = collectionLabel.available;
        select.innerHTML = "";

        availableLabels.forEach((label) => {
            const option = document.createElement("option");
            option.value = label.key;
            option.textContent = label.label;
            select.appendChild(option);
        });
    }

    select.value = currentLabel;
    document.getElementById("label-description").textContent = collectionLabel.current.description;
}

function labelDisplayName(key, labels) {
    const match = (labels || []).find((label) => label.key === key);
    return match ? match.label : key;
}

async function fetchDashboard(options = {}) {
    const { force = false } = options;
    if (liveUpdatesPaused && !force) {
        return;
    }

    const response = await fetch(`/api/dashboard?incident_filter=${encodeURIComponent(currentIncidentFilter)}&_=${Date.now()}`);
    const payload = await response.json();

    setText("cpu-usage", `${payload.summary.cpu_percent}%`);
    setText("memory-usage", `${payload.summary.memory_percent}%`);
    setText("process-count", payload.summary.total_processes);
    setText("health-classification", payload.summary.health_classification ?? "Stable");
    setText("anomaly-score", payload.summary.anomaly_score ?? 0);
    setText("high-cpu-processes", payload.summary.high_cpu_processes ?? 0);
    setText("high-memory-processes", payload.summary.high_memory_processes ?? 0);
    setText(
        "latest-sample-label",
        labelDisplayName(payload.summary.collection_label ?? "unlabeled", payload.collection_label?.available)
    );
    setText("risk-score", payload.summary.risk_score);
    setText("last-refresh-time", `Last refreshed: ${formatRefreshTime(payload.summary.latest_sample_time)}`);
    updateRiskLevel(payload.summary.risk_level);

    setText("cpu-trend", payload.analysis.cpu_trend);
    setText("memory-trend", payload.analysis.memory_trend);
    setText("cpu-streak", payload.analysis.cpu_streak ?? 0);
    setText("memory-streak", payload.analysis.memory_streak ?? 0);
    setText("memory-growth-streak", payload.analysis.memory_growth_streak ?? 0);
    setText("analysis-observation", payload.analysis.observation);
    setText("risk-intensity", payload.risk_breakdown.intensity ?? 0);
    setText("risk-duration", payload.risk_breakdown.duration ?? 0);
    setText("risk-deviation", payload.risk_breakdown.deviation ?? 0);
    setText("risk-process-pressure", payload.risk_breakdown.process_pressure ?? 0);
    setText("baseline-cpu", payload.intelligence.baseline.cpu ?? 0);
    setText("baseline-memory", payload.intelligence.baseline.memory ?? 0);
    setText("anomaly-confidence", payload.intelligence.anomaly.confidence ?? "Low");
    setText("health-driver", payload.intelligence.health.driver ?? "None");
    setText("predicted-cpu", payload.intelligence.prediction.cpu_next ?? 0);
    setText("predicted-memory", payload.intelligence.prediction.memory_next ?? 0);
    setText("suspect-name", payload.intelligence.process.top_suspect.display_name ?? "None");
    setText("suspect-pid", payload.intelligence.process.top_suspect.pid ?? "-");
    setText("suspect-score", payload.intelligence.process.top_suspect.score ?? 0);
    setText("suspect-label", payload.intelligence.process.top_suspect.label ?? "None");
    renderModeOptions(payload.monitoring_mode);
    renderLabelOptions(payload.collection_label);
    document.getElementById("incident-filter").value = payload.incident_filter ?? "all";

    if (!readingPanelsLocked) {
        setText("incident-title", payload.incident_summary.title ?? "Waiting for monitoring data");
        setText("incident-narrative", payload.incident_summary.narrative ?? "");
        setText("intelligence-explanation", payload.intelligence.explanation ?? "");
        setText("prediction-message", payload.intelligence.prediction.message ?? "");
        setText("suspect-summary", payload.intelligence.process.summary ?? "");
        setText("suspect-reason", payload.intelligence.process.top_suspect.reason ?? "");
        renderIncidentHistory(payload.incident_history ?? []);
    }

    const nextAlertsSignature = buildSignature(payload.alerts);
    const nextRecommendationsSignature = buildSignature(payload.recommendations);

    if (!readingPanelsLocked && nextAlertsSignature !== lastAlertsSignature) {
        renderAlerts("alerts-list", payload.alerts);
        lastAlertsSignature = nextAlertsSignature;
    }

    if (!readingPanelsLocked && nextRecommendationsSignature !== lastRecommendationsSignature) {
        renderList("recommendations-list", payload.recommendations);
        lastRecommendationsSignature = nextRecommendationsSignature;
    }

    renderProcesses(payload.processes);
    updateCharts(payload.charts);
}

async function changeMode(event) {
    const mode = event.target.value;
    await fetch("/api/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
    });
    await fetchDashboard({ force: true });
}

async function changeLabel(event) {
    const label = event.target.value;
    const response = await fetch("/api/label", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label })
    });

    if (!response.ok) {
        const payload = await response.json().catch(() => ({ message: "Unable to change collection label." }));
        window.alert(payload.message || "Unable to change collection label.");
    }

    await fetchDashboard({ force: true });
}

async function changeIncidentFilter(event) {
    currentIncidentFilter = event.target.value;
    await fetchDashboard({ force: true });
}

async function toggleLiveUpdates() {
    liveUpdatesPaused = !liveUpdatesPaused;
    updateLiveUpdateUi();

    if (!liveUpdatesPaused) {
        await fetchDashboard({ force: true });
    }
}

async function exportReport() {
    const response = await fetch("/api/report/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_filter: currentIncidentFilter })
    });

    const payload = await response.json().catch(() => ({ status: "error", path: "" }));
    if (!response.ok || payload.status !== "ok") {
        window.alert("Unable to export the monitoring report.");
        return;
    }

    window.alert(`Report exported to:\n${payload.path}`);
}

window.addEventListener("DOMContentLoaded", async () => {
    cpuChart = createChart(document.getElementById("cpu-chart"), "CPU Usage %", "#22d3ee");
    memoryChart = createChart(document.getElementById("memory-chart"), "Memory Usage %", "#5eead4");

    [
        ".incident-panel",
        ".intelligence-panel",
        ".suspect-panel",
        ".incident-history-panel",
        "#alerts-list",
        "#recommendations-list"
    ].forEach((selector) => {
        const element = document.querySelector(selector);
        if (!element) {
            return;
        }

        element.addEventListener("mouseenter", () => {
            setPanelLockState(true);
        });
        element.addEventListener("mouseleave", () => {
            setPanelLockState(false);
        });
    });

    document.getElementById("toggle-live-button").addEventListener("click", toggleLiveUpdates);
    document.getElementById("export-report-button").addEventListener("click", exportReport);
    document.getElementById("mode-select").addEventListener("change", changeMode);
    document.getElementById("label-select").addEventListener("change", changeLabel);
    document.getElementById("incident-filter").addEventListener("change", changeIncidentFilter);
    document.getElementById("process-table-body").addEventListener("click", openProcessLocation);

    updateLiveUpdateUi();
    await fetchDashboard({ force: true });
    dashboardIntervalId = window.setInterval(() => {
        fetchDashboard();
    }, 5000);
});
