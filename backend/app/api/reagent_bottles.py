from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, select
from sqlalchemy import Integer as SAInteger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.drug import Drug
from app.models.reagent_bottle import ReagentBottle
from app.schemas.reagent_bottle import ReagentBottleCreate, ReagentBottleRead, ReagentBottleUpdate

router = APIRouter(prefix="/api/reagent-bottles", tags=["试剂瓶管理"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def _enrich_bottle_read(db: AsyncSession, bottle: ReagentBottle) -> ReagentBottleRead:
    reagent_name_cn: str | None = None
    if bottle.reagent_code:
        stmt = select(Drug.reagent_name_cn).where(Drug.reagent_code == bottle.reagent_code)
        result = await db.execute(stmt)
        name_row = result.scalar_one_or_none()
        if name_row:
            reagent_name_cn = name_row

    data = {
        "bottle_id": bottle.bottle_id,
        "station_id": bottle.station_id,
        "reagent_code": bottle.reagent_code,
        "reagent_name_cn": reagent_name_cn,
        "label": bottle.label,
        "status": bottle.status,
        "volume_ml": bottle.volume_ml,
        "fill_date": bottle.fill_date,
        "notes": bottle.notes,
        "is_active": bottle.is_active,
        "created_at": bottle.created_at,
        "updated_at": bottle.updated_at,
    }
    return ReagentBottleRead.model_validate(data)


@router.get("", response_model=list[ReagentBottleRead])
async def list_bottles(
    db: DBSession,
    status_filter: str | None = Query(default=None, alias="status"),
    station_id: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ReagentBottleRead]:
    stmt = select(ReagentBottle)
    if status_filter is not None:
        stmt = stmt.where(ReagentBottle.status == status_filter)
    if station_id is not None:
        stmt = stmt.where(ReagentBottle.station_id == station_id)
    stmt = stmt.offset(skip).limit(limit).order_by(cast(ReagentBottle.bottle_id, SAInteger))
    result = await db.execute(stmt)
    bottles = list(result.scalars().all())
    enriched: list[ReagentBottleRead] = []
    for b in bottles:
        enriched.append(await _enrich_bottle_read(db, b))
    return enriched


@router.get("/{bottle_id}", response_model=ReagentBottleRead)
async def get_bottle(db: DBSession, bottle_id: str) -> ReagentBottleRead:
    stmt = select(ReagentBottle).where(ReagentBottle.bottle_id == bottle_id)
    result = await db.execute(stmt)
    bottle = result.scalar_one_or_none()
    if bottle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="试剂瓶不存在")
    return await _enrich_bottle_read(db, bottle)


@router.post("", response_model=ReagentBottleRead, status_code=status.HTTP_201_CREATED)
async def create_bottle(db: DBSession, body: ReagentBottleCreate) -> ReagentBottleRead:
    stmt = select(ReagentBottle).where(ReagentBottle.bottle_id == body.bottle_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"试剂瓶 {body.bottle_id} 已存在",
        )

    bottle = ReagentBottle(
        bottle_id=body.bottle_id,
        station_id=body.station_id,
        reagent_code=body.reagent_code,
        label=body.label,
        status=body.status,
        volume_ml=body.volume_ml,
        notes=body.notes,
    )
    db.add(bottle)
    await db.commit()
    await db.refresh(bottle)
    return await _enrich_bottle_read(db, bottle)


@router.put("/{bottle_id}", response_model=ReagentBottleRead)
async def update_bottle(db: DBSession, bottle_id: str, body: ReagentBottleUpdate) -> ReagentBottleRead:
    stmt = select(ReagentBottle).where(ReagentBottle.bottle_id == bottle_id)
    result = await db.execute(stmt)
    bottle = result.scalar_one_or_none()
    if bottle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="试剂瓶不存在")

    update_data = body.model_dump(exclude_unset=True)
    if "fill_date" not in update_data and body.status == "filled" and bottle.status != "filled":
        update_data["fill_date"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(bottle, field, value)
    bottle.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(bottle)
    return await _enrich_bottle_read(db, bottle)


@router.delete("/{bottle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bottle(db: DBSession, bottle_id: str) -> None:
    stmt = select(ReagentBottle).where(ReagentBottle.bottle_id == bottle_id)
    result = await db.execute(stmt)
    bottle = result.scalar_one_or_none()
    if bottle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="试剂瓶不存在")
    bottle.is_active = False
    bottle.updated_at = datetime.now(timezone.utc)
    await db.commit()
