import os
from datetime import datetime
from pathlib import Path

import psutil

from framework.database import insert_snapshot
from framework.labels import get_current_label
from framework.modes import get_current_mode
from framework.simulator import simulator


HIGH_CPU_THRESHOLD = 60
HIGH_MEMORY_THRESHOLD = 15
TOP_PROCESS_LIMIT = 10
IGNORED_PROCESS_NAMES = {
    "idle",
    "system idle process",
    "system_idle",
}
MONITOR_ENTRYPOINTS = {
    "app.py",
    "run.bat",
}


def _safe_process_name(process_info):
    return process_info.get("name") or "Unknown"


def _build_process_identity(process_info):
    name = _safe_process_name(process_info)
    exe_path = process_info.get("exe") or ""
    cmdline = process_info.get("cmdline") or []

    executable_label = Path(exe_path).name if exe_path else name
    display_name = executable_label or name

    if cmdline:
        details = " ".join(str(part) for part in cmdline[:4]).strip()
    elif exe_path:
        details = exe_path
    else:
        details = name

    return display_name, details[:160], exe_path


def _is_monitor_process(process_info):
    raw_name = (_safe_process_name(process_info) or "").strip().lower()
    pid = int(process_info.get("pid") or -1)
    cmdline_parts = [str(part).lower() for part in (process_info.get("cmdline") or [])]
    normalized_cmdline = " ".join(cmdline_parts).replace("\\", "/")

    if pid == os.getpid():
        return True

    if "python" not in raw_name and "flask" not in raw_name:
        return False

    return any(entrypoint in normalized_cmdline for entrypoint in MONITOR_ENTRYPOINTS)


def _should_ignore_process(process_info, display_name):
    raw_name = (_safe_process_name(process_info) or "").strip().lower()
    normalized_display_name = (display_name or "").strip().lower()
    pid = int(process_info.get("pid") or -1)

    return (
        raw_name in IGNORED_PROCESS_NAMES
        or normalized_display_name in IGNORED_PROCESS_NAMES
        or (pid == 0 and ("idle" in raw_name or "idle" in normalized_display_name))
        or _is_monitor_process(process_info)
    )


def _collect_monitor_overhead():
    cpu_total = 0.0
    memory_total = 0.0

    try:
        root_process = psutil.Process(os.getpid())
        monitor_processes = [root_process] + root_process.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {"cpu_percent": 0.0, "memory_percent": 0.0}

    for process in monitor_processes:
        try:
            cpu_total += float(process.cpu_percent(interval=None) or 0.0)
            memory_total += float(process.memory_percent() or 0.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return {
        "cpu_percent": round(cpu_total, 2),
        "memory_percent": round(memory_total, 2),
    }


def snapshot_system():
    mode = get_current_mode()
    collection_label = get_current_label()

    if mode != "live":
        snapshot = simulator.generate_snapshot(mode)
        snapshot["collection_label"] = collection_label
        insert_snapshot(snapshot)
        return snapshot

    monitor_overhead = _collect_monitor_overhead()
    process_entries = []
    high_cpu_processes = 0
    high_memory_processes = 0

    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent

    for process in psutil.process_iter(
        ["pid", "name", "exe", "cmdline", "cpu_percent", "memory_percent", "create_time", "status"]
    ):
        try:
            info = process.info
            cpu = float(info.get("cpu_percent") or 0.0)
            memory = float(info.get("memory_percent") or 0.0)
            runtime = max(0.0, datetime.now().timestamp() - float(info.get("create_time") or datetime.now().timestamp()))
            display_name, details, exe_path = _build_process_identity(info)

            if _should_ignore_process(info, display_name):
                continue

            if cpu >= HIGH_CPU_THRESHOLD:
                high_cpu_processes += 1
            if memory >= HIGH_MEMORY_THRESHOLD:
                high_memory_processes += 1

            process_entries.append(
                {
                    "pid": int(info["pid"]),
                    "name": _safe_process_name(info),
                    "display_name": display_name,
                    "details": details,
                    "executable_path": exe_path,
                    "cpu_percent": round(cpu, 2),
                    "memory_percent": round(memory, 2),
                    "runtime_seconds": round(runtime, 2),
                    "status": info.get("status") or "unknown",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, TypeError):
            continue

    top_processes = sorted(
        process_entries,
        key=lambda item: (item["cpu_percent"], item["memory_percent"]),
        reverse=True,
    )[:TOP_PROCESS_LIMIT]

    snapshot = {
        "mode": mode,
        "collection_label": collection_label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "cpu_percent": round(cpu_percent, 2),
        "memory_percent": round(memory_percent, 2),
        "total_processes": len(process_entries),
        "high_cpu_processes": high_cpu_processes,
        "high_memory_processes": high_memory_processes,
        "monitor_cpu_percent": monitor_overhead["cpu_percent"],
        "monitor_memory_percent": monitor_overhead["memory_percent"],
        "top_processes": top_processes,
    }

    insert_snapshot(snapshot)
    return snapshot
