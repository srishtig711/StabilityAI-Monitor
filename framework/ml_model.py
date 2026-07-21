import math
import pickle
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = BASE_DIR / "models" / "stability_model.pkl"

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

STABLE_LABELS = {"stable", "normal_work"}
CRITICAL_LABELS = {"critical"}


def _default_prediction(reason):
    return {
        "available": False,
        "predicted_class": "Not trained",
        "confidence": 0,
        "state": "Unavailable",
        "message": reason,
        "model_version": "",
    }


def _load_model():
    if not MODEL_PATH.exists():
        return None

    try:
        with MODEL_PATH.open("rb") as model_file:
            return pickle.load(model_file)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError):
        return None


def _feature_vector(row, feature_columns=None):
    columns = feature_columns or FEATURE_COLUMNS
    values = []
    for column in columns:
        try:
            values.append(float(row[column]))
        except (KeyError, TypeError, ValueError):
            values.append(0.0)
    return values


def _standardize(values, means, stddevs):
    return [
        (value - means[index]) / (stddevs[index] or 1.0)
        for index, value in enumerate(values)
    ]


def _euclidean_distance(left, right):
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(len(left))))


def _label_to_state(label):
    if label in CRITICAL_LABELS:
        return "Critical"
    if label in STABLE_LABELS:
        return "Stable"
    return "Watchlist"


def _compare_with_rule(rule_state, ml_state):
    if not rule_state or ml_state == "Unavailable":
        return "Waiting for both rule-based and ML states."
    if str(rule_state).lower() == str(ml_state).lower():
        return "Rule-based and ML analysis agree."
    return f"Rule-based state is {rule_state}; ML state is {ml_state}."


def predict_from_feature_row(row, rule_state=None):
    model = _load_model()
    if not model:
        return _default_prediction("No trained ML model found. Train after collecting labeled sessions.")
    if row is None:
        return _default_prediction("No latest ML feature sample is available for prediction.")

    feature_columns = model.get("feature_columns", FEATURE_COLUMNS)
    centroids = model.get("centroids", {})
    if not centroids:
        return _default_prediction("The saved ML model has no class centroids.")

    vector = _standardize(
        _feature_vector(row, feature_columns),
        model.get("means", [0.0] * len(feature_columns)),
        model.get("stddevs", [1.0] * len(feature_columns)),
    )
    distances = {
        label: _euclidean_distance(vector, centroid)
        for label, centroid in centroids.items()
    }
    predicted_label = min(distances, key=distances.get)
    inverse_distances = {
        label: 1 / (distance + 0.000001)
        for label, distance in distances.items()
    }
    total_inverse = sum(inverse_distances.values()) or 1
    confidence = round((inverse_distances[predicted_label] / total_inverse) * 100, 2)
    ml_state = _label_to_state(predicted_label)

    return {
        "available": True,
        "predicted_class": predicted_label,
        "confidence": confidence,
        "state": ml_state,
        "message": _compare_with_rule(rule_state, ml_state),
        "model_version": model.get("version", ""),
    }
