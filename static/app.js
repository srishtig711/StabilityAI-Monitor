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
let currentDashboardView = "monitoring";
const developerMode = new URLSearchParams(window.location.search).get("developer") === "1";

function createChart(context, label, color) {
    if (typeof Chart === "undefined") {
        const canvas = context;
        const drawingContext = canvas.getContext("2d");
        const fallbackChart = {
            data: {
                labels: [],
                datasets: [{ label, data: [] }]
            },
            update() {
                const parent = canvas.parentElement;
                const width = parent ? parent.clientWidth : 640;
                const height = parent ? parent.clientHeight : 280;
                const pixelRatio = window.devicePixelRatio || 1;
                canvas.width = Math.max(width, 320) * pixelRatio;
                canvas.height = Math.max(height, 240) * pixelRatio;
                canvas.style.width = `${Math.max(width, 320)}px`;
                canvas.style.height = `${Math.max(height, 240)}px`;
                drawingContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
                const chartWidth = canvas.width / pixelRatio;
                const chartHeight = canvas.height / pixelRatio;
                drawingContext.clearRect(0, 0, chartWidth, chartHeight);
                drawingContext.fillStyle = "#9fb0c7";
                drawingContext.font = "600 13px Segoe UI, Arial";
                drawingContext.fillText(label, 14, 24);

                const values = this.data.datasets[0].data;
                if (!values.length) {
                    drawingContext.font = "13px Segoe UI, Arial";
                    drawingContext.fillText("Waiting for monitoring samples...", 14, 52);
                    return;
                }

                const plot = { left: 48, right: 18, top: 42, bottom: 34 };
                const plotWidth = chartWidth - plot.left - plot.right;
                const plotHeight = chartHeight - plot.top - plot.bottom;
                const yForValue = (value) => chartHeight - plot.bottom - (plotHeight * Math.min(Math.max(value, 0), 100)) / 100;

                drawingContext.font = "12px Segoe UI, Arial";
                drawingContext.lineWidth = 1;
                for (let tick = 0; tick <= 100; tick += 25) {
                    const y = yForValue(tick);
                    drawingContext.strokeStyle = "rgba(148, 163, 184, 0.18)";
                    drawingContext.beginPath();
                    drawingContext.moveTo(plot.left, y);
                    drawingContext.lineTo(chartWidth - plot.right, y);
                    drawingContext.stroke();
                    drawingContext.fillStyle = "#9fb0c7";
                    drawingContext.fillText(`${tick}%`, 8, y + 4);
                }

                drawingContext.strokeStyle = "rgba(148, 163, 184, 0.45)";
                drawingContext.beginPath();
                drawingContext.moveTo(plot.left, plot.top);
                drawingContext.lineTo(plot.left, chartHeight - plot.bottom);
                drawingContext.lineTo(chartWidth - plot.right, chartHeight - plot.bottom);
                drawingContext.stroke();

                drawingContext.strokeStyle = color;
                drawingContext.lineWidth = 2.5;
                drawingContext.beginPath();
                values.forEach((value, index) => {
                    const x = plot.left + (plotWidth * index) / Math.max(values.length - 1, 1);
                    const y = yForValue(value);
                    if (index === 0) {
                        drawingContext.moveTo(x, y);
                    } else {
                        drawingContext.lineTo(x, y);
                    }
                });
                drawingContext.stroke();

                const labels = this.data.labels;
                const labelIndexes = [...new Set([0, Math.floor((labels.length - 1) / 2), labels.length - 1])];
                drawingContext.fillStyle = "#9fb0c7";
                drawingContext.font = "11px Segoe UI, Arial";
                labelIndexes.forEach((index) => {
                    const x = plot.left + (plotWidth * index) / Math.max(labels.length - 1, 1);
                    const labelText = String(labels[index] || "");
                    const textWidth = drawingContext.measureText(labelText).width;
                    drawingContext.fillText(labelText, x - textWidth / 2, chartHeight - 12);
                });
            }
        };

        return fallbackChart;
    }

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

function setDashboardView(view) {
    currentDashboardView = developerMode && view === "collection" ? "collection" : "monitoring";
    document.querySelectorAll(".monitoring-view-panel").forEach((panel) => {
        panel.classList.toggle("hidden", currentDashboardView !== "monitoring");
    });
    document.querySelectorAll(".collection-view-panel").forEach((panel) => {
        panel.classList.toggle("hidden", currentDashboardView !== "collection");
    });
    document.querySelectorAll(".view-switch-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.view === currentDashboardView);
    });
}

function configureDeveloperMode() {
    const collectionButton = document.getElementById("collection-view-button");
    collectionButton.classList.toggle("hidden", !developerMode);
    if (!developerMode) {
        setDashboardView("monitoring");
    }
}

function updateFinalDecision(decision) {
    const target = document.getElementById("final-stability-decision");
    const normalizedDecision = String(decision || "Stable").toLowerCase();
    target.textContent = decision || "Stable";
    target.className = `hero-risk-score ${normalizedDecision}`;
}

function renderMlFeatureSignals(signals) {
    const list = document.getElementById("ml-feature-signals");
    list.innerHTML = "";

    (signals || []).forEach((signal) => {
        const item = document.createElement("li");
        item.textContent = signal;
        list.appendChild(item);
    });
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

function renderLabelCounts(dataReadiness) {
    const list = document.getElementById("label-counts-list");
    list.innerHTML = "";

    (dataReadiness.labels || []).forEach((label) => {
        const li = document.createElement("li");
        li.textContent = `${label.label}: ${label.count}`;
        list.appendChild(li);
    });
}

function renderCollectionSessions(collectionSessions) {
    const current = collectionSessions.current || {};
    setText("session-active-label", current.label_name || "Unlabeled");
    setText("session-started-at", formatRefreshTime(current.started_at));

    const list = document.getElementById("session-history-list");
    list.innerHTML = "";

    const sessions = collectionSessions.recent || [];
    if (!sessions.length) {
        const li = document.createElement("li");
        li.className = "message-item low";
        li.innerHTML = `
            <strong>No collection sessions yet</strong>
            <p>Changing the collection label will create session history.</p>
        `;
        list.appendChild(li);
        return;
    }

    sessions.forEach((session) => {
        const li = document.createElement("li");
        li.className = "message-item low";
        const endedAt = session.ended_at ? formatRefreshTime(session.ended_at) : "active";
        li.innerHTML = `
            <strong>${session.label_name}</strong>
            <p>${formatRefreshTime(session.started_at)} to ${endedAt}</p>
        `;
        list.appendChild(li);
    });
}

async function fetchDashboard(options = {}) {
    const { force = false } = options;
    if (liveUpdatesPaused && !force) {
        return;
    }

    try {
        const response = await fetch(`/api/dashboard?incident_filter=${encodeURIComponent(currentIncidentFilter)}&_=${Date.now()}`);
        if (!response.ok) {
            throw new Error(`Dashboard request failed with status ${response.status}`);
        }
        const payload = await response.json();
        if (!payload.summary || !payload.monitoring_mode || !payload.collection_label) {
            throw new Error("Dashboard response is incomplete");
        }

    setText("cpu-usage", `${payload.summary.cpu_percent}%`);
    setText("memory-usage", `${payload.summary.memory_percent}%`);
    setText("process-count", payload.summary.total_processes);
    setText("health-classification", payload.summary.health_classification ?? "Stable");
    setText("anomaly-score", payload.summary.anomaly_score ?? 0);
    setText("high-cpu-processes", payload.summary.high_cpu_processes ?? 0);
    setText("high-memory-processes", payload.summary.high_memory_processes ?? 0);
    setText("monitor-cpu-overhead", `${payload.summary.monitor_cpu_percent ?? 0}%`);
    setText("monitor-memory-overhead", `${payload.summary.monitor_memory_percent ?? 0}%`);
    setText(
        "latest-sample-label",
        labelDisplayName(payload.summary.collection_label ?? "unlabeled", payload.collection_label?.available)
    );
    setText("risk-score", payload.summary.risk_score);
    setText("last-refresh-time", `Last refreshed: ${formatRefreshTime(payload.summary.latest_sample_time)}`);
    updateRiskLevel(payload.summary.risk_level);

    const mlPrediction = payload.ml_prediction || {};
    updateFinalDecision(mlPrediction.final_decision ?? "Rule-based fallback");
    setText("decision-source", mlPrediction.decision_source ?? "Rule-based fallback");
    setText("hero-ml-risk", mlPrediction.ml_risk ?? 0);
    setText("hero-ml-confidence", `${mlPrediction.confidence ?? 0}%`);

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
    setText("ml-final-decision", mlPrediction.final_decision ?? "Rule-based fallback");
    setText("ml-risk", mlPrediction.ml_risk ?? 0);
    setText("ml-predicted-class", mlPrediction.predicted_class ?? "Not trained");
    setText("ml-confidence", `${mlPrediction.confidence ?? 0}%`);
    setText("ml-decision-source", mlPrediction.decision_source ?? "-");
    setText("ml-model-version", mlPrediction.model_version || "-");
    setText("readiness-labeled-total", payload.data_readiness?.labeled_total ?? 0);
    setText("readiness-unlabeled-total", payload.data_readiness?.unlabeled_total ?? 0);
    setText(
        "readiness-distinct-labels",
        `${payload.data_readiness?.distinct_labeled ?? 0}/${payload.data_readiness?.min_training_labels ?? 2}`
    );
    setText("readiness-status", payload.data_readiness?.ready ? "Ready" : "Not ready");
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
        setText("ml-comparison", mlPrediction.agreement ?? mlPrediction.message ?? "");
        renderMlFeatureSignals(mlPrediction.feature_signals);
        setText("readiness-message", payload.data_readiness?.message ?? "");
        renderLabelCounts(payload.data_readiness ?? { labels: [] });
        renderCollectionSessions(payload.collection_sessions ?? { current: {}, recent: [] });
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
        if (!liveUpdatesPaused) {
            updateLiveUpdateUi();
        }
        return true;
    } catch (error) {
        const status = document.getElementById("live-update-status");
        if (status && !liveUpdatesPaused) {
            status.textContent = "Connecting to local monitor... retrying automatically";
            status.className = "live-update-status paused";
        }
        console.warn("Dashboard refresh failed; retrying automatically.", error);
        return false;
    }
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
    document.getElementById("monitoring-view-button").addEventListener("click", () => setDashboardView("monitoring"));
    document.getElementById("collection-view-button").addEventListener("click", () => setDashboardView("collection"));
    document.getElementById("mode-select").addEventListener("change", changeMode);
    document.getElementById("label-select").addEventListener("change", changeLabel);
    document.getElementById("incident-filter").addEventListener("change", changeIncidentFilter);
    document.getElementById("process-table-body").addEventListener("click", openProcessLocation);

    updateLiveUpdateUi();
    configureDeveloperMode();
    setDashboardView("monitoring");
    dashboardIntervalId = window.setInterval(() => {
        fetchDashboard();
    }, 5000);
    await fetchDashboard({ force: true });
});
