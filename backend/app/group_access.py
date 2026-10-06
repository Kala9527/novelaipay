from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GroupMember, UpstreamGroup, User


def can_use_group(db: Session, group: UpstreamGroup | None, user_id: int) -> bool:
    if group is None or not group.enabled:
        return False
    if not group.is_private:
        return True
    user = db.get(User, user_id)
    return bool(user and (user.is_admin or db.scalar(select(GroupMember.id).where(
        GroupMember.group_id == group.id, GroupMember.user_id == user_id)) is not None))
