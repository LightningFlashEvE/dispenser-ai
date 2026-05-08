"""
测试 intent router 优先级和容器提取逻辑
"""
import pytest
from backend.app.services.intent_router import route_intent
from backend.app.services.ai_extractor import AIExtractor
from backend.app.schemas.task_draft_schema import TaskType


def test_weighing_task_not_misclassified_as_bottle_query():
    """任务意图不应被误判为瓶子查询"""
    # 包含"空瓶"但明确是称量任务
    route = route_intent("我要称10g氯化钠到空瓶1", active_draft=None)
    assert route.route == "start_task"
    assert route.task_type == TaskType.WEIGHING

    # 包含"试剂瓶"但明确是分装任务
    route = route_intent("分装到试剂瓶1和试剂瓶2", active_draft=None)
    assert route.route == "start_task"
    assert route.task_type == TaskType.DISPENSING


def test_bottle_query_requires_explicit_query_verb():
    """瓶子查询必须有明确的查询动词"""
    # 明确的查询
    route = route_intent("查看空瓶列表", active_draft=None)
    assert route.route == "query_bottles"

    route = route_intent("有哪些空瓶", active_draft=None)
    assert route.route == "query_bottles"

    route = route_intent("显示试剂瓶管理", active_draft=None)
    assert route.route == "query_bottles"


def test_vessel_extraction_supports_chinese_bottle_format():
    """容器提取应支持"空瓶N"和"试剂瓶N"格式"""
    from backend.app.services.ai_extractor import _extract_with_rules

    # 空瓶1
    patch = _extract_with_rules(TaskType.WEIGHING, "称10g氯化钠到空瓶1")
    assert patch.get("target_vessel") == "空瓶1"

    # 试剂瓶2
    patch = _extract_with_rules(TaskType.WEIGHING, "放到试剂瓶2")
    assert patch.get("target_vessel") == "试剂瓶2"

    # 保持原有格式支持
    patch = _extract_with_rules(TaskType.WEIGHING, "放到A1")
    assert patch.get("target_vessel") == "A1"

    patch = _extract_with_rules(TaskType.WEIGHING, "放到1号工位")
    assert patch.get("target_vessel") == "1号工位"


def test_task_verb_overrides_bottle_noun():
    """任务动词应优先于瓶子名词"""
    # "放到空瓶1" 是任务，不是查询
    route = route_intent("放到空瓶1", active_draft=None)
    assert route.route != "query_bottles"

    # "分装到试剂瓶" 是任务，不是查询
    route = route_intent("分装到试剂瓶", active_draft=None)
    assert route.route != "query_bottles"
