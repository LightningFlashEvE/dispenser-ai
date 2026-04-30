import logging
from difflib import SequenceMatcher

from app.services.asr.lexicon import DomainLexicon

logger = logging.getLogger(__name__)

# ── 模糊匹配参数 ────────────────────────────────────────────────────
MIN_TERM_LEN = 2          # 最小匹配词长（避免单字误匹配）
MAX_TEXT_LEN = 120        # 只处理前 120 字（ASR 结果通常很短）
AUTO_CORRECT_THRESHOLD = 0.82   # 自动纠正阈值
SUGGESTION_THRESHOLD = 0.65     # 建议提示阈值


def fuzzy_normalize(text: str, lexicon: DomainLexicon) -> tuple[str, list[dict], list[dict]]:
    """对文本进行领域热词模糊匹配。

    算法：
    1. 从热词库读取所有多字领域词（药品、配方、设备、动作、别名）
    2. 在文本中滑动窗口扫描，寻找与热词相似的子串
    3. 相似度 >= 0.82：自动纠正并记录 corrections
    4. 0.65 <= 相似度 < 0.82：不自动替换，只记录 suggestions
    5. < 0.65：忽略

    为避免重叠和短词覆盖长词，按匹配位置从后往前替换。

    返回 (normalized_text, corrections, suggestions)
    """
    corrections: list[dict] = []
    suggestions: list[dict] = []

    if not text or len(text) > MAX_TEXT_LEN:
        return text, corrections, suggestions

    terms = lexicon.get_fuzzy_terms()
    # 过滤掉过短的词（单字容易误匹配日常用语）
    terms = [
        (c, d) for c, d in terms if len(c) >= MIN_TERM_LEN or len(d) >= MIN_TERM_LEN
    ]
    # 按标准词长度降序，优先匹配长词
    terms.sort(key=lambda x: len(x[0]), reverse=True)

    # 去重
    seen: set[tuple[str, str]] = set()
    unique_terms: list[tuple[str, str]] = []
    for c, d in terms:
        key = (c, d)
        if key not in seen:
            seen.add(key)
            unique_terms.append((c, d))

    if not unique_terms:
        return text, corrections, suggestions

    max_term_len = max(len(c) for c, _ in unique_terms)
    text_len = len(text)

    # 滑动窗口收集所有候选匹配
    matches: list[tuple[int, int, str, str, float, str]] = []
    i = 0
    while i < text_len:
        best_ratio = 0.0
        best_match: tuple[str, str] | None = None
        best_end = i + 1

        # 从长到短尝试子串
        max_len = min(i + max_term_len + 2, text_len + 1)
        for end in range(max_len, i + MIN_TERM_LEN, -1):
            substring = text[i:end]
            for canonical, display in unique_terms:
                # 长度差异超过 2 时跳过，减少无意义比较
                if abs(len(canonical) - len(substring)) > 2:
                    continue
                # 避免子串包含关系导致的高相似误匹配
                # 例如 "克氯化钠" 包含 "氯化钠"，相似度会很高，
                # 但这属于正常词组组合，不是语音识别错误。
                if canonical in substring or substring in canonical:
                    continue
                ratio = SequenceMatcher(None, substring, canonical).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = (canonical, display)
                    best_end = end

        if best_match and best_ratio >= SUGGESTION_THRESHOLD:
            canonical, display = best_match
            matches.append((i, best_end, text[i:best_end], canonical, best_ratio, display))
            i = best_end  # 跳过已匹配区域，避免子串重复匹配
        else:
            i += 1

    # 按位置从后往前排序，以便安全替换而不影响前面索引
    matches.sort(key=lambda x: x[0], reverse=True)

    normalized = text
    replaced_spans: list[tuple[int, int]] = []

    for start, end, substring, canonical, ratio, display in matches:
        # 避免与已替换区域重叠
        if any(s < end and start < e for s, e in replaced_spans):
            continue

        if ratio >= AUTO_CORRECT_THRESHOLD:
            normalized = normalized[:start] + canonical + normalized[end:]
            replaced_spans.append((start, end))
            corrections.append(
                {
                    "from": substring,
                    "to": canonical,
                    "type": "fuzzy_match",
                    "confidence": round(ratio, 3),
                    "reason": f"与领域热词 '{canonical}' 相似度 {ratio:.2f}，自动纠正",
                }
            )
        elif ratio >= SUGGESTION_THRESHOLD:
            suggestions.append(
                {
                    "text": substring,
                    "candidate": canonical,
                    "confidence": round(ratio, 3),
                    "reason": f"疑似 '{canonical}'（相似度 {ratio:.2f}），请确认",
                }
            )

    return normalized, corrections, suggestions
