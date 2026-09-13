"""
SYNX Relational SQL Database Layer
Stores statutory audit records, photographic evidence hashes, rule evaluations,
and tracks repeat-offender histories under Section 36(1) of the Legal Metrology Act, 2009.
"""

import json
import uuid
import secrets
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from app.config import DATABASE_PATH
from app.extractor.entities import AuditResult


def get_db_connection() -> sqlite3.Connection:
    """Creates a connection to the SQLite database with Row factory enabled."""
    conn = sqlite3.connect(str(DATABASE_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initializes the relational database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Primary Inspections / Audits Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                audit_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                commodity_name TEXT,
                brand TEXT,
                manufacturer TEXT,
                verdict TEXT NOT NULL,
                overall_score REAL NOT NULL,
                passed_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                pdp_area_sqcm REAL DEFAULT 0.0,
                min_font_height_mm REAL DEFAULT 0.0,
                scale_factor REAL DEFAULT 0.0,
                image_sha256 TEXT,
                image_url TEXT,
                pdf_filename TEXT,
                raw_audit_json TEXT,
                inspector_name TEXT DEFAULT '',
                inspector_email TEXT DEFAULT ''
            );
        """)

        # Schema migrations for existing inspections table
        cursor.execute("PRAGMA table_info(inspections);")
        columns = [col["name"] for col in cursor.fetchall()]
        if "inspector_name" not in columns:
            cursor.execute("ALTER TABLE inspections ADD COLUMN inspector_name TEXT DEFAULT '';")
        if "inspector_email" not in columns:
            cursor.execute("ALTER TABLE inspections ADD COLUMN inspector_email TEXT DEFAULT '';")

        # 2. Relational Child Table: Rule Evaluations & Violations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT NOT NULL,
                clause TEXT NOT NULL,
                title TEXT NOT NULL,
                field_target TEXT,
                status TEXT NOT NULL,
                severity TEXT,
                measured_value TEXT,
                expected_value TEXT,
                penalty_risk TEXT,
                message TEXT,
                FOREIGN KEY (audit_id) REFERENCES inspections(audit_id) ON DELETE CASCADE
            );
        """)

        # 3. User Authentication Tables (Google Auth & Sessions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                picture TEXT,
                role TEXT DEFAULT 'Legal Metrology Inspector',
                department TEXT DEFAULT 'Legal Metrology Enforcement Division',
                created_at TEXT NOT NULL,
                last_login TEXT NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)

        # 4. Fast Lookup Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_created_at ON inspections(created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_manufacturer ON inspections(manufacturer);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_verdict ON inspections(verdict);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_inspector ON inspections(inspector_email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_audit_id ON audit_evaluations(audit_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_clause ON audit_evaluations(clause);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);")

        conn.commit()


def is_inspector_role(role: str) -> bool:
    """Checks if a user's statutory role grants Inspector privileges."""
    if not role:
        return False
    r = role.strip().lower()
    return any(kw in r for kw in ("inspector", "chief", "senior", "director", "admin"))


def get_or_create_google_user(
    google_id: str,
    email: str,
    name: str,
    picture: str = "",
    role: Optional[str] = None,
    department: str = "Legal Metrology Enforcement Division"
) -> Dict[str, Any]:
    """
    Retrieves existing user by google_id or email, or creates a new user.
    Updates last_login timestamp and picture/name if changed, preserving existing role.
    If creating a new user: assigns Inspector if first user in DB, otherwise defaults to 'Field Officer'.
    """
    now_iso = datetime.now().isoformat()
    clean_email = email.lower().strip()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE google_id = ? OR email = ?;", (google_id, clean_email))
        row = cursor.fetchone()
        if row:
            user_id = row["id"]
            if role:
                cursor.execute("""
                    UPDATE users
                    SET name = ?, picture = COALESCE(NULLIF(?, ''), picture), last_login = ?,
                        google_id = COALESCE(google_id, ?), role = ?
                    WHERE id = ?;
                """, (name, picture, now_iso, google_id, role, user_id))
            else:
                cursor.execute("""
                    UPDATE users
                    SET name = ?, picture = COALESCE(NULLIF(?, ''), picture), last_login = ?,
                        google_id = COALESCE(google_id, ?)
                    WHERE id = ?;
                """, (name, picture, now_iso, google_id, user_id))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            return dict(cursor.fetchone())
        else:
            # First user becomes Senior Inspector, otherwise use provided role or default to Field Officer
            cursor.execute("SELECT COUNT(*) FROM users;")
            user_count = cursor.fetchone()[0]
            if user_count == 0:
                assigned_role = "Senior Legal Metrology Officer"
            elif role:
                assigned_role = role
            else:
                assigned_role = "Field Officer"

            cursor.execute("""
                INSERT INTO users (google_id, email, name, picture, role, department, created_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (google_id, clean_email, name, picture, assigned_role, department, now_iso, now_iso))
            conn.commit()
            user_id = cursor.lastrowid
            cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            return dict(cursor.fetchone())


def list_all_users() -> List[Dict[str, Any]]:
    """Returns all registered users with their roles and activity timestamps."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, google_id, email, name, picture, role, department, created_at, last_login
            FROM users
            ORDER BY id ASC;
        """)
        return [dict(r) for r in cursor.fetchall()]


def update_user_role(user_id: int, new_role: str) -> Optional[Dict[str, Any]]:
    """Updates the statutory role of a user."""
    clean_role = new_role.strip()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE id = ?;", (clean_role, user_id))
        conn.commit()
        cursor.execute("""
            SELECT id, google_id, email, name, picture, role, department, created_at, last_login
            FROM users
            WHERE id = ?;
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_user_session(user_id: int, duration_days: int = 30) -> str:
    """Generates a CSPRNG cryptographically secure session token and persists it in SQLite."""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires = now + timedelta(days=duration_days)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (session_token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?);
        """, (token, user_id, now.isoformat(), expires.isoformat()))
        conn.commit()
    return token


def get_user_from_session(token: str) -> Optional[Dict[str, Any]]:
    """Validates session token and returns associated user dict if unexpired."""
    if not token:
        return None
    now_iso = datetime.now().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.*, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? AND s.expires_at > ?;
        """, (token, now_iso))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data.pop("expires_at", None)
        return data


def revoke_session(token: str) -> bool:
    """Deletes a session token from the database."""
    if not token:
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?;", (token,))
        conn.commit()
        return cursor.rowcount > 0


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves user by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def save_audit_record(
    audit: AuditResult,
    image_sha256: str = "",
    pdf_filename: str = "",
    inspector_name: str = "",
    inspector_email: str = ""
) -> Dict[str, Any]:
    """
    Persists an audit result into the SQL database.
    Replaces in-memory transient state with permanent relational records.
    """
    commodity_name = ""
    manufacturer = ""
    brand = ""

    if audit.extracted_fields:
        if "commodity_name" in audit.extracted_fields and audit.extracted_fields["commodity_name"]:
            commodity_name = audit.extracted_fields["commodity_name"].raw_text or ""
        if "manufacturer" in audit.extracted_fields and audit.extracted_fields["manufacturer"]:
            manufacturer = audit.extracted_fields["manufacturer"].raw_text or ""
        if "brand" in audit.extracted_fields and audit.extracted_fields["brand"]:
            brand = audit.extracted_fields["brand"].raw_text or ""

    created_at = audit.timestamp or datetime.now().isoformat()
    if hasattr(audit, "model_dump_json"):
        raw_json = audit.model_dump_json()
    elif hasattr(audit, "model_dump"):
        raw_json = json.dumps(audit.model_dump())
    elif hasattr(audit, "dict"):
        raw_json = json.dumps(audit.dict())
    else:
        raw_json = json.dumps(audit, default=str)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert or Replace in primary inspections table
        cursor.execute("""
            INSERT OR REPLACE INTO inspections (
                audit_id, created_at, commodity_name, brand, manufacturer,
                verdict, overall_score, passed_count, warning_count, failed_count,
                pdp_area_sqcm, min_font_height_mm, scale_factor,
                image_sha256, image_url, pdf_filename, raw_audit_json,
                inspector_name, inspector_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit.audit_id,
            created_at,
            commodity_name,
            brand,
            manufacturer,
            audit.verdict,
            audit.overall_score,
            audit.summary.get("passed", 0),
            audit.summary.get("warnings", 0),
            audit.summary.get("failed", 0),
            audit.pdp.pdp_area_sqcm if audit.pdp else 0.0,
            audit.pdp.required_min_font_height_mm if audit.pdp else 0.0,
            audit.calibration.mm_per_pixel if audit.calibration else 0.0,
            image_sha256,
            audit.image_url or "",
            pdf_filename,
            raw_json,
            inspector_name,
            inspector_email
        ))

        # Clear existing evaluations if updating
        cursor.execute("DELETE FROM audit_evaluations WHERE audit_id = ?;", (audit.audit_id,))

        # Insert child evaluations
        eval_rows = []
        for ev in audit.rule_evaluations or []:
            eval_rows.append((
                audit.audit_id,
                ev.clause,
                ev.title,
                ev.field_target,
                ev.status,
                ev.severity,
                ev.measured_value or "",
                ev.expected_value or "",
                ev.penalty_risk or "",
                ev.message or ""
            ))

        cursor.executemany("""
            INSERT INTO audit_evaluations (
                audit_id, clause, title, field_target, status,
                severity, measured_value, expected_value, penalty_risk, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, eval_rows)

        conn.commit()

    return {
        "audit_id": audit.audit_id,
        "saved_at": created_at,
        "status": "persisted_in_sql"
    }


def get_audit_by_id(audit_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an audit and its complete JSON representation from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inspections WHERE audit_id = ?;", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return None

        data = dict(row)
        if data.get("raw_audit_json"):
            try:
                data["audit_detail"] = json.loads(data["raw_audit_json"])
            except Exception:
                data["audit_detail"] = None
        return data


def list_recent_audits(
    limit: int = 50,
    search: Optional[str] = None,
    inspector_email: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns recent audit records with optional search filter on commodity or manufacturer,
    and optional scope filter by inspector email.
    Clamps limit between 1 and 100 to prevent denial-of-service memory exhaustion.
    """
    safe_limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 50, 100))
    clean_email = inspector_email.strip().lower() if inspector_email else None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if clean_email:
            conditions.append("LOWER(inspector_email) = ?")
            params.append(clean_email)

        if search:
            clean_search = str(search).strip()[:100]
            like_pat = f"%{clean_search}%"
            conditions.append("(commodity_name LIKE ? OR manufacturer LIKE ? OR verdict LIKE ? OR inspector_name LIKE ?)")
            params.extend([like_pat, like_pat, like_pat, like_pat])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT audit_id, created_at, commodity_name, manufacturer,
                   verdict, overall_score, passed_count, warning_count, failed_count,
                   image_url, pdf_filename, inspector_name, inspector_email
            FROM inspections
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ?;
        """
        params.append(safe_limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def count_inspector_audits(inspector_email: str) -> int:
    """Counts statutory inspections completed by a specific officer."""
    if not inspector_email:
        return 0
    clean_email = inspector_email.strip().lower()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM inspections WHERE LOWER(inspector_email) = ?;", (clean_email,))
        row = cursor.fetchone()
        return row[0] if row else 0


def get_manufacturer_offence_count(manufacturer_name: str) -> int:
    """
    Counts previous violations for the given manufacturer to establish
    repeat offender penalties under Section 36(1) of the Legal Metrology Act.
    """
    if not manufacturer_name or len(manufacturer_name.strip()) < 3:
        return 0

    norm_name = f"%{manufacturer_name.strip()}%"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM inspections
            WHERE manufacturer LIKE ? AND verdict = 'NON_COMPLIANT';
        """, (norm_name,))
        result = cursor.fetchone()
        return result[0] if result else 0


def get_system_analytics() -> Dict[str, Any]:
    """Generates compliance ledger analytics across all stored inspections."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM inspections;")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT verdict, COUNT(*) FROM inspections GROUP BY verdict;")
        verdict_counts = {r[0]: r[1] for r in cursor.fetchall()}

        cursor.execute("""
            SELECT clause, title, COUNT(*) as fail_count
            FROM audit_evaluations
            WHERE status = 'FAIL'
            GROUP BY clause, title
            ORDER BY fail_count DESC
            LIMIT 5;
        """)
        top_violations = [
            {"clause": r[0], "title": r[1], "count": r[2]}
            for r in cursor.fetchall()
        ]

        compliant = verdict_counts.get("COMPLIANT", 0)
        compliance_rate = (compliant / total * 100.0) if total > 0 else 0.0

        return {
            "total_inspections": total,
            "verdicts": verdict_counts,
            "compliance_rate_percent": round(compliance_rate, 1),
            "top_statutory_violations": top_violations
        }


def check_db_health() -> Dict[str, Any]:
    """Verifies SQLite database connectivity and returns table row counts."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM inspections;")
            inspections_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users;")
            users_count = cursor.fetchone()[0]
            db_size_bytes = DATABASE_PATH.stat().st_size if DATABASE_PATH.exists() else 0
            return {
                "status": "connected",
                "engine": "SQLite3",
                "database_name": DATABASE_PATH.name,
                "size_kb": round(db_size_bytes / 1024, 2),
                "inspections_count": inspections_count,
                "users_count": users_count
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
