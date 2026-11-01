"""Admin audit trail helpers."""

from __future__ import annotations

import json

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(
    db: Session,
    *,
    admin: User | None,
    action: str,
    entity_type: str = "",
    entity_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    row = AuditLog(
        admin_user_id=admin.id if admin else None,
        action=action[:64],
        entity_type=entity_type[:32],
        entity_id=entity_id,
        before=json.dumps(before or {}, ensure_ascii=False, default=str)[:4000],
        after=json.dumps(after or {}, ensure_ascii=False, default=str)[:4000],
        ip_address=(request.client.host if request and request.client else "")[:64],
        user_agent=(request.headers.get("user-agent", "") if request else "")[:400],
    )
    db.add(row)
    return row
