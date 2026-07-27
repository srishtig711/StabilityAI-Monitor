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
    "cpu_delta",
    "memory_delta",
    "cpu_rolling_avg_3",
    "memory_rolling_avg_3",
    "cpu_rolling_gap_3",
    "memory_rolling_gap_3",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train the supervised stability classifier from labeled ML feature samples."
    )
    parser.add_argument("--min-samples", type=int, default=20, help="Minimum labeled rows required.")
    parser.add_argument("--min-labels", type=int, default=2, help="Minimum distinct labels required.")
    parser.add_argument("--test-ratio", type=float, default=0.25, help="Per-label holdout ratio for evaluation.")
    parser.add_argument("--neighbors", type=int, default=1, help="Neighbors used by the weighted k-nearest-neighbor classifier.")
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
    return _apply_scaler(vectors, means, stddevs), means, stddevs


def _apply_scaler(vectors, means, stddevs):
    return [
        [
            (value - means[index]) / stddevs[index]
            for index, value in enumerate(vector)
        ]
        for vector in vectors
    ]


def _distance(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(len(left))))


def _predict_label(vector, trained, neighbors):
    distances = [
        (_distance(vector, trained_vector), label)
        for trained_vector, label in zip(trained["scaled_vectors"], trained["labels"])
    ]
    distances.sort(key=lambda item: item[0])
    nearest = distances[: max(1, min(neighbors, len(distances)))]
    votes = Counter()

    for distance, label in nearest:
        votes[label] += 1 / (distance + 0.000001)

    return votes.most_common(1)[0][0]


def _evaluate(vectors, labels, trained, neighbors):
    predictions = [_predict_label(vector, trained, neighbors) for vector in vectors]
    correct = sum(1 for expected, predicted in zip(labels, predictions) if expected == predicted)
    matrix = defaultdict(Counter)
    for expected, predicted in zip(labels, predictions):
        matrix[expected][predicted] += 1
    return {
        "accuracy": round((correct / len(labels)) * 100, 2) if labels else 0,
        "total": len(labels),
        "correct": correct,
        "matrix": matrix,
        "predictions": predictions,
    }


def _split_rows_by_label(rows, test_ratio):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["collection_label"]].append(row)

    train_rows = []
    test_rows = []
    normalized_ratio = min(max(test_ratio, 0.0), 0.5)

    for label, label_rows in grouped.items():
        if len(label_rows) < 4 or normalized_ratio <= 0:
            train_rows.extend(label_rows)
            continue

        test_count = max(1, round(len(label_rows) * normalized_ratio))
        test_count = min(test_count, len(label_rows) - 2)
        train_rows.extend(label_rows[:-test_count])
        test_rows.extend(label_rows[-test_count:])

    return train_rows, test_rows


def _train_classifier(rows):
    labels = [row["collection_label"] for row in rows]
    vectors = [_row_to_vector(row) for row in rows]
    scaled_vectors, means, stddevs = _scale_vectors(vectors)
    return {
        "labels": labels,
        "vectors": vectors,
        "scaled_vectors": scaled_vectors,
        "means": means,
        "stddevs": stddevs,
    }


def _evaluate_model(rows, test_ratio, neighbors):
    train_rows, test_rows = _split_rows_by_label(rows, test_ratio)
    evaluation_rows = test_rows
    evaluation_type = "holdout"

    if len(test_rows) < 2 or len({row["collection_label"] for row in test_rows}) < 2:
        train_rows = rows
        evaluation_rows = rows
        evaluation_type = "training"

    trained = _train_classifier(train_rows)
    evaluation_labels = [row["collection_label"] for row in evaluation_rows]
    evaluation_vectors = [_row_to_vector(row) for row in evaluation_rows]
    scaled_evaluation_vectors = _apply_scaler(
        evaluation_vectors,
        trained["means"],
        trained["stddevs"],
    )
    evaluation = _evaluate(scaled_evaluation_vectors, evaluation_labels, trained, neighbors)
    evaluation["type"] = evaluation_type
    evaluation["train_total"] = len(train_rows)
    return evaluation


def _build_classification_metrics(labels, evaluation):
    metrics = {}
    matrix = evaluation["matrix"]

    for label in labels:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[other][label] for other in labels if other != label)
        false_negative = sum(matrix[label][other] for other in labels if other != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0
        metrics[label] = {
            "precision": round(precision * 100, 2),
            "recall": round(recall * 100, 2),
            "f1": round(f1 * 100, 2),
        }

    return metrics


def _write_report(report_path, model, evaluation):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    labels = sorted(model["label_counts"])
    metrics = _build_classification_metrics(labels, evaluation)
    matrix_lines = []
    for expected in labels:
        cells = [str(evaluation["matrix"][expected][predicted]) for predicted in labels]
        matrix_lines.append(f"| {expected} | {' | '.join(cells)} |")

    report = f"""# ML Evaluation Report

Generated at: {model['created_at']}
Model type: Standard-scaled supervised classifier
Classifier: Weighted k-nearest-neighbor
Training samples: {model['training_samples']}
Neighbors: {model['neighbors']}
Labels: {', '.join(labels)}
Evaluation type: {evaluation['type']}
Evaluation samples: {evaluation['total']}
Evaluation accuracy: {evaluation['accuracy']}% ({evaluation['correct']}/{evaluation['total']})

## Label Counts

{chr(10).join(f'- {label}: {count}' for label, count in sorted(model['label_counts'].items()))}

## Confusion Matrix

| Expected | {' | '.join(labels)} |
| --- | {' | '.join('---' for _ in labels)} |
{chr(10).join(matrix_lines)}

## Per-Class Metrics

| Label | Precision % | Recall % | F1 % |
| --- | --- | --- | --- |
{chr(10).join(f"| {label} | {metrics[label]['precision']} | {metrics[label]['recall']} | {metrics[label]['f1']} |" for label in labels)}

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

    trained = _train_classifier(rows)
    evaluation = _evaluate_model(rows, args.test_ratio, args.neighbors)

    model = {
        "version": "weighted-knn-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "feature_columns": FEATURE_COLUMNS,
        "means": trained["means"],
        "stddevs": trained["stddevs"],
        "scaled_vectors": trained["scaled_vectors"],
        "labels": trained["labels"],
        "neighbors": args.neighbors,
        "label_counts": dict(label_counts),
        "training_samples": len(rows),
        "evaluation": {
            "accuracy": evaluation["accuracy"],
            "total": evaluation["total"],
            "correct": evaluation["correct"],
            "type": evaluation["type"],
        },
    }

    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    with args.model_path.open("wb") as model_file:
        pickle.dump(model, model_file)

    _write_report(args.report_path, model, evaluation)
    print(f"Model saved to: {args.model_path}")
    print(f"Evaluation report saved to: {args.report_path}")
    print(f"Evaluation type: {evaluation['type']}")
    print(f"Evaluation accuracy: {evaluation['accuracy']}%")


if __name__ == "__main__":
    main()
