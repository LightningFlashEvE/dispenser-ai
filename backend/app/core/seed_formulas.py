"""Seed database with test formulas."""
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.drug import Drug  # noqa: F401
from app.models.formula import Formula, FormulaStep, _utcnow

logger = logging.getLogger(__name__)

_DEFAULT_FORMULAS = [
    {
        "formula_id": "F001",
        "formula_name": "0.9% 生理盐水",
        "aliases_list": ["NS", "盐水", "生理盐水"],
        "notes": "标准生理盐水配制，单次剂量",
        "steps": [
            {
                "step_index": 1,
                "step_name": "称取氯化钠",
                "command_type": "dispense",
                "reagent_code": "NA001",
                "target_mass_mg": 9000,
                "tolerance_mg": 100,
                "target_vessel": "V01",
            },
        ],
    },
    {
        "formula_id": "F002",
        "formula_name": "复合维生素溶液",
        "aliases_list": ["VC溶液", "维生素配方"],
        "notes": "维生素C + 葡萄糖 + 柠檬酸 混合溶液",
        "steps": [
            {
                "step_index": 1,
                "step_name": "称取维生素C",
                "command_type": "dispense",
                "reagent_code": "NA009",
                "target_mass_mg": 5000,
                "tolerance_mg": 50,
                "target_vessel": "V01",
            },
            {
                "step_index": 2,
                "step_name": "称取葡萄糖",
                "command_type": "dispense",
                "reagent_code": "NA007",
                "target_mass_mg": 15000,
                "tolerance_mg": 200,
                "target_vessel": "V01",
            },
            {
                "step_index": 3,
                "step_name": "称取柠檬酸",
                "command_type": "dispense",
                "reagent_code": "NA008",
                "target_mass_mg": 3000,
                "tolerance_mg": 50,
                "target_vessel": "V01",
            },
        ],
    },
    {
        "formula_id": "F003",
        "formula_name": "缓冲液配方 B",
        "aliases_list": ["PBS", "磷酸缓冲液"],
        "notes": "NaCl + NaHCO3 + KCl 标准缓冲液",
        "steps": [
            {
                "step_index": 1,
                "step_name": "称取氯化钠",
                "command_type": "dispense",
                "reagent_code": "NA001",
                "target_mass_mg": 8000,
                "tolerance_mg": 100,
                "target_vessel": "V01",
            },
            {
                "step_index": 2,
                "step_name": "称取碳酸氢钠",
                "command_type": "dispense",
                "reagent_code": "NA003",
                "target_mass_mg": 2000,
                "tolerance_mg": 30,
                "target_vessel": "V01",
            },
            {
                "step_index": 3,
                "step_name": "称取氯化钾",
                "command_type": "dispense",
                "reagent_code": "NA002",
                "target_mass_mg": 400,
                "tolerance_mg": 10,
                "target_vessel": "V01",
            },
        ],
    },
    {
        "formula_id": "F004",
        "formula_name": "氯化钾注射液",
        "aliases_list": ["KCl注射", "补钾"],
        "notes": "KCl + NaCl 混合注射液",
        "steps": [
            {
                "step_index": 1,
                "step_name": "称取氯化钾",
                "command_type": "dispense",
                "reagent_code": "NA002",
                "target_mass_mg": 3000,
                "tolerance_mg": 50,
                "target_vessel": "V01",
            },
            {
                "step_index": 2,
                "step_name": "称取氯化钠",
                "command_type": "dispense",
                "reagent_code": "NA001",
                "target_mass_mg": 6000,
                "tolerance_mg": 100,
                "target_vessel": "V01",
            },
        ],
    },
    {
        "formula_id": "F005",
        "formula_name": "葡萄糖酸钙混合液",
        "aliases_list": ["补钙配方", "钙溶液"],
        "notes": "CaCl2 + NaCl + 葡萄糖 混合补充液",
        "steps": [
            {
                "step_index": 1,
                "step_name": "称取氯化钙",
                "command_type": "dispense",
                "reagent_code": "NA010",
                "target_mass_mg": 5000,
                "tolerance_mg": 50,
                "target_vessel": "V01",
            },
            {
                "step_index": 2,
                "step_name": "称取氯化钠",
                "command_type": "dispense",
                "reagent_code": "NA001",
                "target_mass_mg": 4000,
                "tolerance_mg": 50,
                "target_vessel": "V01",
            },
            {
                "step_index": 3,
                "step_name": "称取葡萄糖",
                "command_type": "dispense",
                "reagent_code": "NA007",
                "target_mass_mg": 10000,
                "tolerance_mg": 150,
                "target_vessel": "V01",
            },
        ],
    },
]


async def seed_formulas() -> None:
    """仅当数据库为空时，插入默认配方和步骤数据。"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Formula).limit(1))
            existing = result.scalar_one_or_none()
            if existing:
                logger.info("种子检测：配方数据已有记录，跳过插入")
                return

            for fm in _DEFAULT_FORMULAS:
                steps_data = fm.pop("steps")
                formula = Formula(
                    formula_id=fm.pop("formula_id"),
                    formula_name=fm.pop("formula_name"),
                    aliases_list=fm.pop("aliases_list", []),
                    notes=fm.pop("notes", None),
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                session.add(formula)

                for sd in steps_data:
                    step = FormulaStep(
                        formula_id=formula.formula_id,
                        step_index=sd.pop("step_index"),
                        step_name=sd.pop("step_name", None),
                        command_type=sd.pop("command_type"),
                        reagent_code=sd.pop("reagent_code", None),
                        target_mass_mg=sd.pop("target_mass_mg", None),
                        tolerance_mg=sd.pop("tolerance_mg", None),
                        target_vessel=sd.pop("target_vessel", None),
                    )
                    session.add(step)

            await session.commit()
            logger.info("配方种子数据已插入（%d 条）", len(_DEFAULT_FORMULAS))

    except Exception as e:  # noqa: BLE001
        logger.warning("配方种子数据插入失败: %s", e)
