import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "monitoring.db"
PROCESS_SAMPLE_RETENTION_DAYS = 30
SYSTEM_SAMPLE_RETENTION_DAYS = 365
INCIDENT_RETENTION_DAYS = 180
ML_FEATURE_RETENTION_DAYS = 730


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=MEMORY")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def _ensure_column(cursor, table_name, column_name, definition):
    columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing_names = {column[1] for column in columns}
    if column_name not in existing_names:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def ensure_database():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO collection_state (key, value)
        VALUES ('current_label', 'unlabeled')
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL DEFAULT 'live',
            collection_label TEXT NOT NULL DEFAULT 'unlabeled',
            created_at TEXT NOT NULL,
            cpu_percent REAL NOT NULL,
            memory_percent REAL NOT NULL,
            total_processes INTEGER NOT NULL,
            high_cpu_processes INTEGER NOT NULL,
            high_memory_processes INTEGER NOT NULL,
            monitor_cpu_percent REAL NOT NULL DEFAULT 0,
            monitor_memory_percent REAL NOT NULL DEFAULT 0
        )
        """
    )
    _ensure_column(cursor, "system_samples", "mode", "TEXT NOT NULL DEFAULT 'live'")
    _ensure_column(cursor, "system_samples", "collection_label", "TEXT NOT NULL DEFAULT 'unlabeled'")
    _ensure_column(cursor, "system_samples", "monitor_cpu_percent", "REAL NOT NULL DEFAULT 0")
    _ensure_column(cursor, "system_samples", "monitor_memory_percent", "REAL NOT NULL DEFAULT 0")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS process_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_sample_id INTEGER NOT NULL,
            mode TEXT NOT NULL DEFAULT 'live',
            collection_label TEXT NOT NULL DEFAULT 'unlabeled',
            pid INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '',
            executable_path TEXT NOT NULL DEFAULT '',
            cpu_percent REAL NOT NULL,
            memory_percent REAL NOT NULL,
            runtime_seconds REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(system_sample_id) REFERENCES system_samples(id)
        )
        """
    )
    _ensure_column(cursor, "process_samples", "mode", "TEXT NOT NULL DEFAULT 'live'")
    _ensure_column(cursor, "process_samples", "collection_label", "TEXT NOT NULL DEFAULT 'unlabeled'")
    _ensure_column(cursor, "process_samples", "display_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(cursor, "process_samples", "details", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(cursor, "process_samples", "executable_path", "TEXT NOT NULL DEFAULT ''")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS incident_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL DEFAULT 'live',
            event_time TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            process_name TEXT NOT NULL DEFAULT '',
            process_pid TEXT NOT NULL DEFAULT '',
            UNIQUE(mode, event_time, title)
        )
        """
    )
    _ensure_column(cursor, "incident_events", "process_name", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(cursor, "incident_events", "process_pid", "TEXT NOT NULL DEFAULT ''")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_feature_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_sample_id INTEGER NOT NULL UNIQUE,
            mode TEXT NOT NULL DEFAULT 'live',
            collection_label TEXT NOT NULL DEFAULT 'unlabeled',
            created_at TEXT NOT NULL,
            cpu_percent REAL NOT NULL,
            memory_percent REAL NOT NULL,
            total_processes INTEGER NOT NULL,
            high_cpu_processes INTEGER NOT NULL,
            high_memory_processes INTEGER NOT NULL,
            monitor_cpu_percent REAL NOT NULL DEFAULT 0,
            monitor_memory_percent REAL NOT NULL DEFAULT 0,
            sampled_process_count INTEGER NOT NULL,
            avg_process_cpu REAL NOT NULL,
            max_process_cpu REAL NOT NULL,
            avg_process_memory REAL NOT NULL,
            max_process_memory REAL NOT NULL
        )
        """
    )
    _ensure_column(cursor, "ml_feature_samples", "collection_label", "TEXT NOT NULL DEFAULT 'unlabeled'")
    _ensure_column(cursor, "ml_feature_samples", "monitor_cpu_percent", "REAL NOT NULL DEFAULT 0")
    _ensure_column(cursor, "ml_feature_samples", "monitor_memory_percent", "REAL NOT NULL DEFAULT 0")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_samples_created_at ON system_samples(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_process_samples_system_sample_id ON process_samples(system_sample_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incident_events_event_time ON incident_events(event_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ml_feature_samples_created_at ON ml_feature_samples(created_at)")

    _backfill_ml_feature_samples(cursor)

    connection.commit()
    connection.close()


def _backfill_ml_feature_samples(cursor):
    cursor.execute(
        """
        INSERT OR IGNORE INTO ml_feature_samples (
            system_sample_id,
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
            max_process_memory
        )
        SELECT
            s.id,
            s.mode,
            s.collection_label,
            s.created_at,
            s.cpu_percent,
            s.memory_percent,
            s.total_processes,
            s.high_cpu_processes,
            s.high_memory_processes,
            s.monitor_cpu_percent,
            s.monitor_memory_percent,
            COUNT(p.id),
            COALESCE(AVG(p.cpu_percent), 0),
            COALESCE(MAX(p.cpu_percent), 0),
            COALESCE(AVG(p.memory_percent), 0),
            COALESCE(MAX(p.memory_percent), 0)
        FROM system_samples s
        LEFT JOIN process_samples p ON p.system_sample_id = s.id
        WHERE NOT EXISTS (
            SELECT 1
            FROM ml_feature_samples f
            WHERE f.system_sample_id = s.id
        )
        GROUP BY s.id
        """
    )


def _insert_ml_feature_sample(cursor, sample_id, snapshot):
    processes = snapshot.get("top_processes", [])
    process_count = len(processes)
    cpu_values = [float(process.get("cpu_percent") or 0) for process in processes]
    memory_values = [float(process.get("memory_percent") or 0) for process in processes]

    cursor.execute(
        """
        INSERT OR IGNORE INTO ml_feature_samples (
            system_sample_id,
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
            max_process_memory
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sample_id,
            snapshot.get("mode", "live"),
            snapshot.get("collection_label", "unlabeled"),
            snapshot["created_at"],
            snapshot["cpu_percent"],
            snapshot["memory_percent"],
            snapshot["total_processes"],
            snapshot["high_cpu_processes"],
            snapshot["high_memory_processes"],
            snapshot.get("monitor_cpu_percent", 0),
            snapshot.get("monitor_memory_percent", 0),
            process_count,
            round(sum(cpu_values) / process_count, 2) if process_count else 0,
            round(max(cpu_values), 2) if cpu_values else 0,
            round(sum(memory_values) / process_count, 2) if process_count else 0,
            round(max(memory_values), 2) if memory_values else 0,
        ),
    )


def insert_snapshot(snapshot):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO system_samples (
            mode,
            collection_label,
            created_at,
            cpu_percent,
            memory_percent,
            total_processes,
            high_cpu_processes,
            high_memory_processes,
            monitor_cpu_percent,
            monitor_memory_percent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.get("mode", "live"),
            snapshot.get("collection_label", "unlabeled"),
            snapshot["created_at"],
            snapshot["cpu_percent"],
            snapshot["memory_percent"],
            snapshot["total_processes"],
            snapshot["high_cpu_processes"],
            snapshot["high_memory_processes"],
            snapshot.get("monitor_cpu_percent", 0),
            snapshot.get("monitor_memory_percent", 0),
        ),
    )

    sample_id = cursor.lastrowid

    cursor.executemany(
        """
        INSERT INTO process_samples (
            system_sample_id,
            mode,
            collection_label,
            pid,
            name,
            display_name,
            details,
            executable_path,
            cpu_percent,
            memory_percent,
            runtime_seconds,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                sample_id,
                snapshot.get("mode", "live"),
                snapshot.get("collection_label", "unlabeled"),
                process["pid"],
                process["name"],
                process.get("display_name", process["name"]),
                process.get("details", ""),
                process.get("executable_path", ""),
                process["cpu_percent"],
                process["memory_percent"],
                process["runtime_seconds"],
                process["status"],
            )
            for process in snapshot["top_processes"]
        ],
    )

    _insert_ml_feature_sample(cursor, sample_id, snapshot)

    connection.commit()
    connection.close()


def cleanup_old_records():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM process_samples
        WHERE system_sample_id IN (
            SELECT id
            FROM system_samples
            WHERE replace(created_at, 'T', ' ') < datetime('now', ?)
        )
        """,
        (f"-{PROCESS_SAMPLE_RETENTION_DAYS} days",),
    )
    deleted_process_samples = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM incident_events
        WHERE replace(event_time, 'T', ' ') < datetime('now', ?)
        """,
        (f"-{INCIDENT_RETENTION_DAYS} days",),
    )
    deleted_incidents = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM system_samples
        WHERE replace(created_at, 'T', ' ') < datetime('now', ?)
        """,
        (f"-{SYSTEM_SAMPLE_RETENTION_DAYS} days",),
    )
    deleted_system_samples = cursor.rowcount

    cursor.execute(
        """
        DELETE FROM ml_feature_samples
        WHERE replace(created_at, 'T', ' ') < datetime('now', ?)
        """,
        (f"-{ML_FEATURE_RETENTION_DAYS} days",),
    )
    deleted_ml_features = cursor.rowcount

    connection.commit()
    connection.close()

    return {
        "process_samples": deleted_process_samples,
        "incident_events": deleted_incidents,
        "system_samples": deleted_system_samples,
        "ml_feature_samples": deleted_ml_features,
    }


def fetch_recent_system_samples(limit=30, mode=None):
    connection = get_connection()
    if mode:
        rows = connection.execute(
            """
            SELECT *
            FROM system_samples
            WHERE mode = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (mode, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT *
            FROM system_samples
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    connection.close()
    return list(reversed(rows))


def fetch_latest_processes(limit=10, mode=None):
    connection = get_connection()
    if mode:
        latest = connection.execute(
            "SELECT MAX(id) AS latest_id FROM system_samples WHERE mode = ?",
            (mode,),
        ).fetchone()
    else:
        latest = connection.execute(
            "SELECT MAX(id) AS latest_id FROM system_samples"
        ).fetchone()

    if not latest or latest["latest_id"] is None:
        connection.close()
        return []

    rows = connection.execute(
        """
        SELECT pid, name, display_name, details, executable_path, cpu_percent, memory_percent, runtime_seconds, status
        FROM process_samples
        WHERE system_sample_id = ?
        ORDER BY cpu_percent DESC, memory_percent DESC
        LIMIT ?
        """,
        (latest["latest_id"], limit),
    ).fetchall()
    connection.close()
    return rows


def fetch_latest_ml_feature_sample(mode=None):
    connection = get_connection()

    if mode:
        row = connection.execute(
            """
            SELECT *
            FROM ml_feature_samples
            WHERE mode = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (mode,),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT *
            FROM ml_feature_samples
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    connection.close()
    return row


def insert_incident_events(events, mode):
    if not events:
        return

    connection = get_connection()
    cursor = connection.cursor()
    cursor.executemany(
        """
        INSERT OR IGNORE INTO incident_events (
            mode,
            event_time,
            severity,
            title,
            message,
            process_name,
            process_pid
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                mode,
                event["time"],
                event["severity"],
                event["title"],
                event["message"],
                event.get("process_name", ""),
                str(event.get("process_pid", "")),
            )
            for event in events
        ],
    )
    connection.commit()
    connection.close()


def fetch_recent_incidents(limit=12, mode=None, severity_filter="all"):
    connection = get_connection()

    severity_levels = {
        "all": ["low", "medium", "high", "critical"],
        "medium_plus": ["medium", "high", "critical"],
        "high_plus": ["high", "critical"],
        "critical": ["critical"],
    }
    severities = severity_levels.get(severity_filter, severity_levels["all"])
    severity_placeholders = ", ".join("?" for _ in severities)

    query = f"""
        SELECT
            MIN(event_time) AS first_time,
            MAX(event_time) AS time,
            severity,
            title,
            message,
            process_name,
            process_pid,
            COUNT(*) AS occurrences
        FROM incident_events
        WHERE severity IN ({severity_placeholders})
    """
    params = list(severities)

    if mode:
        query += " AND mode = ?"
        params.append(mode)

    query += " GROUP BY severity, title, message, process_name, process_pid ORDER BY MAX(event_time) DESC LIMIT ?"
    params.append(limit)

    rows = connection.execute(query, tuple(params)).fetchall()
    connection.close()
    return list(reversed(rows))
