from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class ChemicalCandidate:
    chemical_id: str
    display_name: str
    cas_no: str | None
    grade: str | None
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


_CATALOG = [
    {
        "chemical_id": "CHEM_NACL_AR_001",
        "display_name": "氯化钠",
        "cas_no": "7647-14-5",
        "grade": "分析纯",
        "aliases": ["NaCl", "食盐", "盐"],
    },
    {
        "chemical_id": "CHEM_KCL_AR_001",
        "display_name": "氯化钾",
        "cas_no": "7447-40-7",
        "grade": "分析纯",
        "aliases": ["KCl", "钾盐"],
    },
    {
        "chemical_id": "CHEM_GLUCOSE_AR_001",
        "display_name": "葡萄糖",
        "cas_no": "50-99-7",
        "grade": "分析纯",
        "aliases": ["Glucose", "右旋糖"],
    },
    {
        "chemical_id": "CHEM_ETHANOL_AR_001",
        "display_name": "乙醇",
        "cas_no": "64-17-5",
        "grade": "分析纯",
        "aliases": ["酒精", "Ethanol"],
    },
    {
        "chemical_id": "CHEM_ETHANOL_STD_001",
        "display_name": "乙醇",
        "cas_no": "64-17-5",
        "grade": "标准品",
        "aliases": ["酒精标准品", "Ethanol standard"],
    },
]

HIGH_CONFIDENCE_THRESHOLD = 0.9


def lookup_chemical_candidates(name_text: str | None) -> list[ChemicalCandidate]:
    query = (name_text or "").strip()
    if not query:
        return []

    candidates: list[ChemicalCandidate] = []
    query_lower = query.lower()
    for item in _CATALOG:
        display_name = item["display_name"]
        aliases = item.get("aliases", [])
        confidence = _score(query_lower, display_name, aliases)
        if confidence <= 0:
            continue
        candidates.append(
            ChemicalCandidate(
                chemical_id=item["chemical_id"],
                display_name=display_name,
                cas_no=item.get("cas_no"),
                grade=item.get("grade"),
                confidence=confidence,
            )
        )

    candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
    return candidates


def select_candidate_by_id(
    candidates: list[dict],
    chemical_id: str,
) -> dict | None:
    wanted = chemical_id.strip().lower()
    return next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("chemical_id", "")).lower() == wanted
        ),
        None,
    )


def select_candidate_by_index(
    candidates: list[dict],
    index: int,
) -> dict | None:
    if index < 0 or index >= len(candidates):
        return None
    return candidates[index]


def _score(query_lower: str, display_name: str, aliases: list[str]) -> float:
    name_lower = display_name.lower()
    if query_lower == name_lower:
        return 0.94
    if query_lower in [alias.lower() for alias in aliases]:
        return 0.93
    if name_lower in query_lower or query_lower in name_lower:
        return 0.72
    alias_substring = any(
        alias.lower() in query_lower or query_lower in alias.lower()
        for alias in aliases
        if alias
    )
    if alias_substring:
        return 0.68
    ratio = SequenceMatcher(None, query_lower, name_lower).ratio()
    return round(ratio * 0.6, 4) if ratio >= 0.75 else 0.0
