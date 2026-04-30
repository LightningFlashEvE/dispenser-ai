import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 默认内置基础词表（用于测试和数据库不可用时降级） ──────────────────
DEFAULT_DRUG_NAMES = ["氯化钠", "葡萄糖", "无水乙醇", "碳酸氢钠"]
DEFAULT_DRUG_ALIASES = {
    "NaCl": "氯化钠",
    "nacl": "氯化钠",
    "食盐": "氯化钠",
}
DEFAULT_FORMULA_NAMES = ["生理盐水", "缓冲液", "复合维生素溶液"]
DEFAULT_DEVICE_NAMES = ["天平", "机械臂", "摄像头", "工位", "料仓"]
DEFAULT_ACTION_WORDS = [
    "称取",
    "称量",
    "称重",
    "加入",
    "添加",
    "启动",
    "暂停",
    "继续",
    "停止",
    "取消",
    "确认",
    "去皮",
    "归零",
    "初始化",
    "复位",
]
DEFAULT_UNIT_WORDS = ["克", "毫克", "千克", "毫升", "升", "g", "mg", "kg", "ml", "L"]


class DomainLexicon:
    """领域热词库，用于 ASR 后处理纠错。

    热词来源：
    1. 药品库中的药品名称（reagent_name_cn）和别名（aliases_list）
    2. 配方库中的配方名称（formula_name）
    3. 设备配置中的设备名称
    4. 固定动作词和单位词

    后续接入真实数据库：
    - 在应用启动时调用 ``await lexicon.load_from_db()``，传入 AsyncSession
    - 或定期在后台任务中刷新
    - 若数据库模型 ``app.models.drug`` / ``app.models.formula`` 已就绪，
      取消 try/except 包裹，直接使用 ORM 查询
    """

    def __init__(self) -> None:
        self.drugs: list[str] = []
        self.drug_aliases: dict[str, str] = {}
        self.formulas: list[str] = []
        self.devices: list[str] = []
        self.actions: list[str] = []
        self.units: list[str] = []
        self._load_defaults()

    def _load_defaults(self) -> None:
        """加载默认内置词表（仅用于开发和测试，生产环境应优先从数据库读取）。"""
        self.drugs = list(DEFAULT_DRUG_NAMES)
        self.drug_aliases = dict(DEFAULT_DRUG_ALIASES)
        self.formulas = list(DEFAULT_FORMULA_NAMES)
        self.devices = list(DEFAULT_DEVICE_NAMES)
        self.actions = list(DEFAULT_ACTION_WORDS)
        self.units = list(DEFAULT_UNIT_WORDS)

    async def load_from_db(self, db: Any | None = None) -> None:
        """尝试从数据库加载药品和配方热词。

        说明：
        - 当前项目 ``app.models`` 目录可能尚未创建，因此使用 try/except 降级。
        - 若后续 ORM 模型文件已补齐，可移除异常捕获，直接查询。
        - 调用方可选择传入已有的 AsyncSession，否则本方法内部创建。
        """
        from app.core.database import AsyncSessionLocal

        try:
            from app.models.drug import Drug
            from app.models.formula import Formula
        except ImportError as e:
            logger.warning(
                "ASR 热词库无法导入数据库模型（%s），继续使用默认内置词表", e
            )
            return

        session_created = False
        if db is None:
            db = AsyncSessionLocal()
            session_created = True

        try:
            from sqlalchemy import select

            # ── 加载药品名称和别名 ────────────────────────────────
            stmt = select(Drug).where(Drug.is_active == True)  # noqa: E712
            result = await db.execute(stmt)
            drugs_db = result.scalars().all()

            drug_names: list[str] = []
            drug_aliases: dict[str, str] = dict(self.drug_aliases)

            for drug in drugs_db:
                if drug.reagent_name_cn:
                    drug_names.append(drug.reagent_name_cn)
                if drug.reagent_name_en and drug.reagent_name_en != drug.reagent_name_cn:
                    drug_aliases[drug.reagent_name_en] = drug.reagent_name_cn
                if drug.reagent_name_formula and drug.reagent_name_formula != drug.reagent_name_cn:
                    drug_aliases[drug.reagent_name_formula] = drug.reagent_name_cn
                if hasattr(drug, "aliases_list") and drug.aliases_list:
                    for alias in drug.aliases_list:
                        if alias and alias != drug.reagent_name_cn:
                            drug_aliases[alias] = drug.reagent_name_cn

            if drug_names:
                self.drugs = list(dict.fromkeys(drug_names + self.drugs))
            if drug_aliases:
                self.drug_aliases = drug_aliases

            # ── 加载配方名称 ──────────────────────────────────────
            stmt_f = select(Formula)
            result_f = await db.execute(stmt_f)
            formulas_db = result_f.scalars().all()

            formula_names = [f.formula_name for f in formulas_db if f.formula_name]
            if formula_names:
                self.formulas = list(dict.fromkeys(formula_names + self.formulas))

            logger.info(
                "ASR 热词库已从数据库加载：药品=%d 配方=%d 别名=%d",
                len(self.drugs),
                len(self.formulas),
                len(self.drug_aliases),
            )
        except Exception:
            logger.exception("ASR 热词库从数据库加载失败，继续使用默认内置词表")
        finally:
            if session_created:
                await db.close()

    def get_all_terms(self) -> list[str]:
        """获取所有标准热词（不含别名）。"""
        return self.drugs + self.formulas + self.devices + self.actions + self.units

    def get_fuzzy_terms(self) -> list[tuple[str, str]]:
        """获取用于模糊匹配的 (标准词, 显示名) 列表。

        返回别名映射：显示名为别名，标准词为规范名。
        """
        terms: list[tuple[str, str]] = []
        for drug in self.drugs:
            terms.append((drug, drug))
        for formula in self.formulas:
            terms.append((formula, formula))
        for device in self.devices:
            terms.append((device, device))
        for action in self.actions:
            terms.append((action, action))
        for alias, canonical in self.drug_aliases.items():
            terms.append((canonical, alias))
        return terms
