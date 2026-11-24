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
    "cpu_delta",
    "memory_delta",
    "cpu_rolling_avg_3",
    "memory_rolling_avg_3",
    "cpu_rolling_gap_3",
    "memory_rolling_gap_3",
]

STABLE_LABELS = {"stable", "normal_work"}
CRITICAL_LABELS = {"critical"}
CLASS_RISK_WEIGHTS = {
    "stable": 5,
    "normal_work": 15,
    "spike": 55,
    "cpu_stress": 75,
    "memory_pressure": 75,
    "heavy_multitasking": 85,
    "critical": 100,
}
LOW_CONFIDENCE_THRESHOLD = 55
_cached_model = None
_model_load_attempted = False


def _default_prediction(reason):
    return {
        "available": False,
        "predicted_class": "Not trained",
        "confidence": 0,
        "state": "Unavailable",
        "ml_risk": 0,
        "final_decision": "Rule-based fallback",
        "decision_source": "Rule-based fallback",
        "agreement": "ML model is unavailable.",
        "probabilities": {},
        "feature_signals": [],
        "message": reason,
        "model_version": "",
    }


def _load_model():
    global _cached_model, _model_load_attempted

    if _model_load_attempted:
        return _cached_model

    _model_load_attempted = True
    if not MODEL_PATH.exists():
        return None

    try:
        with MODEL_PATH.open("rb") as model_file:
            _cached_model = pickle.load(model_file)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ValueError, ImportError):
        _cached_model = None

    return _cached_model


def warm_model_cache():
    """Load the model before the browser opens, avoiding a slow first dashboard request."""
    return _load_model()


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


def _predict_with_knn(vector, model):
    training_vectors = model.get("scaled_vectors", [])
    labels = model.get("labels", [])
    neighbors = max(1, min(int(model.get("neighbors", 7)), len(training_vectors)))
    distances = [
        (_euclidean_distance(vector, trained_vector), label)
        for trained_vector, label in zip(training_vectors, labels)
    ]
    distances.sort(key=lambda item: item[0])
    votes = {}

    for distance, label in distances[:neighbors]:
        votes[label] = votes.get(label, 0) + 1 / (distance + 0.000001)

    total_vote = sum(votes.values()) or 1
    predicted_label = max(votes, key=votes.get)
    confidence = round((votes[predicted_label] / total_vote) * 100, 2)
    return predicted_label, confidence


def _predict_with_centroids(vector, model):
    centroids = model.get("centroids", {})
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
    return predicted_label, confidence


def _label_to_state(label):
    if label in CRITICAL_LABELS:
        return "Critical"
    if label in STABLE_LABELS:
        return "Stable"
    return "Watchlist"


def _risk_to_decision(risk):
    if risk >= 75:
        return "Critical"
    if risk >= 45:
        return "Watchlist"
    return "Stable"


def _rule_to_decision(rule_state):
    normalized = str(rule_state or "").strip().lower()
    if normalized in {"critical", "unstable"}:
        return "Critical"
    if normalized in {"degrading", "watchlist", "high", "medium"}:
        return "Watchlist"
    return "Stable"


def _feature_signals(row):
    def value(key):
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            return 0

    signals = []
    cpu = float(value("cpu_percent") or 0)
    memory = float(value("memory_percent") or 0)
    cpu_delta = float(value("cpu_delta") or 0)
    memory_delta = float(value("memory_delta") or 0)
    high_cpu = int(value("high_cpu_processes") or 0)
    high_memory = int(value("high_memory_processes") or 0)
    max_process_cpu = float(value("max_process_cpu") or 0)
    max_process_memory = float(value("max_process_memory") or 0)

    if cpu >= 80:
        signals.append(f"High CPU usage at {cpu:.1f}%.")
    if memory >= 85:
        signals.append(f"High memory usage at {memory:.1f}%.")
    if abs(cpu_delta) >= 18:
        signals.append(f"Sudden CPU change of {cpu_delta:+.1f} percentage points.")
    if abs(memory_delta) >= 8:
        signals.append(f"Sudden memory change of {memory_delta:+.1f} percentage points.")
    if high_cpu:
        signals.append(f"{high_cpu} process(es) crossed the high-CPU threshold.")
    if high_memory:
        signals.append(f"{high_memory} process(es) crossed the high-memory threshold.")
    if max_process_cpu >= 50:
        signals.append(f"Top sampled process CPU reached {max_process_cpu:.1f}%.")
    if max_process_memory >= 12:
        signals.append(f"Top sampled process memory reached {max_process_memory:.1f}%.")

    return signals[:4] or ["Current resource pattern was matched against labeled historical telemetry."]


def _build_decision(rule_state, confidence, ml_risk):
    ml_decision = _risk_to_decision(ml_risk)
    rule_decision = _rule_to_decision(rule_state)

    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return (
            rule_decision,
            "Rule-based fallback due to low ML confidence",
            f"ML confidence is {confidence}%, so the rule-based decision remains active.",
        )

    if ml_decision == rule_decision:
        agreement = "ML and rule-based analysis agree."
    else:
        agreement = f"ML primary decision is {ml_decision}; rule-based evidence is {rule_decision}."

    return ml_decision, "ML primary decision", agreement


def predict_from_feature_row(row, rule_state=None):
    model = _load_model()
    if not model:
        return _default_prediction("No trained ML model found. Train after collecting labeled sessions.")
    if row is None:
        return _default_prediction("No latest ML feature sample is available for prediction.")

    feature_columns = model.get("feature_columns", FEATURE_COLUMNS)
    if not model.get("scaled_vectors") and not model.get("centroids"):
        if not model.get("estimator"):
            return _default_prediction("The saved ML model has no classifier data.")

    raw_vector = _feature_vector(row, feature_columns)
    probabilities_by_label = {}
    if model.get("estimator"):
        estimator = model["estimator"]
        predicted_label = str(estimator.predict([raw_vector])[0])
        if hasattr(estimator, "predict_proba"):
            probabilities = estimator.predict_proba([raw_vector])[0]
            classes = [str(label) for label in estimator.classes_]
            probabilities_by_label = {
                label: round(float(probability) * 100, 2)
                for label, probability in zip(classes, probabilities)
            }
            confidence = round(float(probabilities[classes.index(predicted_label)]) * 100, 2)
        else:
            confidence = 0
    else:
        vector = _standardize(
            raw_vector,
            model.get("means", [0.0] * len(feature_columns)),
            model.get("stddevs", [1.0] * len(feature_columns)),
        )
    if not model.get("estimator") and model.get("scaled_vectors"):
        predicted_label, confidence = _predict_with_knn(vector, model)
    elif not model.get("estimator"):
        predicted_label, confidence = _predict_with_centroids(vector, model)
    if not probabilities_by_label:
        probabilities_by_label = {predicted_label: confidence}

    weighted_risk = sum(
        CLASS_RISK_WEIGHTS.get(label, 50) * probability / 100
        for label, probability in probabilities_by_label.items()
    )
    ml_risk = round(max(0, min(100, weighted_risk)), 2)
    ml_state = _label_to_state(predicted_label)
    final_decision, decision_source, agreement = _build_decision(rule_state, confidence, ml_risk)

    return {
        "available": True,
        "predicted_class": predicted_label,
        "confidence": confidence,
        "state": ml_state,
        "ml_risk": ml_risk,
        "final_decision": final_decision,
        "decision_source": decision_source,
        "agreement": agreement,
        "probabilities": probabilities_by_label,
        "feature_signals": _feature_signals(row),
        "message": agreement,
        "model_version": model.get("version", ""),
    }


def predict_from_feature_window(rows, rule_state=None):
    if not rows:
        return predict_from_feature_row(None, rule_state=rule_state)

    predictions = [predict_from_feature_row(row, rule_state=rule_state) for row in rows]
    latest_prediction = predictions[-1]
    if not latest_prediction.get("available"):
        return latest_prediction

    labels = sorted(
        {
            label
            for prediction in predictions
            for label in prediction.get("probabilities", {})
        }
    )
    averaged_probabilities = {
        label: round(
            sum(prediction.get("probabilities", {}).get(label, 0) for prediction in predictions) / len(predictions),
            2,
        )
        for label in labels
    }
    predicted_label = max(averaged_probabilities, key=averaged_probabilities.get)
    confidence = averaged_probabilities[predicted_label]
    ml_risk = round(
        max(
            0,
            min(
                100,
                sum(CLASS_RISK_WEIGHTS.get(label, 50) * probability / 100 for label, probability in averaged_probabilities.items()),
            ),
        ),
        2,
    )
    final_decision, decision_source, agreement = _build_decision(rule_state, confidence, ml_risk)

    return {
        **latest_prediction,
        "predicted_class": predicted_label,
        "confidence": confidence,
        "state": _label_to_state(predicted_label),
        "ml_risk": ml_risk,
        "final_decision": final_decision,
        "decision_source": f"{decision_source} ({len(predictions)}-sample consensus)",
        "agreement": agreement,
        "probabilities": averaged_probabilities,
        "message": agreement,
        "window_size": len(predictions),
    }
