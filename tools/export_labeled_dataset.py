import argparse
import csv
import sqlite3
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "monitoring.db"
EXPORT_DIR = ROOT_DIR / "reports"
DEFAULT_EXPORT_PATH = EXPORT_DIR / "labeled_stability_dataset.csv"
UNLABELED_VALUE = "unlabeled"

FEATURE_COLUMNS = [
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
]
METADATA_COLUMNS = [
    "system_sample_id",
    "mode",
    "created_at",
]
TARGET_COLUMN = "collection_label"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export labeled numeric ML features for supervised stability classification."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_EXPORT_PATH,
        help="CSV output path.",
    )
    parser.add_argument(
        "--include-unlabeled",
        action="store_true",
        help="Include rows whose collection_label is unlabeled.",
    )
    parser.add_argument(
        "--features-only",
        action="store_true",
        help="Exclude metadata columns and export only numeric features plus target label.",
    )
    return parser.parse_args()


def _build_query(include_unlabeled):
    selected_columns = [*METADATA_COLUMNS, *FEATURE_COLUMNS, TARGET_COLUMN]
    query = f"""
        SELECT
            {", ".join(selected_columns)}
        FROM ml_feature_samples
    """

    if not include_unlabeled:
        query += """
        WHERE collection_label != ?
        """

    query += """
        ORDER BY created_at
    """
    params = () if include_unlabeled else (UNLABELED_VALUE,)
    return query, params


def _fetch_rows(include_unlabeled):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    query, params = _build_query(include_unlabeled)
    rows = connection.execute(query, params).fetchall()
    connection.close()
    return rows


def _fieldnames(features_only):
    if features_only:
        return [*FEATURE_COLUMNS, TARGET_COLUMN]
    return [*METADATA_COLUMNS, *FEATURE_COLUMNS, TARGET_COLUMN]


def _write_csv(rows, output_path, fieldnames):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fieldnames})


def _print_summary(rows, output_path, include_unlabeled):
    counts = Counter(row[TARGET_COLUMN] for row in rows)
    print(f"Exported rows: {len(rows)}")
    print(f"Output path: {output_path}")
    print(f"Included unlabeled: {'yes' if include_unlabeled else 'no'}")

    if not counts:
        print("No labeled rows found yet. Collect data with a non-unlabeled dashboard label first.")
        return

    print("Rows by label:")
    for label, count in sorted(counts.items()):
        print(f"- {label}: {count}")


def main():
    args = parse_args()
    rows = _fetch_rows(args.include_unlabeled)
    fieldnames = _fieldnames(args.features_only)
    _write_csv(rows, args.output, fieldnames)
    _print_summary(rows, args.output, args.include_unlabeled)


if __name__ == "__main__":
    main()
