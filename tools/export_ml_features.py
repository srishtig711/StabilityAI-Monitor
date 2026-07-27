import csv
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "monitoring.db"
EXPORT_DIR = ROOT_DIR / "reports"
EXPORT_PATH = EXPORT_DIR / "ml_feature_samples.csv"


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT
            mode,
            collection_label,
            created_at,
            cpu_percent,
            memory_percent,
            total_processes,
            high_cpu_processes,
            high_memory_processes,
            monitor_cpu_percent,
            monitor_memory_percent,
            sampled_process_count,
            avg_process_cpu,
            max_process_cpu,
            avg_process_memory,
            max_process_memory,
            cpu_delta,
            memory_delta,
            cpu_rolling_avg_3,
            memory_rolling_avg_3,
            cpu_rolling_gap_3,
            memory_rolling_gap_3
        FROM ml_feature_samples
        ORDER BY created_at
        """
    ).fetchall()
    connection.close()

    fieldnames = rows[0].keys() if rows else [
        "mode",
        "collection_label",
        "created_at",
        "cpu_percent",
        "memory_percent",
        "total_processes",
        "high_cpu_processes",
        "high_memory_processes",
        "monitor_cpu_percent",
        "monitor_memory_percent",
        "sampled_process_count",
        "avg_process_cpu",
        "max_process_cpu",
        "avg_process_memory",
        "max_process_memory",
        "cpu_delta",
        "memory_delta",
        "cpu_rolling_avg_3",
        "memory_rolling_avg_3",
        "cpu_rolling_gap_3",
        "memory_rolling_gap_3",
    ]

    with EXPORT_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)

    print(EXPORT_PATH)


if __name__ == "__main__":
    main()
