"""化学计算服务。

Windows 开发阶段：按需计算摩尔质量、密度换算。
Jetson 部署阶段：相同逻辑，无平台差异。
"""

from typing import Any


def mass_to_moles(mass_mg: int, molar_weight_g_mol: float) -> float:
    if molar_weight_g_mol <= 0:
        raise ValueError(f"摩尔质量必须为正数，得到 {molar_weight_g_mol}")
    return (mass_mg / 1000.0) / molar_weight_g_mol


def moles_to_mass(moles: float, molar_weight_g_mol: float) -> int:
    """摩尔数 → 质量(mg) 整数."""
    return int(round(moles * molar_weight_g_mol * 1000))


def calc_mass_by_fraction(total_mass_mg: int, fraction: float) -> int:
    """按质量分数计算组分质量(mg) 整数."""
    return int(round(total_mass_mg * fraction))


def calc_mix_components(
    total_mass_mg: int,
    ratio_type: str,
    components: list[dict[str, Any]],
    molar_weights: dict[str, float],
) -> list[dict[str, Any]]:
    """计算混合配方中各组分的目标质量(mg)。

    mass_fraction: 直接按占比分配
    molar_fraction: 先转质量占比，再分配
    """
    if ratio_type == "molar_fraction":
        total_molar_mass = sum(
            c.get("fraction", 0) * molar_weights.get(c.get("raw_text", ""), 1.0)
            for c in components
        )
        if total_molar_mass <= 0:
            raise ValueError("摩尔分数换算失败：加权摩尔质量总和为 0（检查 fraction 和 molar_weight）")
        mass_fractions = []
        for c in components:
            raw = c.get("raw_text", "")
            mw = molar_weights.get(raw, 1.0)
            mass_fractions.append((c["fraction"] * mw) / total_molar_mass)
    else:
        mass_fractions = [c.get("fraction", 0) for c in components]

    result = []
    for i, c in enumerate(components):
        result.append({
            **c,
            "target_mass_mg": calc_mass_by_fraction(total_mass_mg, mass_fractions[i]),
        })
    return result
