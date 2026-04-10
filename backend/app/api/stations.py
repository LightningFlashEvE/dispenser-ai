from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.station import Station
from app.schemas.station import StationRead, StationUpdate

router = APIRouter(prefix="/api/stations", tags=["工位管理"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[StationRead])
async def list_stations(
    db: DBSession,
    occupied_only: bool = False,
    has_bottle: bool | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Station]:
    stmt = select(Station)
    if occupied_only:
        stmt = stmt.where(Station.is_occupied == True)  # noqa: E712
    if has_bottle is not None:
        stmt = stmt.where(Station.has_bottle == has_bottle)
    stmt = stmt.offset(skip).limit(limit).order_by(Station.station_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/free", response_model=list[StationRead])
async def list_free_stations(db: DBSession) -> list[Station]:
    """返回当前空闲（无容器占用）的工位列表，供视觉层和规则引擎使用。"""
    stmt = select(Station).where(Station.is_occupied == False).order_by(Station.station_id)  # noqa: E712
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{station_id}", response_model=StationRead)
async def get_station(db: DBSession, station_id: str) -> Station:
    stmt = select(Station).where(Station.station_id == station_id)
    result = await db.execute(stmt)
    station = result.scalar_one_or_none()
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工位不存在")
    return station


@router.patch("/{station_id}", response_model=StationRead)
async def update_station(
    db: DBSession, station_id: str, station_in: StationUpdate
) -> Station:

    stmt = select(Station).where(Station.station_id == station_id)
    result = await db.execute(stmt)
    station = result.scalar_one_or_none()
    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工位不存在")

    update_data = station_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(station, field, value)
    station.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(station)
    return station


@router.post("", response_model=StationRead, status_code=status.HTTP_201_CREATED)
async def create_station(db: DBSession, station_in: StationRead) -> Station:
    """手动注册工位。station_id 唯一。"""
    stmt = select(Station).where(Station.station_id == station_in.station_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"工位 {station_in.station_id} 已存在",
        )

    station = Station(station_id=station_in.station_id)
    for field, value in station_in.model_dump().items():
        if field != "station_id" and value is not None:
            setattr(station, field, value)

    db.add(station)
    await db.commit()
    await db.refresh(station)
    return station
