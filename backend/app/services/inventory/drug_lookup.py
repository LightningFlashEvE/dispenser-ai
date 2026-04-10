from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.drug import Drug


def fuzzy_score(drug: Drug, keyword: str) -> float:
    kw = keyword.lower().strip()
    if not kw:
        return 0.0
    if drug.reagent_code.lower() == kw:
        return 1.0
    if drug.reagent_name_cn.lower() == kw:
        return 0.95
    if drug.reagent_code.lower().startswith(kw):
        return 0.9
    if drug.reagent_name_cn.lower().startswith(kw):
        return 0.85
    aliases_lower = [alias.lower() for alias in drug.aliases_list]
    if kw in aliases_lower:
        return 0.95
    if any(kw in alias for alias in aliases_lower):
        return 0.75
    if drug.reagent_name_formula and kw in drug.reagent_name_formula.lower():
        return 0.7
    if drug.reagent_name_en and kw in drug.reagent_name_en.lower():
        return 0.6
    if kw in drug.reagent_name_cn.lower():
        return 0.5
    return 0.0


async def find_best_drug(keyword: str | None) -> tuple[Drug | None, float]:
    if not keyword:
        return None, 0.0
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Drug).where(Drug.is_active == True))
        drugs = list(result.scalars().all())
    if not drugs:
        return None, 0.0
    best_drug: Drug | None = None
    best_score = 0.0
    for drug in drugs:
        score = fuzzy_score(drug, keyword)
        if score > best_score:
            best_drug = drug
            best_score = score
    return best_drug, best_score


def drug_to_dict(drug: Drug) -> dict:
    return {
        "reagent_code": drug.reagent_code,
        "reagent_name_cn": drug.reagent_name_cn,
        "reagent_name_en": drug.reagent_name_en,
        "reagent_name_formula": drug.reagent_name_formula,
        "purity_grade": drug.purity_grade,
        "station_id": drug.station_id,
        "molar_weight_g_mol": drug.molar_weight_g_mol,
        "stock_mg": drug.stock_mg,
        "notes": drug.notes,
    }
