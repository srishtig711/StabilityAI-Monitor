import argparse
import math
import pickle
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "monitoring.db"
MODEL_PATH = ROOT_DIR / "models" / "stability_model.pkl"
REPORT_PATH = ROOT_DIR / "reports" / "ml_evaluation_report.md"
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train the supervised stability classifier from labeled ML feature samples."
    )
    parser.add_argument("--min-samples", type=int, default=20, help="Minimum labeled rows required.")
    parser.add_argument("--min-labels", type=int, default=2, help="Minimum distinct labels required.")
    parser.add_argument("--model-path", type=Path, default=MODEL_PATH, help="Output model path.")
    parser.add_argument("--report-path", type=Path, default=REPORT_PATH, help="Evaluation report path.")
    return parser.parse_args()


def _fetch_training_rows():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        f"""
        SELECT
            {", ".join(FEATURE_COLUMNS)},
            collection_label
        FROM ml_feature_samples
        WHERE collection_label != ?
        ORDER BY created_at
        """,
        (UNLABELED_VALUE,),
    ).fetchall()
    connection.close()
    return rows


def _row_to_vector(row):
    return [float(row[column] or 0) for column in FEATURE_COLUMNS]


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _stddev(values, center):
    if len(values) < 2:
        return 1.0

    variance = sum((value - center) ** 2 for value in values) / len(values)
    stddev = math.sqrt(variance)
    return stddev or 1.0


def _scale_vectors(vectors):
    columns = list(zip(*vectors))
    means = [_mean(list(column)) for column in columns]
    stddevs = [_stddev(list(column), means[index]) for index, column in enumerate(columns)]
    scaled = [
        [
            (value - means[index]) / stddevs[index]
            for index, value in enumerate(vector)
        ]
        for vector in vectors
    ]
    return scaled, means, stddevs


def _build_centroids(vectors, labels):
    grouped = defaultdict(list)
    for vector, label in zip(vectors, labels):
        grouped[label].append(vector)

    centroids = {}
    for label, label_vectors in grouped.items():
        centroids[label] = [
            _mean([vector[index] for vector in label_vectors])
            for index in range(len(FEATURE_COLUMNS))
        ]
    return centroids


def _distance(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(len(left))))


def _predict_label(vector, centroids):
    return min(centroids, key=lambda label: _distance(vector, centroids[label]))


def _evaluate(vectors, labels, centroids):
    predictions = [_predict_label(vector, centroids) for vector in vectors]
    correct = sum(1 for expected, predicted in zip(labels, predictions) if expected == predicted)
    matrix = defaultdict(Counter)
    for expected, predicted in zip(labels, predictions):
        matrix[expected][predicted] += 1
    return {
        "accuracy": round((correct / len(labels)) * 100, 2) if labels else 0,
        "total": len(labels),
        "correct": correct,
        "matrix": matrix,
    }


def _write_report(report_path, model, evaluation):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    labels = sorted(model["label_counts"])
    matrix_lines = []
    for expected in labels:
        cells = [str(evaluation["matrix"][expected][predicted]) for predicted in labels]
        matrix_lines.append(f"| {expected} | {' | '.join(cells)} |")

    report = f"""# ML Evaluation Report

Generated at: {model['created_at']}
Model type: Standard-scaled nearest-centroid classifier
Training samples: {model['training_samples']}
Labels: {', '.join(labels)}
Training accuracy: {evaluation['accuracy']}% ({evaluation['correct']}/{evaluation['total']})

## Label Counts

{chr(10).join(f'- {label}: {count}' for label, count in sorted(model['label_counts'].items()))}

## Confusion Matrix

| Expected | {' | '.join(labels)} |
| --- | {' | '.join('---' for _ in labels)} |
{chr(10).join(matrix_lines)}

## Feature Columns

{chr(10).join(f'- {column}' for column in FEATURE_COLUMNS)}
"""
    report_path.write_text(report, encoding="utf-8")


def main():
    args = parse_args()
    rows = _fetch_training_rows()
    labels = [row["collection_label"] for row in rows]
    label_counts = Counter(labels)

    if len(rows) < args.min_samples:
        raise SystemExit(f"Need at least {args.min_samples} labeled samples; found {len(rows)}.")
    if len(label_counts) < args.min_labels:
        raise SystemExit(f"Need at least {args.min_labels} labels; found {len(label_counts)}.")

    vectors = [_row_to_vector(row) for row in rows]
    scaled_vectors, means, stddevs = _scale_vectors(vectors)
    centroids = _build_centroids(scaled_vectors, labels)
    evaluation = _evaluate(scaled_vectors, labels, centroids)

    model = {
        "version": "nearest-centroid-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "feature_columns": FEATURE_COLUMNS,
        "means": means,
        "stddevs": stddevs,
        "centroids": centroids,
        "label_counts": dict(label_counts),
        "training_samples": len(rows),
        "evaluation": {
            "accuracy": evaluation["accuracy"],
            "total": evaluation["total"],
            "correct": evaluation["correct"],
        },
    }

    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    with args.model_path.open("wb") as model_file:
        pickle.dump(model, model_file)

    _write_report(args.report_path, model, evaluation)
    print(f"Model saved to: {args.model_path}")
    print(f"Evaluation report saved to: {args.report_path}")
    print(f"Training accuracy: {evaluation['accuracy']}%")


if __name__ == "__main__":
    main()
