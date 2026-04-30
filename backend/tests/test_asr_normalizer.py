"""
ASR 后处理归一化单元测试

覆盖固定错词替换、数字归一化、单位归一化、语境敏感替换、
领域热词模糊匹配等核心功能。
"""

import pytest

from app.services.asr.lexicon import DomainLexicon
from app.services.asr.normalizer import normalize_asr_text


def _get_lexicon() -> DomainLexicon:
    """获取测试用热词库（默认内置词表）。"""
    return DomainLexicon()


class TestFixedReplacements:
    """固定错词替换测试"""

    def test_lu_hua_na(self):
        """录化钠 -> 氯化钠"""
        r = normalize_asr_text("录化钠", _get_lexicon())
        assert r["normalized_text"] == "氯化钠"
        assert any(c["from"] == "录化钠" and c["to"] == "氯化钠" for c in r["corrections"])

    def test_lu_hua_na2(self):
        """氯化拿 -> 氯化钠"""
        r = normalize_asr_text("氯化拿", _get_lexicon())
        assert r["normalized_text"] == "氯化钠"
        assert any(c["from"] == "氯化拿" for c in r["corrections"])

    def test_lv_hua_na(self):
        """绿化钠 -> 氯化钠"""
        r = normalize_asr_text("绿化钠", _get_lexicon())
        assert r["normalized_text"] == "氯化钠"

    def test_hao_ke(self):
        """豪克 -> 毫克"""
        r = normalize_asr_text("豪克", _get_lexicon())
        assert r["normalized_text"] == "毫克"
        assert any(c["from"] == "豪克" and c["to"] == "毫克" for c in r["corrections"])

    def test_mao_ke(self):
        """毛克 -> 毫克"""
        r = normalize_asr_text("毛克", _get_lexicon())
        assert r["normalized_text"] == "毫克"

    def test_cheng_qu(self):
        """乘取 -> 称取"""
        r = normalize_asr_text("乘取", _get_lexicon())
        assert r["normalized_text"] == "称取"

    def test_pei_fang(self):
        """配放 -> 配方"""
        r = normalize_asr_text("配放", _get_lexicon())
        assert r["normalized_text"] == "配方"

    def test_nacl_upper(self):
        """NaCl -> 氯化钠"""
        r = normalize_asr_text("NaCl", _get_lexicon())
        assert r["normalized_text"] == "氯化钠"

    def test_nacl_lower(self):
        """nacl -> 氯化钠"""
        r = normalize_asr_text("nacl", _get_lexicon())
        assert r["normalized_text"] == "氯化钠"

    def test_cheng_liang(self):
        """成量 -> 称量"""
        r = normalize_asr_text("成量", _get_lexicon())
        assert r["normalized_text"] == "称量"

    def test_chan_liang(self):
        """产量 -> 称量"""
        r = normalize_asr_text("产量", _get_lexicon())
        assert r["normalized_text"] == "称量"

    def test_cheng_zhong(self):
        """成众 -> 称重"""
        r = normalize_asr_text("成众", _get_lexicon())
        assert r["normalized_text"] == "称重"

    def test_cheng_zhong2(self):
        """城重 -> 称重"""
        r = normalize_asr_text("城重", _get_lexicon())
        assert r["normalized_text"] == "称重"

    def test_cheng_qu2(self):
        """成取 -> 称取"""
        r = normalize_asr_text("成取", _get_lexicon())
        assert r["normalized_text"] == "称取"


class TestNumberNormalization:
    """中文数字与单位归一化测试"""

    def test_five_ge_with_drug(self):
        """称取五个氯化钠 -> 称取5克氯化钠"""
        r = normalize_asr_text("称取五个氯化钠", _get_lexicon())
        assert "5克" in r["normalized_text"]
        assert "氯化钠" in r["normalized_text"]
        # 不应残留 "个"
        assert "个" not in r["normalized_text"]

    def test_half_gram(self):
        """称取半克氯化钠 -> 称取0.5克氯化钠"""
        r = normalize_asr_text("称取半克氯化钠", _get_lexicon())
        assert "0.5克" in r["normalized_text"]

    def test_five_point_five(self):
        """称取五点五克录化钠 -> 称取5.5克氯化钠"""
        r = normalize_asr_text("称取五点五克录化钠", _get_lexicon())
        assert "5.5克" in r["normalized_text"]
        assert "氯化钠" in r["normalized_text"]

    def test_fifty_mg(self):
        """称取五十毫克氯化钠 -> 称取50毫克氯化钠"""
        r = normalize_asr_text("称取五十毫克氯化钠", _get_lexicon())
        assert "50毫克" in r["normalized_text"]

    def test_english_unit(self):
        """5g / 5mg 归一化"""
        r = normalize_asr_text("称取5g氯化钠", _get_lexicon())
        assert "5克" in r["normalized_text"]

        r2 = normalize_asr_text("称取5mg氯化钠", _get_lexicon())
        assert "5毫克" in r2["normalized_text"]

    def test_no_change_first_station(self):
        """第一个工位 -> 不改【个】为【克】"""
        r = normalize_asr_text("第一个工位", _get_lexicon())
        # 【个】不应被替换为【克】
        assert "克" not in r["normalized_text"]

    def test_no_change_open_formula(self):
        """打开第一个配方 -> 不改【个】为【克】"""
        r = normalize_asr_text("打开第一个配方", _get_lexicon())
        assert "克" not in r["normalized_text"]

    def test_stop_task(self):
        """停止当前任务 -> 保持正确，不引入错误纠正"""
        r = normalize_asr_text("停止当前任务", _get_lexicon())
        assert "停止" in r["normalized_text"]
        assert "任务" in r["normalized_text"]


class TestDeviceTerms:
    """设备相关术语测试"""

    def test_tian_ping(self):
        """天枰去皮 -> 天平去皮"""
        r = normalize_asr_text("天枰去皮", _get_lexicon())
        assert "天平" in r["normalized_text"]
        assert "去皮" in r["normalized_text"]
        assert "天枰" not in r["normalized_text"]


class TestMetaFields:
    """返回结构元字段测试"""

    def test_raw_text_preserved(self):
        """raw_text 必须保留原始输入"""
        raw = "录化钠"
        r = normalize_asr_text(raw, _get_lexicon())
        assert r["raw_text"] == raw

    def test_needs_confirmation_when_corrected(self):
        """存在纠正时 needs_confirmation 应为 True"""
        r = normalize_asr_text("录化钠", _get_lexicon())
        assert r["needs_confirmation"] is True

    def test_no_confirmation_when_clean(self):
        """无纠正时 needs_confirmation 应为 False"""
        r = normalize_asr_text("你好", _get_lexicon())
        assert r["needs_confirmation"] is False

    def test_empty_input(self):
        """空输入处理"""
        r = normalize_asr_text("", _get_lexicon())
        assert r["normalized_text"] == ""
        assert r["needs_confirmation"] is False


class TestCommandPhrases:
    """固定口令测试清单"""

    @pytest.mark.parametrize(
        "phrase",
        [
            "称取五克氯化钠",
            "称取五点五克氯化钠",
            "称取五十毫克氯化钠",
            "加入二号工位",
            "天平去皮",
            "初始化设备",
            "暂停当前任务",
            "继续当前任务",
            "停止当前任务",
            "打开配方一",
            "删除配方一",
            "查询设备状态",
            "查看最近报警",
            "称取半克葡萄糖",
            "称取五毫克碳酸氢钠",
        ],
    )
    def test_phrases_do_not_crash(self, phrase: str):
        """所有固定口令必须正常处理不抛异常"""
        r = normalize_asr_text(phrase, _get_lexicon())
        assert isinstance(r["normalized_text"], str)
        assert r["raw_text"] == phrase
