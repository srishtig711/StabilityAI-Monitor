from threading import Lock

from framework.simulator import simulator


MODE_DETAILS = {
    "live": {
        "label": "Live System",
        "description": "Uses real CPU and memory values from the current computer.",
        "kind": "live",
    },
    "demo_normal": {
        "label": "Demo: Normal",
        "description": "Simulates a stable computer with minor natural fluctuations.",
        "kind": "demo",
    },
    "demo_cpu_stress": {
        "label": "Demo: CPU Stress",
        "description": "Simulates sustained high CPU usage with periodic spikes.",
        "kind": "demo",
    },
    "demo_memory_leak": {
        "label": "Demo: Memory Leak",
        "description": "Simulates memory consumption that keeps increasing over time.",
        "kind": "demo",
    },
    "demo_spike": {
        "label": "Demo: Sudden Spikes",
        "description": "Simulates a mostly stable system with abrupt abnormal spikes.",
        "kind": "demo",
    },
    "demo_critical": {
        "label": "Demo: Critical Instability",
        "description": "Simulates severe instability with high CPU and memory pressure.",
        "kind": "demo",
    },
}


_current_mode = "live"
_mode_lock = Lock()


def get_current_mode():
    with _mode_lock:
        return _current_mode


def set_current_mode(mode):
    if mode not in MODE_DETAILS:
        raise ValueError(f"Unsupported mode: {mode}")

    global _current_mode
    with _mode_lock:
        _current_mode = mode
        simulator.reset(mode)
        return MODE_DETAILS[mode]


def get_mode_details(mode=None):
    selected_mode = mode or get_current_mode()
    return {"key": selected_mode, **MODE_DETAILS[selected_mode]}


def list_modes():
    return [{"key": key, **details} for key, details in MODE_DETAILS.items()]
