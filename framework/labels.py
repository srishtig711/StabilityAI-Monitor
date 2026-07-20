from threading import Lock

from framework.database import get_connection


LABEL_DETAILS = {
    "unlabeled": {
        "label": "Unlabeled",
        "description": "Collected without a confirmed training label.",
    },
    "stable": {
        "label": "Stable",
        "description": "Quiet, healthy system behavior.",
    },
    "normal_work": {
        "label": "Normal Work",
        "description": "Real usage such as browsing, editing, coding, or light multitasking.",
    },
    "cpu_stress": {
        "label": "CPU Stress",
        "description": "Controlled or real workload where CPU pressure is expected.",
    },
    "memory_pressure": {
        "label": "Memory Pressure",
        "description": "Controlled or real workload where memory pressure is expected.",
    },
    "spike": {
        "label": "Spike",
        "description": "Short sudden resource bursts.",
    },
    "heavy_multitasking": {
        "label": "Heavy Multitasking",
        "description": "Many active apps or workloads running together.",
    },
    "critical": {
        "label": "Critical",
        "description": "Severe instability or near-failure behavior.",
    },
}

DEFAULT_COLLECTION_LABEL = "unlabeled"
_label_lock = Lock()


def _normalize_label(label):
    normalized = str(label or DEFAULT_COLLECTION_LABEL).strip().lower()
    if normalized not in LABEL_DETAILS:
        raise ValueError(f"Unsupported collection label: {label}")
    return normalized


def get_current_label():
    with _label_lock:
        try:
            connection = get_connection()
            row = connection.execute(
                "SELECT value FROM collection_state WHERE key = 'current_label'"
            ).fetchone()
            connection.close()
        except Exception:
            return DEFAULT_COLLECTION_LABEL

    if not row:
        return DEFAULT_COLLECTION_LABEL

    try:
        return _normalize_label(row["value"])
    except ValueError:
        return DEFAULT_COLLECTION_LABEL


def set_current_label(label):
    selected_label = _normalize_label(label)

    with _label_lock:
        connection = get_connection()
        connection.execute(
            """
            INSERT INTO collection_state (key, value)
            VALUES ('current_label', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (selected_label,),
        )
        connection.commit()
        connection.close()

    return get_label_details(selected_label)


def get_label_details(label=None):
    selected_label = _normalize_label(label or get_current_label())
    return {"key": selected_label, **LABEL_DETAILS[selected_label]}


def list_labels():
    return [{"key": key, **details} for key, details in LABEL_DETAILS.items()]
