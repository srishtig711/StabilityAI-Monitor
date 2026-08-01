import argparse
import math
import pickle
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
    from sklearn.model_selection import train_test_split

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


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


def _split_indices_chronological(labels, test_ratio):
    grouped = defaultdict(list)
    for index, label in enumerate(labels):
        grouped[label].append(index)

    train_indices = []
    test_indices = []
    normalized_ratio = min(max(test_ratio, 0.0), 0.5)

    for label_indices in grouped.values():
        test_count = max(1, round(len(label_indices) * normalized_ratio))
        test_count = min(test_count, len(label_indices) - 2) if len(label_indices) >= 4 else 0
        if test_count <= 0:
            train_indices.extend(label_indices)
            continue
        train_indices.extend(label_indices[:-test_count])
        test_indices.extend(label_indices[-test_count:])

    return train_indices, test_indices


def _sklearn_matrix(labels, expected, predicted):
    matrix_values = confusion_matrix(expected, predicted, labels=labels)
    matrix = defaultdict(Counter)
    for row_index, expected_label in enumerate(labels):
        for column_index, predicted_label in enumerate(labels):
            matrix[expected_label][predicted_label] = int(matrix_values[row_index][column_index])
    return matrix


def _sklearn_metric_rows(labels, expected, predicted):
    precision, recall, f1, _ = precision_recall_fscore_support(
        expected,
        predicted,
        labels=labels,
        zero_division=0,
    )
    return {
        label: {
            "precision": round(float(precision[index]) * 100, 2),
            "recall": round(float(recall[index]) * 100, 2),
            "f1": round(float(f1[index]) * 100, 2),
        }
        for index, label in enumerate(labels)
    }


def _evaluate_sklearn_model(model, vectors, labels, test_indices, evaluation_type):
    expected = [labels[index] for index in test_indices]
    predicted = model.predict([vectors[index] for index in test_indices])
    sorted_labels = sorted(set(labels))
    correct = int(sum(1 for left, right in zip(expected, predicted) if left == right))
    return {
        "type": evaluation_type,
        "accuracy": round(float(accuracy_score(expected, predicted)) * 100, 2) if expected else 0,
        "total": len(expected),
        "correct": correct,
        "matrix": _sklearn_matrix(sorted_labels, expected, predicted),
        "metrics": _sklearn_metric_rows(sorted_labels, expected, predicted),
    }


def _average_random_stratified_score(model_factory, vectors, labels, test_ratio, repeats=10):
    scores = []
    normalized_ratio = min(max(test_ratio, 0.05), 0.5)
    indices = list(range(len(labels)))

    for seed in range(repeats):
        train_indices, test_indices = train_test_split(
            indices,
            test_size=normalized_ratio,
            random_state=seed,
            stratify=labels,
        )
        model = model_factory()
        model.fit([vectors[index] for index in train_indices], [labels[index] for index in train_indices])
        predicted = model.predict([vectors[index] for index in test_indices])
        expected = [labels[index] for index in test_indices]
        scores.append(float(accuracy_score(expected, predicted)) * 100)

    return {
        "type": f"random_stratified_{repeats}x",
        "accuracy": round(sum(scores) / len(scores), 2),
        "min_accuracy": round(min(scores), 2),
        "max_accuracy": round(max(scores), 2),
        "repeats": repeats,
    }


def _sklearn_model_factories():
    return {
        "Gradient Boosting": lambda: GradientBoostingClassifier(random_state=42),
        "Random Forest": lambda: RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            class_weight="balanced",
            min_samples_leaf=2,
        ),
        "Extra Trees": lambda: ExtraTreesClassifier(
            n_estimators=400,
            random_state=42,
            class_weight="balanced",
            min_samples_leaf=1,
        ),
    }


def _train_sklearn_model(rows, test_ratio):
    vectors = [_row_to_vector(row) for row in rows]
    labels = [row["collection_label"] for row in rows]
    train_indices, test_indices = _split_indices_chronological(labels, test_ratio)
    factories = _sklearn_model_factories()
    comparison = []
    trained_for_comparison = {}

    for name, factory in factories.items():
        model = factory()
        model.fit([vectors[index] for index in train_indices], [labels[index] for index in train_indices])
        chronological = _evaluate_sklearn_model(model, vectors, labels, test_indices, "chronological_holdout")
        random_score = _average_random_stratified_score(factory, vectors, labels, test_ratio)
        comparison.append(
            {
                "name": name,
                "chronological_accuracy": chronological["accuracy"],
                "random_accuracy": random_score["accuracy"],
                "random_min_accuracy": random_score["min_accuracy"],
                "random_max_accuracy": random_score["max_accuracy"],
            }
        )
        trained_for_comparison[name] = (model, chronological, random_score)

    best_name = max(
        comparison,
        key=lambda item: (item["chronological_accuracy"], item["random_accuracy"]),
    )["name"]
    final_model = factories[best_name]()
    final_model.fit(vectors, labels)
    selected_model, chronological_evaluation, random_evaluation = trained_for_comparison[best_name]

    return {
        "version": "sklearn-gradient-boosting-v1" if best_name == "Gradient Boosting" else f"sklearn-{best_name.lower().replace(' ', '-')}-v1",
        "classifier": best_name,
        "estimator": final_model,
        "evaluation": chronological_evaluation,
        "random_evaluation": random_evaluation,
        "comparison": comparison,
    }


def _write_report(report_path, model, evaluation):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    labels = sorted(model["label_counts"])
    metrics = evaluation.get("metrics") or _build_classification_metrics(labels, evaluation)
    matrix_lines = []
    for expected in labels:
        cells = [str(evaluation["matrix"][expected][predicted]) for predicted in labels]
        matrix_lines.append(f"| {expected} | {' | '.join(cells)} |")

    report = f"""# ML Evaluation Report

Generated at: {model['created_at']}
Model type: Standard-scaled supervised classifier
Classifier: {model['classifier']}
Training samples: {model['training_samples']}
Labels: {', '.join(labels)}
Evaluation type: {evaluation['type']}
Evaluation samples: {evaluation['total']}
Evaluation accuracy: {evaluation['accuracy']}% ({evaluation['correct']}/{evaluation['total']})
Random stratified accuracy: {model.get('random_evaluation', {}).get('accuracy', 'n/a')}%

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

## Model Comparison

| Model | Chronological Holdout % | Random Stratified Avg % | Random Min % | Random Max % |
| --- | --- | --- | --- | --- |
{chr(10).join(f"| {item['name']} | {item['chronological_accuracy']} | {item['random_accuracy']} | {item['random_min_accuracy']} | {item['random_max_accuracy']} |" for item in model.get('comparison', []))}

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

    if SKLEARN_AVAILABLE:
        sklearn_result = _train_sklearn_model(rows, args.test_ratio)
        evaluation = sklearn_result["evaluation"]
        random_evaluation = sklearn_result["random_evaluation"]
        comparison = sklearn_result["comparison"]
        classifier = sklearn_result["classifier"]
    else:
        trained = _train_classifier(rows)
        evaluation = _evaluate_model(rows, args.test_ratio, args.neighbors)
        random_evaluation = {}
        comparison = []
        classifier = "Weighted k-nearest-neighbor"

    model = {
        "version": sklearn_result["version"] if SKLEARN_AVAILABLE else "weighted-knn-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "feature_columns": FEATURE_COLUMNS,
        "classifier": classifier,
        "label_counts": dict(label_counts),
        "training_samples": len(rows),
        "random_evaluation": random_evaluation,
        "comparison": comparison,
        "evaluation": {
            "accuracy": evaluation["accuracy"],
            "total": evaluation["total"],
            "correct": evaluation["correct"],
            "type": evaluation["type"],
        },
    }
    if SKLEARN_AVAILABLE:
        model["estimator"] = sklearn_result["estimator"]
    else:
        model["means"] = trained["means"]
        model["stddevs"] = trained["stddevs"]
        model["scaled_vectors"] = trained["scaled_vectors"]
        model["labels"] = trained["labels"]
        model["neighbors"] = args.neighbors

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
