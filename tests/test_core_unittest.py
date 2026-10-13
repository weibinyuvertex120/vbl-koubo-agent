"""
使用 Python 标准库 unittest 进行无外部依赖的核心测试
"""

import unittest
from pathlib import Path

from vbl_koubo.engine.normalizer import (
    normalize_numbers,
    clean_spoken_punctuation,
    split_into_breath_chunks,
    calculate_spoken_metrics,
    _int_to_chinese
)
from vbl_koubo.engine.skill_loader import load_skill_by_name, list_available_skills


class TestVBLKouboCore(unittest.TestCase):

    def test_int_to_chinese(self):
        self.assertEqual(_int_to_chinese("0"), "零")
        self.assertEqual(_int_to_chinese("5"), "五")
        self.assertEqual(_int_to_chinese("15"), "十五")
        self.assertEqual(_int_to_chinese("108"), "一百零八")
        self.assertEqual(_int_to_chinese("1200"), "一千二百")

    def test_normalize_numbers(self):
        # 测试百分比转换
        res = normalize_numbers("OSWorld 2.0 得分 72.6%")
        self.assertIn("百分之七十二点六", res)
        # 测试小数转换
        self.assertIn("二点零", res)
        # 测试整数
        res_int = normalize_numbers("输出 50 美元")
        self.assertIn("五十", res_int)
        # 测试紧跟中文的数字转换与型号年份
        self.assertIn("四零九零显卡", normalize_numbers("搭载 4090显卡"))
        self.assertIn("带来三个优势", normalize_numbers("带来3个优势"))

    def test_clean_spoken_punctuation(self):
        raw = "关键指标如下：准确率（综合）达到 90%；不仅如此——还有新特性。"
        cleaned = clean_spoken_punctuation(raw)
        self.assertNotIn("：", cleaned)
        self.assertNotIn("；", cleaned)
        self.assertNotIn("（", cleaned)
        self.assertNotIn("——", cleaned)

    def test_split_into_breath_chunks(self):
        # 逗号留在行内，只有句号/叹号/问号真正结束才断行
        sentence_with_commas = "这里是VBL，今天我们来看最新发布的模型，重点是把电脑操作放进同一个工作流。"
        chunks = split_into_breath_chunks(sentence_with_commas)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], sentence_with_commas)

        # 真正有多个结束标点的句子才切开
        two_sentences = "第一句讲完了。第二句接着说！"
        chunks_multi = split_into_breath_chunks(two_sentences)
        self.assertEqual(len(chunks_multi), 2)
        self.assertEqual(chunks_multi[0], "第一句讲完了。")
        self.assertEqual(chunks_multi[1], "第二句接着说！")

        # 超过上限且完全没有任何标点停顿的超长句才会被切开，且不自行补逗号
        super_long_no_punct = "这是一句完全没有任何标点符号而且长度超过了三十二个字甚至更长的极端测试文本用于验证切开逻辑"
        chunks_long = split_into_breath_chunks(super_long_no_punct, max_chars=20)
        self.assertGreater(len(chunks_long), 1)
        for c in chunks_long:
            self.assertNotIn("，", c)

    def test_calculate_spoken_metrics(self):
        text = "这里是VBL。本期看GPT六Astra。"
        count, seconds = calculate_spoken_metrics(text, wpm=250)
        self.assertGreater(count, 0)
        self.assertGreater(seconds, 0.0)

    def test_load_skill(self):
        skill = load_skill_by_name("vbl-rational")
        self.assertEqual(skill.name, "vbl-rational")
        self.assertIn("冷静带人看懂", skill.content)
        self.assertEqual(skill.author, "VBL")

    def test_list_skills(self):
        skills = list_available_skills()
        self.assertIn("vbl-rational", skills)
        self.assertNotIn("_template", skills)


if __name__ == "__main__":
    unittest.main()
