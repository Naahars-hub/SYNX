"""
SYNX Relational SQL Database Layer
Stores statutory audit records, photographic evidence hashes, rule evaluations,
and tracks repeat-offender histories under Section 36(1) of the Legal Metrology Act, 2009.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
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
                raw_audit_json TEXT
            );
        """)

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

        # 3. Fast Lookup Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_created_at ON inspections(created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_manufacturer ON inspections(manufacturer);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_inspections_verdict ON inspections(verdict);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_audit_id ON audit_evaluations(audit_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_clause ON audit_evaluations(clause);")

        conn.commit()


def save_audit_record(audit: AuditResult, image_sha256: str = "", pdf_filename: str = "") -> Dict[str, Any]:
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
                image_sha256, image_url, pdf_filename, raw_audit_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            raw_json
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


def list_recent_audits(limit: int = 50, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns recent audit records with optional search filter on commodity or manufacturer.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if search:
            like_pat = f"%{search.strip()}%"
            cursor.execute("""
                SELECT audit_id, created_at, commodity_name, manufacturer,
                       verdict, overall_score, passed_count, warning_count, failed_count,
                       image_url, pdf_filename
                FROM inspections
                WHERE commodity_name LIKE ? OR manufacturer LIKE ? OR verdict LIKE ?
                ORDER BY created_at DESC
                LIMIT ?;
            """, (like_pat, like_pat, like_pat, limit))
        else:
            cursor.execute("""
                SELECT audit_id, created_at, commodity_name, manufacturer,
                       verdict, overall_score, passed_count, warning_count, failed_count,
                       image_url, pdf_filename
                FROM inspections
                ORDER BY created_at DESC
                LIMIT ?;
            """, (limit,))

        rows = cursor.fetchall()
        return [dict(r) for r in rows]


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
