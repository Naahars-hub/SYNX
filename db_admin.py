#!/usr/bin/env python3
"""
SYNX Database Administration & Operations CLI
Provides database verification, integrity checking, statistics, backups, and maintenance.
"""

import sys
import shutil
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import DATABASE_PATH
from app.db import init_db, check_db_health, get_system_analytics


def cmd_verify(args):
    """Verifies schema integrity, table existence, and foreign key compliance."""
    print("=" * 60)
    print("  SYNX DATABASE INTEGRITY & SCHEMA VERIFICATION")
    print("=" * 60)
    print(f"Database Path : {DATABASE_PATH}")
    if not DATABASE_PATH.exists():
        print("[ERROR] Database file does not exist. Initializing new schema...")
        init_db()

    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()

    # 1. PRAGMA integrity_check
    cursor.execute("PRAGMA integrity_check;")
    integrity = cursor.fetchall()
    print("\n[1] SQLite File Integrity:")
    for row in integrity:
        status_str = "OK" if row[0] == "ok" else f"WARNING: {row[0]}"
        print(f"    - PRAGMA integrity_check: {status_str}")

    # 2. PRAGMA foreign_key_check
    cursor.execute("PRAGMA foreign_key_check;")
    fk_violations = cursor.fetchall()
    print("\n[2] Foreign Key Integrity:")
    if not fk_violations:
        print("    - No foreign key violations found (100% consistent).")
    else:
        print(f"    - WARNING: Found {len(fk_violations)} FK violation(s): {fk_violations}")

    # 3. Table inspection and counts
    expected_tables = ["inspections", "audit_evaluations", "users", "sessions"]
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    found_tables = {row[0] for row in cursor.fetchall()}

    print("\n[3] Relational Tables & Row Counts:")
    all_ok = True
    for tbl in expected_tables:
        if tbl in found_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {tbl};")
            count = cursor.fetchone()[0]
            print(f"    [OK] Table '{tbl}': {count:,} records")
        else:
            print(f"    [MISSING] Table '{tbl}' NOT found!")
            all_ok = False

    # 4. Storage metrics
    size_bytes = DATABASE_PATH.stat().st_size
    print(f"\n[4] Database File Size: {size_bytes / 1024:.2f} KB ({size_bytes / (1024 * 1024):.2f} MB)")
    conn.close()

    if all_ok:
        print("\n--> Database verification completed successfully. Schema is 100% operational.")
        return 0
    else:
        print("\n--> Verification detected issues. Run `python db_admin.py init` to repair schema.")
        return 1


def cmd_stats(args):
    """Displays detailed inspection and system analytics."""
    print("=" * 60)
    print("  SYNX COMPLIANCE LEDGER & ANALYTICS OVERVIEW")
    print("=" * 60)
    health = check_db_health()
    print(f"Database Health Status: {health.get('status')}")
    print(f"File Size             : {health.get('size_kb')} KB")
    print(f"Total Inspections     : {health.get('inspections_count')}")
    print(f"Registered Inspectors : {health.get('users_count')}")

    analytics = get_system_analytics()
    print("\nVerdict Breakdown:")
    for verdict, count in analytics.get("verdicts", {}).items():
        print(f"  - {verdict:<16}: {count}")
    print(f"Overall Compliance Rate: {analytics.get('compliance_rate_percent')}%")

    top_v = analytics.get("top_statutory_violations", [])
    if top_v:
        print("\nTop Statutory Violations:")
        for idx, item in enumerate(top_v, 1):
            print(f"  {idx}. {item['clause']}: {item['title']} ({item['count']} occurrences)")
    return 0


def cmd_backup(args):
    """Creates a timestamped snapshot backup of the database."""
    backup_dir = BASE_DIR / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_file = backup_dir / f"metrology_audit_{timestamp}.db"

    # SQLite backup API ensures clean atomic copy even while database is actively written to
    src_conn = sqlite3.connect(str(DATABASE_PATH))
    dest_conn = sqlite3.connect(str(target_file))
    with dest_conn:
        src_conn.backup(dest_conn)
    dest_conn.close()
    src_conn.close()

    size_kb = target_file.stat().st_size / 1024
    print(f"[OK] Database backed up successfully:")
    print(f"     Destination: {target_file}")
    print(f"     Size       : {size_kb:.2f} KB")
    return 0


def cmd_vacuum(args):
    """Runs SQLite VACUUM and REINDEX to optimize storage and queries."""
    print("[*] Optimizing database storage...")
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.execute("VACUUM;")
    conn.execute("REINDEX;")
    conn.close()
    size_kb = DATABASE_PATH.stat().st_size / 1024
    print(f"[OK] VACUUM and REINDEX complete. Current size: {size_kb:.2f} KB.")
    return 0


def cmd_init(args):
    """Initializes tables and indexes."""
    print(f"[*] Initializing database schema at: {DATABASE_PATH}")
    init_db()
    print("[OK] Relational tables and indexes created/verified.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="SYNX Legal Metrology Database Administration Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    subparsers.add_parser("verify", help="Check database integrity, schema tables, and record counts")
    subparsers.add_parser("stats", help="Show inspection statistics and analytics")
    subparsers.add_parser("backup", help="Create a timestamped backup of the database")
    subparsers.add_parser("vacuum", help="Compact and re-index database")
    subparsers.add_parser("init", help="Create schema tables if missing")

    args = parser.parse_args()
    if not args.command:
        # Default to verify
        return cmd_verify(args)

    commands = {
        "verify": cmd_verify,
        "stats": cmd_stats,
        "backup": cmd_backup,
        "vacuum": cmd_vacuum,
        "init": cmd_init
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
