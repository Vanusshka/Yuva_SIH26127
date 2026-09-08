import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values


# ============================================================
# CONFIGURATION
# ============================================================

SQLITE_PATH = "backend/data/traffic.db"

POSTGRES_URL = os.environ.get("POSTGRES_URL")

if not POSTGRES_URL:
    raise RuntimeError(
        "POSTGRES_URL environment variable is not set."
    )


# ============================================================
# CONNECT
# ============================================================

print("Connecting to SQLite...")

sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
sqlite_cur = sqlite_conn.cursor()

print("Connecting to PostgreSQL...")

pg_conn = psycopg2.connect(POSTGRES_URL)
pg_cur = pg_conn.cursor()

print("Connected successfully.\n")


# ============================================================
# HELPER
# ============================================================

def migrate_table(table_name, columns):
    print(f"Migrating {table_name}...")

    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    rows = sqlite_cur.execute(
        f"SELECT {column_sql} FROM {table_name}"
    ).fetchall()

    print(f"  SQLite rows: {len(rows)}")

    if not rows:
        print("  Nothing to migrate.")
        return

    # Only insert rows that don't already exist.
    # This makes the script safer to re-run.
    primary_key = "id"

    insert_sql = f"""
        INSERT INTO {table_name} ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT ({primary_key}) DO NOTHING
    """

    inserted = 0

    for row in rows:
        values = tuple(row[column] for column in columns)

        pg_cur.execute(insert_sql, values)

        if pg_cur.rowcount:
            inserted += 1

    pg_conn.commit()

    print(f"  Inserted: {inserted}")
    print()


# ============================================================
# MIGRATION ORDER
# ============================================================
#
# trajectory_cameras must come before detections because:
#
# detections.camera_id
#       ↓
# trajectory_cameras.camera_id
#
# cameras must come before vehicle_events because:
#
# vehicle_events.camera_id
#       ↓
# cameras.camera_id
#
# ============================================================


# 1. TRAJECTORY CAMERAS

migrate_table(
    "trajectory_cameras",
    [
        "id",
        "camera_id",
        "location_name",
        "road_name",
        "direction",
        "latitude",
        "longitude",
        "created_at",
    ],
)


# 2. CAMERAS

migrate_table(
    "cameras",
    [
        "id",
        "camera_id",
        "name",
        "latitude",
        "longitude",
        "address",
        "status",
        "created_at",
    ],
)


# 3. DETECTIONS

migrate_table(
    "detections",
    [
        "id",
        "plate_number",
        "camera_id",
        "timestamp",
        "detection_confidence",
        "created_at",
    ],
)


# 4. VEHICLE EVENTS

migrate_table(
    "vehicle_events",
    [
        "id",
        "plate_number",
        "camera_id",
        "timestamp",
        "vehicle_type",
        "vehicle_confidence",
        "plate_confidence",
        "ocr_confidence",
        "image_path",
        "created_at",
        "confidence_tier",
        "valid_ocr_reads",
        "matching_ocr_reads",
        "agreement_rate",
        "vehicle_category",
    ],
)


# 5. MANUAL REVIEWS

migrate_table(
    "manual_reviews",
    [
        "id",
        "camera_id",
        "timestamp",
        "vehicle_type",
        "vehicle_category",
        "ocr_plate_text",
        "ocr_confidence",
        "confidence_tier",
        "agreement_rate",
        "valid_ocr_reads",
        "matching_ocr_reads",
        "source_file",
        "frame_number",
        "track_id",
        "reason",
        "review_status",
        "reviewed_plate",
        "reviewer_notes",
        "reviewed_at",
        "created_at",
    ],
)


# ============================================================
# RESET POSTGRES SEQUENCES
# ============================================================
#
# Because we preserve the original SQLite IDs, PostgreSQL's
# auto-increment sequences need to be moved past the largest ID.
#
# ============================================================

print("Updating PostgreSQL ID sequences...")

sequence_tables = [
    "trajectory_cameras",
    "cameras",
    "detections",
    "vehicle_events",
    "manual_reviews",
]

for table in sequence_tables:
    pg_cur.execute(
        f"""
        SELECT setval(
            pg_get_serial_sequence('{table}', 'id'),
            COALESCE((SELECT MAX(id) FROM {table}), 1),
            true
        )
        """
    )

pg_conn.commit()


# ============================================================
# VERIFY
# ============================================================

print("\nMigration complete!")
print("\nPostgreSQL row counts:")

for table in sequence_tables:
    pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = pg_cur.fetchone()[0]
    print(f"  {table}: {count}")


# ============================================================
# CLOSE
# ============================================================

pg_cur.close()
pg_conn.close()

sqlite_cur.close()
sqlite_conn.close()

print("\nConnections closed.")