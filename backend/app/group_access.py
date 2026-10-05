from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GroupMember, UpstreamGroup


def can_use_group(db: Session, group: UpstreamGroup | None, user_id: int) -> bool:
    return bool(group and group.enabled and (
        not group.is_private or db.scalar(select(GroupMember.id).where(
            GroupMember.group_id == group.id, GroupMember.user_id == user_id)) is not None
    ))
