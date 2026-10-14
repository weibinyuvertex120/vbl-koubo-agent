"""
vbl-koubo-agent 核心单元测试
测试 Normalizer 正则化安全网与 Skill 加载机制
"""

from pathlib import Path
from vbl_koubo.engine.normalizer import (
    normalize_numbers,
    clean_spoken_punctuation,
    split_into_breath_chunks,
    calculate_spoken_metrics,
    _int_to_chinese
)
from vbl_koubo.engine.skill_loader import load_skill_by_name, list_available_skills


def test_int_to_chinese():
    assert _int_to_chinese("0") == "零"
    assert _int_to_chinese("5") == "五"
    assert _int_to_chinese("15") == "十五"
    assert _int_to_chinese("108") == "一百零八"
    assert _int_to_chinese("1200") == "一千二百"


def test_normalize_numbers():
    # 测试百分比转换
    assert "百分之七十二点六" in normalize_numbers("OSWorld 2.0 得分 72.6%")
    # 测试小数转换
    assert "二点零" in normalize_numbers("版本 2.0")
    # 测试整数
    assert "五十" in normalize_numbers("输出 50 美元")


def test_clean_spoken_punctuation():
    raw = "关键指标如下：准确率（综合）达到 90%；不仅如此——还有新特性。"
    cleaned = clean_spoken_punctuation(raw)
    assert "：" not in cleaned
    assert "；" not in cleaned
    assert "（" not in cleaned
    assert "——" not in cleaned


def test_split_into_breath_chunks():
    long_sentence = "这里是VBL，今天我们来看OpenAI最新发布的模型，重点是把电脑操作和软件工程放进同一个工作流。"
    chunks = split_into_breath_chunks(long_sentence, max_chars=18)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 22  # 切分后的块不超标


def test_calculate_spoken_metrics():
    text = "这里是VBL。本期看GPT六Astra。"
    count, seconds = calculate_spoken_metrics(text, wpm=250)
    assert count > 0
    assert seconds > 0.0


def test_load_skill():
    skill = load_skill_by_name("vbl-rational")
    assert skill.name == "vbl-rational"
    assert "冷静带人看懂" in skill.content
    assert skill.author == "VBL"


def test_list_skills():
    skills = list_available_skills()
    assert "vbl-rational" in skills
    assert "_template" not in skills  # 确保排除了模板目录

def test_slugify_preserves_decomposed_unicode_characters():
    from run import slugify

    assert slugify('Cafe\u0301') == 'Café'

