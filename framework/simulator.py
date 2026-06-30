import math
import random
from datetime import datetime


HIGH_CPU_THRESHOLD = 70
HIGH_MEMORY_THRESHOLD = 20


class ScenarioSimulator:
    def __init__(self):
        self._states = {}

    def reset(self, mode):
        self._states.pop(mode, None)

    def generate_snapshot(self, mode):
        state = self._states.setdefault(mode, self._build_initial_state(mode))
        state["step"] += 1

        if mode == "demo_normal":
            cpu = self._clamp(26 + math.sin(state["step"] / 2) * 6 + self._jitter(-4, 4), 10, 45)
            memory = self._clamp(42 + math.sin(state["step"] / 3) * 4 + self._jitter(-2, 2), 30, 58)
        elif mode == "demo_cpu_stress":
            cpu = self._clamp(76 + math.sin(state["step"] / 2) * 9 + self._jitter(-4, 5), 60, 96)
            if state["step"] % 4 == 0:
                cpu = self._clamp(cpu + self._jitter(8, 14), 60, 98)
            memory = self._clamp(52 + math.sin(state["step"] / 4) * 5 + self._jitter(-2, 3), 42, 66)
        elif mode == "demo_memory_leak":
            state["memory_level"] = self._clamp(state["memory_level"] + self._jitter(1.2, 2.8), 45, 97)
            cpu = self._clamp(34 + math.sin(state["step"] / 2) * 5 + self._jitter(-3, 4), 20, 52)
            memory = state["memory_level"]
        elif mode == "demo_spike":
            cpu = self._clamp(32 + math.sin(state["step"] / 2) * 7 + self._jitter(-5, 5), 15, 55)
            memory = self._clamp(44 + math.sin(state["step"] / 3) * 5 + self._jitter(-3, 3), 32, 62)
            if state["step"] % 5 == 0:
                cpu = self._clamp(cpu + self._jitter(28, 42), 20, 95)
            if state["step"] % 7 == 0:
                memory = self._clamp(memory + self._jitter(16, 24), 35, 92)
        elif mode == "demo_critical":
            cpu = self._clamp(88 + math.sin(state["step"] / 1.8) * 5 + self._jitter(-3, 4), 78, 99)
            state["memory_level"] = self._clamp(state["memory_level"] + self._jitter(0.8, 2.4), 82, 98)
            memory = state["memory_level"]
            if state["step"] % 3 == 0:
                cpu = self._clamp(cpu + self._jitter(2, 6), 80, 99)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        processes = self._build_processes(mode, state["step"], cpu, memory)
        high_cpu_processes = sum(1 for process in processes if process["cpu_percent"] >= HIGH_CPU_THRESHOLD)
        high_memory_processes = sum(1 for process in processes if process["memory_percent"] >= HIGH_MEMORY_THRESHOLD)

        return {
            "mode": mode,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "cpu_percent": round(cpu, 2),
            "memory_percent": round(memory, 2),
            "total_processes": self._total_process_count(mode, state["step"]),
            "high_cpu_processes": high_cpu_processes,
            "high_memory_processes": high_memory_processes,
            "top_processes": processes,
        }

    def _build_initial_state(self, mode):
        if mode in {"demo_memory_leak", "demo_critical"}:
            memory_level = 48 if mode == "demo_memory_leak" else 84
        else:
            memory_level = 42

        return {"step": 0, "memory_level": memory_level}

    def _build_processes(self, mode, step, cpu, memory):
        names = {
            "demo_normal": ["browser", "editor", "terminal", "sync_service", "cloud_backup"],
            "demo_cpu_stress": ["render_engine", "analysis_worker", "browser", "terminal", "system_service"],
            "demo_memory_leak": ["data_cache", "browser", "notebook_kernel", "service_host", "editor"],
            "demo_spike": ["backup_task", "browser", "update_service", "terminal", "editor"],
            "demo_critical": ["render_engine", "ml_worker", "database_cache", "browser", "system_service"],
        }[mode]

        process_values = []
        for index, name in enumerate(names, start=1):
            cpu_share = max(0.8, cpu * (0.32 - (index - 1) * 0.05) + self._jitter(-3, 4))
            memory_share = max(0.6, memory * (0.18 - (index - 1) * 0.025) + self._jitter(-1.5, 2.5))
            runtime = 240 + step * 5 + index * 33
            process_values.append(
                {
                    "pid": 4000 + index,
                    "name": name,
                    "display_name": name.replace("_", " ").title(),
                    "details": f"{name}.exe --scenario {mode} --worker {index}",
                    "executable_path": "",
                    "cpu_percent": round(self._clamp(cpu_share, 0, 95), 2),
                    "memory_percent": round(self._clamp(memory_share, 0, 75), 2),
                    "runtime_seconds": round(runtime, 2),
                    "status": "running",
                }
            )

        return sorted(
            process_values,
            key=lambda item: (item["cpu_percent"], item["memory_percent"]),
            reverse=True,
        )

    def _total_process_count(self, mode, step):
        base = {
            "demo_normal": 112,
            "demo_cpu_stress": 129,
            "demo_memory_leak": 118,
            "demo_spike": 121,
            "demo_critical": 137,
        }[mode]
        return int(base + math.sin(step / 3) * 2)

    @staticmethod
    def _jitter(start, end):
        return random.uniform(start, end)

    @staticmethod
    def _clamp(value, minimum, maximum):
        return max(minimum, min(maximum, value))


simulator = ScenarioSimulator()
