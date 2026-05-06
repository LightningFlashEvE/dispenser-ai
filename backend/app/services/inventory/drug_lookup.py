from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.drug import Drug


def fuzzy_score(drug: Drug, keyword: str) -> float:
    kw = keyword.lower().strip()
    if not kw:
        return 0.0

    name_cn = drug.reagent_name_cn.lower()
    name_en = (drug.reagent_name_en or "").lower()
    name_formula = (drug.reagent_name_formula or "").lower()
    aliases_lower = [alias.lower() for alias in drug.aliases_list]

    # exact match on code / name
    if drug.reagent_code.lower() == kw:
        return 1.0
    if name_cn == kw:
        return 0.95

    # prefix match (e.g. "氯化" matches "氯化钠")
    if drug.reagent_code.lower().startswith(kw):
        return 0.9
    if name_cn.startswith(kw):
        return 0.85

    # alias exact / substring
    if kw in aliases_lower:
        return 0.95
    if any(kw in alias for alias in aliases_lower):
        return 0.75

    # keyword as substring of drug fields
    if name_formula and kw in name_formula:
        return 0.7
    if name_en and kw in name_en:
        return 0.6
    if kw in name_cn:
        return 0.5

    # reverse: drug name appears inside the keyword (e.g. "查一下氯化钠库存")
    # require at least 2 chars to avoid false positives on single-char names
    if name_cn and len(name_cn) >= 2 and name_cn in kw:
        return 0.55
    if name_en and len(name_en) >= 2 and name_en in kw:
        return 0.45
    if name_formula and len(name_formula) >= 2 and name_formula in kw:
        return 0.4
    if any(alias in kw for alias in aliases_lower if len(alias) >= 2):
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
