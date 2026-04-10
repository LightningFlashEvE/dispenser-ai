from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.formula import Formula, FormulaStep
from app.schemas.formula import (
    FormulaCreate,
    FormulaRead,
    FormulaSearchResult,
    FormulaStepBase,
    FormulaUpdate,
)

router = APIRouter(prefix="/api/formulas", tags=["配方管理"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


def _fuzzy_score(formula: Formula, keyword: str) -> float:
    kw = keyword.lower().strip()
    if formula.formula_id.lower() == kw:
        return 1.0
    if formula.formula_name.lower() == kw:
        return 0.95
    if formula.formula_id.lower().startswith(kw):
        return 0.9
    if formula.formula_name.lower().startswith(kw):
        return 0.85
    if kw in formula.aliases_list:
        return 0.95
    if any(kw in alias.lower() for alias in formula.aliases_list):
        return 0.7
    if kw in formula.formula_name.lower():
        return 0.5
    return 0.0


@router.get("", response_model=list[FormulaRead])
async def list_formulas(
    db: DBSession,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Formula]:
    stmt = select(Formula).offset(skip).limit(limit).order_by(Formula.formula_name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/search", response_model=list[FormulaSearchResult])
async def search_formulas(
    db: DBSession,
    q: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[dict]:
    stmt = select(Formula)
    result = await db.execute(stmt)
    all_formulas: list[Formula] = list(result.scalars().all())

    scored: list[tuple[Formula, float]] = [
        (f, _fuzzy_score(f, q)) for f in all_formulas
    ]
    scored = [(f, s) for f, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [
        {
            "formula_id": f.formula_id,
            "formula_name": f.formula_name,
            "aliases_list": f.aliases_list,
            "step_count": len(f.steps),
            "score": round(s, 4),
        }
        for f, s in scored[:limit]
    ]


@router.get("/{formula_id}", response_model=FormulaRead)
async def get_formula(db: DBSession, formula_id: str) -> Formula:
    stmt = select(Formula).where(Formula.formula_id == formula_id)
    result = await db.execute(stmt)
    formula = result.scalar_one_or_none()
    if formula is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配方不存在")
    return formula


@router.post("", response_model=FormulaRead, status_code=status.HTTP_201_CREATED)
async def create_formula(db: DBSession, formula_in: FormulaCreate) -> Formula:
    stmt = select(Formula).where(Formula.formula_id == formula_in.formula_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"配方ID {formula_in.formula_id} 已存在",
        )

    formula = Formula(
        formula_id=formula_in.formula_id,
        formula_name=formula_in.formula_name,
        aliases_list=formula_in.aliases_list,
        notes=formula_in.notes,
    )

    for step_in in formula_in.steps:
        step = FormulaStep(
            formula_id=formula.formula_id,
            step_index=step_in.step_index,
            step_name=step_in.step_name,
            command_type=step_in.command_type,
            reagent_code=step_in.reagent_code,
            target_mass_mg=step_in.target_mass_mg,
            tolerance_mg=step_in.tolerance_mg,
            target_vessel=step_in.target_vessel,
        )
        formula.steps.append(step)

    db.add(formula)
    await db.commit()
    await db.refresh(formula)
    return formula


@router.put("/{formula_id}", response_model=FormulaRead)
async def update_formula(
    db: DBSession, formula_id: str, formula_in: FormulaUpdate
) -> Formula:
    stmt = select(Formula).where(Formula.formula_id == formula_id)
    result = await db.execute(stmt)
    formula = result.scalar_one_or_none()
    if formula is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配方不存在")

    if formula_in.formula_name is not None:
        formula.formula_name = formula_in.formula_name
    if formula_in.aliases_list is not None:
        formula.aliases_list = formula_in.aliases_list
    if formula_in.notes is not None:
        formula.notes = formula_in.notes

    if formula_in.steps is not None:
        del_stmt = delete(FormulaStep).where(FormulaStep.formula_id == formula_id)
        await db.execute(del_stmt)
        for step_in in formula_in.steps:
            step = FormulaStep(
                formula_id=formula_id,
                step_index=step_in.step_index,
                step_name=step_in.step_name,
                command_type=step_in.command_type,
                reagent_code=step_in.reagent_code,
                target_mass_mg=step_in.target_mass_mg,
                tolerance_mg=step_in.tolerance_mg,
                target_vessel=step_in.target_vessel,
            )
            formula.steps.append(step)

    formula.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(formula)
    return formula


@router.delete("/{formula_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_formula(db: DBSession, formula_id: str) -> None:
    stmt = delete(Formula).where(Formula.formula_id == formula_id)
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配方不存在")
    await db.commit()
