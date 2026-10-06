from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..group_access import can_use_group
from ..models import Announcement, ModelMapping, ModelRoute, PriceVersion, UpstreamAccount, UpstreamGroup, User, utcnow
from .deps import admin_user, optional_user


public_router = APIRouter(prefix='/api/public', tags=['public'])
admin_router = APIRouter(prefix='/api/admin/announcements', tags=['admin'])


class AnnouncementInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=10000)
    is_private: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode='after')
    def validate_schedule(self):
        self.title = self.title.strip()
        self.body = self.body.strip()
        if not self.title or not self.body:
            raise ValueError('Title and body are required')
        for field in ('starts_at', 'ends_at'):
            value = getattr(self, field)
            if value is not None:
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f'{field} must include a time zone')
                setattr(self, field, value.astimezone(timezone.utc))
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError('End time must be later than start time')
        return self


def announcement_view(row: Announcement) -> dict:
    return {'id': row.id, 'title': row.title, 'body': row.body,
            'is_private': row.is_private, 'starts_at': row.starts_at,
            'ends_at': row.ends_at, 'created_at': row.created_at,
            'updated_at': row.updated_at}


@public_router.get('/models')
def public_models(user: User | None = Depends(optional_user),
                  db: Session = Depends(get_db)) -> list[dict]:
    result = []
    mappings = db.scalars(select(ModelMapping).where(
        ModelMapping.enabled.is_(True), ModelMapping.deleted_at.is_(None),
    ).order_by(ModelMapping.public_name, ModelMapping.id)).all()
    for mapping in mappings:
        group = db.get(UpstreamGroup, mapping.group_id)
        if group is None or group.deleted_at or not group.enabled:
            continue
        if group.is_private and (user is None or not can_use_group(db, group, user.id)):
            continue
        price = db.scalar(select(PriceVersion).where(
            PriceVersion.model_mapping_id == mapping.id,
        ).order_by(PriceVersion.id.desc()))
        active_route = db.scalar(select(ModelRoute.id).join(UpstreamAccount,
            ModelRoute.account_id == UpstreamAccount.id).where(
            ModelRoute.model_mapping_id == mapping.id,
            UpstreamAccount.enabled.is_(True), UpstreamAccount.deleted_at.is_(None),
        ).limit(1))
        if price is None or active_route is None:
            continue
        result.append({'name': mapping.public_name, 'group_id': group.id,
                       'group_name': group.name, 'is_private': group.is_private,
                       'price': str(price.amount), 'extra_amount': str(price.extra_amount),
                       'currency': price.currency, 'billing_mode': price.billing_mode})
    return result


@public_router.get('/announcements')
def visible_announcements(user: User | None = Depends(optional_user),
                          db: Session = Depends(get_db)) -> list[dict]:
    now = utcnow()
    query = select(Announcement).where(
        or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
        or_(Announcement.ends_at.is_(None), Announcement.ends_at > now),
    )
    if user is None:
        query = query.where(Announcement.is_private.is_(False))
    return [announcement_view(row) for row in db.scalars(query.order_by(
        Announcement.created_at.desc(), Announcement.id.desc()))]


@admin_router.get('')
def all_announcements(_: User = Depends(admin_user),
                      db: Session = Depends(get_db)) -> list[dict]:
    return [announcement_view(row) for row in db.scalars(select(Announcement).order_by(
        Announcement.created_at.desc(), Announcement.id.desc()))]


@admin_router.post('')
def create_announcement(payload: AnnouncementInput, _: User = Depends(admin_user),
                        db: Session = Depends(get_db)) -> dict:
    row = Announcement(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return announcement_view(row)


@admin_router.patch('/{announcement_id}')
def update_announcement(announcement_id: int, payload: AnnouncementInput,
                        _: User = Depends(admin_user), db: Session = Depends(get_db)) -> dict:
    row = db.get(Announcement, announcement_id)
    if row is None:
        raise HTTPException(404, 'Announcement not found')
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return announcement_view(row)


@admin_router.delete('/{announcement_id}')
def delete_announcement(announcement_id: int, _: User = Depends(admin_user),
                        db: Session = Depends(get_db)) -> dict:
    row = db.get(Announcement, announcement_id)
    if row is None:
        raise HTTPException(404, 'Announcement not found')
    db.delete(row)
    db.commit()
    return {'ok': True}
