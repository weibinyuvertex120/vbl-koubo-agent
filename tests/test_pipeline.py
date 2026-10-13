"""
Pipeline 编排与质检单元测试
"""

import unittest
from vbl_koubo.pipeline.checker import run_quality_gate, check_forbidden_words
from vbl_koubo.pipeline.orchestrator import KouboOrchestrator


class TestPipeline(unittest.TestCase):

    def test_forbidden_words_detection(self):
        bad_text = "综上所述，在这个快节奏的时代，这个技术太炸裂了，毫无疑问不仅如此。"
        violations = check_forbidden_words(bad_text)
        self.assertIn("综上所述", violations)
        self.assertIn("快节奏的时代", violations)
        self.assertIn("太炸裂了", violations)
        self.assertIn("毫无疑问", violations)

    def test_quality_gate_sanitization(self):
        text_with_crap = "总而言之，我们需要关注事实。鉴于此，先看数据。"
        res = run_quality_gate(text_with_crap)
        self.assertNotIn("总而言之", res.clean_text)
        self.assertIn("所以，先看数据", res.clean_text)

    def test_orchestrator_generate_hooks(self):
        orch = KouboOrchestrator(skill_name="vbl-rational")
        facts = "产品更新：GPT-6 发布，OSWorld 得分 72.6%"
        hooks = orch.generate_hooks(facts)
        self.assertEqual(len(hooks), 3)
        types = [h.type for h in hooks]
        self.assertIn("H", types)
        self.assertIn("K", types)
        self.assertIn("R", types)

    def test_extract_json_from_markdown_fence(self):
        # 测试防崩溃提取：带 markdown ```json 围栏的大模型返回
        from vbl_koubo.pipeline.orchestrator import extract_json_from_response
        wrapped_json = "```json\n{\"hooks\": [{\"type\": \"H\", \"label\": \"测试\", \"text\": \"文案\", \"rationale\": \"意图\"}]}\n```"
        data = extract_json_from_response(wrapped_json)
        self.assertIsNotNone(data)
        self.assertIn("hooks", data)
        self.assertEqual(data["hooks"][0]["type"], "H")

    def test_orchestrator_build_teleprompter(self):
        orch = KouboOrchestrator(skill_name="vbl-rational")
        hook = "这里是VBL。先看一组确凿证据。"
        body = "官方页面显示，得分达到 72.6%，价格为 10 美元。先看页面证据，再决定它适不适合你的工作流。"
        script = orch.build_teleprompter_script("GPT-6评测", hook, body)

        self.assertIn("百分之七十二点六", script.clean_voice_text)
        self.assertIn("十美元", script.clean_voice_text)
        self.assertGreater(script.total_words, 20)
        self.assertGreater(script.total_estimated_seconds, 5.0)
        self.assertGreater(len(script.segments), 2)

    def test_orchestrator_generate_body_retry(self):
        # 模拟包含禁词的生成结果，验证质检重试机制
        orch = KouboOrchestrator(skill_name="vbl-rational")
        call_count = 0
        def fake_llm(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "综上所述，这个技术不仅让我们看到了未来，更带来了变化。"
            return "先看官方事实，新模型降低了百分之五十的延迟。"

        cleaned = orch.generate_body("事实", "开场", llm_callable=fake_llm, max_retries=2, mode="create")
        self.assertNotIn("综上所述", cleaned)
        self.assertIn("百分之五十", cleaned)
        self.assertEqual(call_count, 2)

    def test_prompt_polish_mode_selection(self):
        # 测试长草稿输入时自动进入 polish 模式并注入字数区间
        orch = KouboOrchestrator(skill_name="vbl-rational")
        captured_prompt = ""
        def fake_llm(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "这是润色后的正文。"

        long_text = "这是测试长草稿。" * 50  # 超过 300 字
        orch.generate_body(long_text, "开场", llm_callable=fake_llm, mode="auto")
        self.assertIn("绝对禁止将长视频粗暴压缩为内容梗概", captured_prompt)
        self.assertIn("成稿字数区间严格控制在", captured_prompt)


if __name__ == "__main__":
    unittest.main()
