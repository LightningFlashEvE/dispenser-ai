from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.drug import Drug
from app.schemas.drug import DrugCreate, DrugRead, DrugSearchResult, DrugUpdate

router = APIRouter(prefix="/api/drugs", tags=["药品管理"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


def _fuzzy_score(drug: Drug, keyword: str) -> float:
    kw = keyword.lower().strip()
    if drug.reagent_code.lower() == kw:
        return 1.0
    if drug.reagent_name_cn.lower() == kw:
        return 0.95
    if drug.reagent_code.lower().startswith(kw):
        return 0.9
    if drug.reagent_name_cn.lower().startswith(kw):
        return 0.85
    if kw in drug.aliases_list:
        return 0.95
    if any(kw in alias.lower() for alias in drug.aliases_list):
        return 0.75
    if drug.reagent_name_formula and kw in drug.reagent_name_formula.lower():
        return 0.7
    if drug.reagent_name_en and kw in drug.reagent_name_en.lower():
        return 0.6
    if kw in drug.reagent_name_cn.lower():
        return 0.5
    return 0.0


@router.get("", response_model=list[DrugRead])
async def list_drugs(
    db: DBSession,
    active_only: bool = True,
    station_id: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Drug]:
    stmt = select(Drug)
    if active_only:
        stmt = stmt.where(Drug.is_active == True)  # noqa: E712
    if station_id is not None:
        stmt = stmt.where(Drug.station_id == station_id)
    stmt = stmt.offset(skip).limit(limit).order_by(Drug.reagent_name_cn)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/search", response_model=list[DrugSearchResult])
async def search_drugs(
    db: DBSession,
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    stmt = select(Drug).where(Drug.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    all_drugs: list[Drug] = list(result.scalars().all())

    scored: list[tuple[Drug, float]] = [
        (d, _fuzzy_score(d, q)) for d in all_drugs
    ]
    scored = [(d, s) for d, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [
        {
            "reagent_code": d.reagent_code,
            "reagent_name_cn": d.reagent_name_cn,
            "reagent_name_en": d.reagent_name_en,
            "reagent_name_formula": d.reagent_name_formula,
            "purity_grade": d.purity_grade,
            "station_id": d.station_id,
            "stock_mg": d.stock_mg,
            "score": round(s, 4),
        }
        for d, s in scored[:limit]
    ]


@router.get("/{reagent_code}", response_model=DrugRead)
async def get_drug(db: DBSession, reagent_code: str) -> Drug:
    stmt = select(Drug).where(Drug.reagent_code == reagent_code)
    result = await db.execute(stmt)
    drug = result.scalar_one_or_none()
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在")
    return drug


@router.post("", response_model=DrugRead, status_code=status.HTTP_201_CREATED)
async def create_drug(db: DBSession, drug_in: DrugCreate) -> Drug:
    stmt = select(Drug).where(Drug.reagent_code == drug_in.reagent_code)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"药品编号 {drug_in.reagent_code} 已存在",
        )

    drug = Drug(
        reagent_code=drug_in.reagent_code,
        reagent_name_cn=drug_in.reagent_name_cn,
        reagent_name_en=drug_in.reagent_name_en,
        reagent_name_formula=drug_in.reagent_name_formula,
        aliases_list=drug_in.aliases_list,
        cas_number=drug_in.cas_number,
        purity_grade=drug_in.purity_grade,
        molar_weight_g_mol=drug_in.molar_weight_g_mol,
        density_g_cm3=drug_in.density_g_cm3,
        station_id=drug_in.station_id,
        stock_mg=drug_in.stock_mg,
        notes=drug_in.notes,
    )
    db.add(drug)
    await db.commit()
    await db.refresh(drug)
    return drug


@router.put("/{reagent_code}", response_model=DrugRead)
async def update_drug(
    db: DBSession, reagent_code: str, drug_in: DrugUpdate
) -> Drug:
    stmt = select(Drug).where(Drug.reagent_code == reagent_code)
    result = await db.execute(stmt)
    drug = result.scalar_one_or_none()
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在")

    update_data = drug_in.model_dump(exclude_unset=True)
    # aliases_list 需要特殊处理
    if "aliases_list" in update_data:
        drug.aliases_list = update_data.pop("aliases_list")  # type: ignore[assignment]

    for field, value in update_data.items():
        setattr(drug, field, value)

    drug.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(drug)
    return drug


@router.delete("/{reagent_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drug(db: DBSession, reagent_code: str) -> None:
    stmt = (
        update(Drug)
        .where(Drug.reagent_code == reagent_code)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在")
    await db.commit()


@router.patch("/{reagent_code}/stock", response_model=DrugRead)
async def adjust_stock(
    db: DBSession, reagent_code: str, delta_mg: int
) -> Drug:
    stmt = select(Drug).where(Drug.reagent_code == reagent_code)
    result = await db.execute(stmt)
    drug = result.scalar_one_or_none()
    if drug is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="药品不存在")

    new_stock = drug.stock_mg + delta_mg
    if new_stock < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"库存不足：当前 {drug.stock_mg} mg，尝试扣减 {abs(delta_mg)} mg",
        )

    drug.stock_mg = new_stock
    drug.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(drug)
    return drug
