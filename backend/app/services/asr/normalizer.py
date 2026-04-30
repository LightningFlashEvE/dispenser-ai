import logging
import re
import time
from typing import Any

from app.services.asr.fuzzy_matcher import fuzzy_normalize
from app.services.asr.lexicon import DomainLexicon
from app.services.asr.number_normalizer import normalize_numbers

logger = logging.getLogger(__name__)

# ── 固定错词替换表（可扩展） ────────────────────────────────────────
FIXED_REPLACEMENTS: dict[str, str] = {
    "录化钠": "氯化钠",
    "氯化拿": "氯化钠",
    "绿化钠": "氯化钠",
    "氯化纳": "氯化钠",
    "NaCl": "氯化钠",
    "nacl": "氯化钠",
    "豪克": "毫克",
    "毛克": "毫克",
    "毫可": "毫克",
    "乘取": "称取",
    "乘去": "称取",
    "撑取": "称取",
    "称去": "称取",
    "配放": "配方",
    "配芳": "配方",
    "天枰": "天平",
    "添平": "天平",
}

# ── 动作词集合（用于 "个 -> 克" 语境判断） ──────────────────────────
ACTION_WORDS = {"称取", "取", "加入", "添加", "倒", "放"}

# ── 默认领域词后缀（用于 "个 -> 克" 语境判断） ─────────────────────
DEFAULT_DOMAIN_WORDS = {
    "氯化钠",
    "葡萄糖",
    "无水乙醇",
    "碳酸氢钠",
    "氯化钾",
    "硫酸铜",
    "氢氧化钠",
    "硝酸银",
    "柠檬酸",
    "维生素C",
    "氯化钙",
}


def _apply_fixed_replacements(text: str) -> tuple[str, list[dict]]:
    """应用固定错词替换表。"""
    corrections: list[dict] = []
    normalized = text

    # 按长度降序排列，避免短词干扰长词（如先替换"钠"再替换"录化钠"会导致问题）
    sorted_items = sorted(
        FIXED_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True
    )

    for wrong, correct in sorted_items:
        if wrong in normalized:
            normalized = normalized.replace(wrong, correct)
            corrections.append(
                {
                    "from": wrong,
                    "to": correct,
                    "type": "fixed_replacement",
                    "confidence": 1.0,
                    "reason": f"固定错词纠正：'{wrong}' 是常见语音识别错误，标准写法为 '{correct}'",
                }
            )

    return normalized, corrections


def _normalize_units(text: str) -> tuple[str, list[dict]]:
    """英文单位归一化为中文单位。"""
    corrections: list[dict] = []
    normalized = text

    # 注意：Python re 默认 Unicode 模式下 \b 将中文字符视为单词字符，
    # 导致 "5g氯化钠" 中 g 与 氯 之间没有单词边界。
    # 使用 (?![a-zA-Z]) 确保后面不再紧跟英文字母即可。
    unit_patterns = [
        (re.compile(r"(\d+(?:\.\d+)?)\s*mg(?![a-zA-Z])"), "毫克"),
        (re.compile(r"(\d+(?:\.\d+)?)\s*kg(?![a-zA-Z])"), "千克"),
        (re.compile(r"(\d+(?:\.\d+)?)\s*ml(?![a-zA-Z])"), "毫升"),
        (re.compile(r"(\d+(?:\.\d+)?)\s*[lL](?![a-zA-Z])"), "升"),
        (re.compile(r"(\d+(?:\.\d+)?)\s*g(?![a-zA-Z])"), "克"),
    ]

    for pattern, cn_unit in unit_patterns:
        def make_repl(unit: str, src_pattern: re.Pattern) -> Any:
            def repl(m: re.Match) -> str:
                num = m.group(1)
                src_unit = src_pattern.pattern.split("\\s*")[-1].replace("\\b", "").replace("[lL]", "L")
                corrections.append(
                    {
                        "from": m.group(0),
                        "to": f"{num}{unit}",
                        "type": "unit_normalization",
                        "confidence": 1.0,
                        "reason": f"单位归一化：英文单位 {src_unit} -> 中文单位 {unit}",
                    }
                )
                return f"{num}{unit}"
            return repl

        normalized = pattern.sub(make_repl(cn_unit, pattern), normalized)

    return normalized, corrections


def _replace_ge_with_context(text: str, lexicon: DomainLexicon | None = None) -> tuple[str, list[dict]]:
    """语境敏感的 '个 -> 克' 替换。

    规则：动作词 + 数字 + 个 + 药品名/领域词
    例如：称取五个氯化钠 -> 称取5克氯化钠
    但：第一个工位 -> 不改；打开第一个配方 -> 不改
    """
    corrections: list[dict] = []
    normalized = text

    # 构建领域词列表
    domain_words = set(DEFAULT_DOMAIN_WORDS)
    if lexicon is not None:
        domain_words.update(lexicon.drugs)
        domain_words.update(lexicon.formulas)
        domain_words.update(lexicon.devices)

    if not domain_words:
        return normalized, corrections

    action_pattern = "|".join(re.escape(a) for a in ACTION_WORDS)
    domain_pattern = "|".join(re.escape(d) for d in domain_words if len(d) >= 2)

    if not action_pattern or not domain_pattern:
        return normalized, corrections

    # 匹配：动作词前缀 + 数字 + 个 + 领域词（正向预查）
    pattern = re.compile(
        rf"((?:{action_pattern}))\s*(\d+(?:\.\d+)?)\s*个(?=\s*(?:{domain_pattern}))"
    )

    def repl(m: re.Match) -> str:
        prefix = m.group(1)
        num = m.group(2)
        corrections.append(
            {
                "from": f"{prefix}{num}个",
                "to": f"{prefix}{num}克",
                "type": "context_aware",
                "confidence": 0.95,
                "reason": "语境纠正：在动作词+数字+个+药品名的语境中，'个'应理解为质量单位'克'",
            }
        )
        return f"{prefix}{num}克"

    normalized = pattern.sub(repl, normalized)
    return normalized, corrections


def normalize_asr_text(
    raw_text: str,
    lexicon: DomainLexicon | None = None,
) -> dict[str, Any]:
    """对 ASR 原始文本进行领域归一化。

    处理流程（按顺序）：
    1. 固定错词替换（最高优先级）
    2. 中文数字归一化
    3. 英文单位归一化
    4. 语境敏感替换（个 -> 克）
    5. 领域热词模糊匹配

    Args:
        raw_text: whisper.cpp 输出的原始文本（已转简体中文）
        lexicon: 领域热词库，若为 None 则跳过模糊匹配

    Returns:
        {
            "raw_text": str,
            "normalized_text": str,
            "corrections": list[dict],
            "suggestions": list[dict],
            "needs_confirmation": bool,
        }
    """
    t0 = time.perf_counter()
    raw_text = raw_text.strip()

    if not raw_text:
        return {
            "raw_text": "",
            "normalized_text": "",
            "corrections": [],
            "suggestions": [],
            "needs_confirmation": False,
        }

    all_corrections: list[dict] = []
    all_suggestions: list[dict] = []

    # 1. 固定错词替换
    text, corrections = _apply_fixed_replacements(raw_text)
    all_corrections.extend(corrections)

    # 2. 中文数字归一化
    text, corrections = normalize_numbers(text)
    all_corrections.extend(corrections)

    # 3. 英文单位归一化
    text, corrections = _normalize_units(text)
    all_corrections.extend(corrections)

    # 4. 语境敏感替换（个 -> 克）
    text, corrections = _replace_ge_with_context(text, lexicon)
    all_corrections.extend(corrections)

    # 5. 领域热词模糊匹配
    if lexicon is not None:
        text, corrections, suggestions = fuzzy_normalize(text, lexicon)
        all_corrections.extend(corrections)
        all_suggestions.extend(suggestions)

    needs_confirmation = bool(all_corrections or all_suggestions)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 日志：按规范记录 ASR 后处理结果
    logger.info(
        "ASR 归一化完成：raw=%r normalized=%r corrections=%d suggestions=%d "
        "lexicon_terms=%d elapsed=%.2fms",
        raw_text,
        text,
        len(all_corrections),
        len(all_suggestions),
        len(lexicon.get_all_terms()) if lexicon else 0,
        elapsed_ms,
    )

    return {
        "raw_text": raw_text,
        "normalized_text": text,
        "corrections": all_corrections,
        "suggestions": all_suggestions,
        "needs_confirmation": needs_confirmation,
    }
