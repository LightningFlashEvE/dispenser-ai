import logging
import re

logger = logging.getLogger(__name__)

# ── 中文数字映射 ────────────────────────────────────────────────────
CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

CN_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
}

# ── 单位归一化映射（常见错词 -> 标准词） ────────────────────────────
UNIT_NORMALIZATION = {
    "豪克": "毫克",
    "毛克": "毫克",
    "毫可": "毫克",
}

# 中文数字字符集（用于正则）
CN_NUM_CHARS = r"[一二两三四五六七八九十百千万亿点零半]"


def _parse_cn_number(cn: str) -> float | None:
    """将纯中文数字字符串解析为浮点数。

    支持：
    - 单个数字：一、二、两...
    - 组合数字：二十、五十、一百二十三
    - 小数：五点五、零点五
    - 特殊：半 -> 0.5
    """
    if not cn:
        return None

    if cn == "半":
        return 0.5

    # 处理小数（仅支持一个小数点）
    if "点" in cn:
        parts = cn.split("点", 1)
        int_part = _parse_cn_number(parts[0])
        if int_part is None:
            return None
        frac_str = parts[1]
        frac_val = 0.0
        for i, ch in enumerate(frac_str):
            if ch not in CN_DIGITS:
                return None
            frac_val += CN_DIGITS[ch] * (10 ** -(i + 1))
        return int_part + frac_val

    total = 0
    current = 0
    for ch in cn:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            if current == 0:
                current = 1
            total += current * CN_UNITS[ch]
            current = 0
        else:
            # 遇到无法解析的字符，整体失败
            return None
    total += current
    return total


def normalize_numbers(text: str) -> tuple[str, list[dict]]:
    """将文本中的中文数字归一化为阿拉伯数字。

    处理策略：
    1. 先匹配中文数字+单位的组合，整体替换
    2. 再匹配独立的中文数字（允许空格）
    3. 常见错词单位替换（豪克->毫克等）

    返回 (normalized_text, corrections)
    """
    corrections: list[dict] = []
    normalized = text

    # ── 阶段 1：中文数字 + 英文/中文单位 组合 ─────────────────────
    # 匹配模式：连续中文数字 + 可选空格 + 单位后缀
    pattern_with_unit = re.compile(
        rf"({CN_NUM_CHARS}+)\s*([gG毫克千克升毫升mMkK][gGlL]?)"
    )

    def _replace_with_unit(m: re.Match) -> str:
        num_str = m.group(1)
        unit_str = m.group(2)
        num_val = _parse_cn_number(num_str)
        if num_val is None:
            return m.group(0)

        # 单位归一化（英文单位 -> 中文单位）
        unit_lower = unit_str.lower()
        unit_norm_map = {
            "g": "克",
            "mg": "毫克",
            "kg": "千克",
            "ml": "毫升",
            "l": "升",
        }
        normalized_unit = unit_norm_map.get(unit_lower, unit_str)

        corrections.append(
            {
                "from": m.group(0),
                "to": f"{num_val}{normalized_unit}",
                "type": "number_unit",
                "confidence": 1.0,
                "reason": f"中文数字归一化：{num_str} -> {num_val}，单位归一化：{unit_str} -> {normalized_unit}",
            }
        )
        return f"{num_val}{normalized_unit}"

    normalized = pattern_with_unit.sub(_replace_with_unit, normalized)

    # ── 阶段 2：常见错词单位替换（不依赖数字） ────────────────────
    for wrong, correct in sorted(
        UNIT_NORMALIZATION.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if wrong in normalized:
            normalized = normalized.replace(wrong, correct)
            corrections.append(
                {
                    "from": wrong,
                    "to": correct,
                    "type": "unit_correction",
                    "confidence": 1.0,
                    "reason": f"单位错词纠正：'{wrong}' -> '{correct}'",
                }
            )

    # ── 阶段 3：独立中文数字（尚未被前面阶段处理的） ──────────────
    # 简单策略：查找仍留在文本中的中文数字串
    pattern_standalone = re.compile(rf"{CN_NUM_CHARS}+")

    def _replace_standalone(m: re.Match) -> str:
        num_str = m.group(0)
        num_val = _parse_cn_number(num_str)
        if num_val is None:
            return num_str
        corrections.append(
            {
                "from": num_str,
                "to": str(num_val),
                "type": "number",
                "confidence": 1.0,
                "reason": f"中文数字归一化：{num_str} -> {num_val}",
            }
        )
        return str(num_val)

    normalized = pattern_standalone.sub(_replace_standalone, normalized)

    return normalized, corrections
