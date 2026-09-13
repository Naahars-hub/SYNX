"""
SYNX Legal Metrology Database Package
Relational storage for statutory inspection ledgers, rule findings, and repeat-offense history.
"""
from app.db.database import (
    init_db,
    save_audit_record,
    get_audit_by_id,
    list_recent_audits,
    get_manufacturer_offence_count,
    get_system_analytics,
    get_or_create_google_user,
    create_user_session,
    get_user_from_session,
    revoke_session,
    get_user_by_id,
    count_inspector_audits,
    is_inspector_role,
    list_all_users,
    update_user_role,
    check_db_health
)

__all__ = [
    "init_db",
    "save_audit_record",
    "get_audit_by_id",
    "list_recent_audits",
    "get_manufacturer_offence_count",
    "get_system_analytics",
    "get_or_create_google_user",
    "create_user_session",
    "get_user_from_session",
    "revoke_session",
    "get_user_by_id",
    "count_inspector_audits",
    "is_inspector_role",
    "list_all_users",
    "update_user_role",
    "check_db_health",
]
