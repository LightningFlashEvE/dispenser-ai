"""Seed database with default drugs for testing."""
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.drug import Drug, _utcnow

logger = logging.getLogger(__name__)

_DEFAULT_DRUGS = [
    {
        "reagent_code": "NA001",
        "reagent_name_cn": "氯化钠",
        "reagent_name_en": "Sodium Chloride",
        "reagent_name_formula": "NaCl",
        "aliases_list": ["食盐", "盐"],
        "cas_number": "7647-14-5",
        "purity_grade": "AR",
        "molar_weight_g_mol": 58.44,
        "density_g_cm3": 2.165,
        "station_id": "ST01",
        "stock_mg": 50000,
        "notes": "常用基准试剂",
    },
    {
        "reagent_code": "NA002",
        "reagent_name_cn": "氯化钾",
        "reagent_name_en": "Potassium Chloride",
        "reagent_name_formula": "KCl",
        "aliases_list": ["钾盐"],
        "cas_number": "7447-40-7",
        "purity_grade": "AR",
        "molar_weight_g_mol": 74.55,
        "density_g_cm3": 1.984,
        "station_id": "ST02",
        "stock_mg": 30000,
        "notes": "电解质补充",
    },
    {
        "reagent_code": "NA003",
        "reagent_name_cn": "碳酸氢钠",
        "reagent_name_en": "Sodium Bicarbonate",
        "reagent_name_formula": "NaHCO3",
        "aliases_list": ["小苏打", "重碳酸钠"],
        "cas_number": "144-55-8",
        "purity_grade": "AR",
        "molar_weight_g_mol": 84.01,
        "density_g_cm3": 2.20,
        "station_id": "ST03",
        "stock_mg": 80000,
        "notes": "常用缓冲剂",
    },
    {
        "reagent_code": "NA004",
        "reagent_name_cn": "硫酸铜",
        "reagent_name_en": "Copper Sulfate",
        "reagent_name_formula": "CuSO4·5H2O",
        "aliases_list": ["蓝矾", "胆矾"],
        "cas_number": "7758-99-8",
        "purity_grade": "AR",
        "molar_weight_g_mol": 249.68,
        "density_g_cm3": 2.284,
        "station_id": "ST04",
        "stock_mg": 20000,
        "notes": "蓝色晶体，有毒",
    },
    {
        "reagent_code": "NA005",
        "reagent_name_cn": "氢氧化钠",
        "reagent_name_en": "Sodium Hydroxide",
        "reagent_name_formula": "NaOH",
        "aliases_list": ["烧碱", "苛性钠"],
        "cas_number": "1310-73-2",
        "purity_grade": "AR",
        "molar_weight_g_mol": 40.00,
        "density_g_cm3": 2.130,
        "station_id": "ST05",
        "stock_mg": 40000,
        "notes": "强碱，腐蚀性",
    },
    {
        "reagent_code": "NA006",
        "reagent_name_cn": "硝酸银",
        "reagent_name_en": "Silver Nitrate",
        "reagent_name_formula": "AgNO3",
        "aliases_list": ["银盐"],
        "cas_number": "7761-88-8",
        "purity_grade": "AR",
        "molar_weight_g_mol": 169.87,
        "density_g_cm3": 4.350,
        "station_id": "ST06",
        "stock_mg": 5000,
        "notes": "见光分解，棕色瓶保存",
    },
    {
        "reagent_code": "NA007",
        "reagent_name_cn": "葡萄糖",
        "reagent_name_en": "Glucose",
        "reagent_name_formula": "C6H12O6",
        "aliases_list": ["右旋糖"],
        "cas_number": "50-99-7",
        "purity_grade": "AR",
        "molar_weight_g_mol": 180.16,
        "density_g_cm3": 1.540,
        "station_id": "ST07",
        "stock_mg": 100000,
        "notes": "生物培养基常用",
    },
    {
        "reagent_code": "NA008",
        "reagent_name_cn": "柠檬酸",
        "reagent_name_en": "Citric Acid",
        "reagent_name_formula": "C6H8O7",
        "aliases_list": ["枸橼酸"],
        "cas_number": "77-92-9",
        "purity_grade": "AR",
        "molar_weight_g_mol": 192.12,
        "density_g_cm3": 1.665,
        "station_id": "ST08",
        "stock_mg": 60000,
        "notes": "食品级添加剂",
    },
    {
        "reagent_code": "NA009",
        "reagent_name_cn": "维生素C",
        "reagent_name_en": "Vitamin C",
        "reagent_name_formula": "C6H8O6",
        "aliases_list": ["抗坏血酸", "抗坏血酸钠"],
        "cas_number": "50-81-7",
        "purity_grade": "AR",
        "molar_weight_g_mol": 176.12,
        "density_g_cm3": 1.650,
        "station_id": "ST09",
        "stock_mg": 15000,
        "notes": "易氧化变黄",
    },
    {
        "reagent_code": "NA010",
        "reagent_name_cn": "氯化钙",
        "reagent_name_en": "Calcium Chloride",
        "reagent_name_formula": "CaCl2",
        "aliases_list": ["干燥剂"],
        "cas_number": "10043-52-4",
        "purity_grade": "AR",
        "molar_weight_g_mol": 110.98,
        "density_g_cm3": 2.150,
        "station_id": "ST10",
        "stock_mg": 25000,
        "notes": "强吸湿性，常用干燥剂",
    },
]


async def seed_database() -> None:
    """仅当数据库为空时，插入默认药品数据。"""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Drug).limit(1))
            existing = result.scalar_one_or_none()
            if existing:
                logger.info("种子检测：数据库已有数据，跳过插入")
                return

            for data in _DEFAULT_DRUGS:
                drug = Drug(
                    is_active=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                    **{k: v for k, v in data.items() if k not in ("is_active", "created_at", "updated_at")},
                )
                session.add(drug)

            await session.commit()
            logger.info("种子数据已插入（%d 条药品记录）", len(_DEFAULT_DRUGS))

    except Exception as e:
        logger.warning("种子数据插入失败: %s", e)
