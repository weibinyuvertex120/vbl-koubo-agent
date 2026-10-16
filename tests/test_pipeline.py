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

    def test_proper_nouns_check_with_sample_input(self):
        # 使用只读方式读取 sample_input.txt，不调用模型，纯函数测试
        from pathlib import Path
        from vbl_koubo.pipeline.checker import extract_proper_nouns, check_proper_nouns_preservation, run_quality_gate
        
        sample_file = Path("sample_input.txt")
        source_text = sample_file.read_text(encoding="utf-8")
        
        # 验证通用动态提取：包含大写专名与连字符名，不含小写词组
        extracted = extract_proper_nouns(source_text)
        self.assertIn("HyperFrames", extracted)
        self.assertIn("Agent-Reach", extracted)
        self.assertIn("OpenCut", extracted)
        self.assertIn("SaaS", extracted)

        # 假成稿 1：拿掉 HyperFrames，必须红（判定失败，且指明丢失 HyperFrames）
        fake_bad_draft = (
            "欢迎收看本周开源软件汇总。今天介绍的工具是 HeyGen 开源的，"
            "第二个是 Agent-Reach，第三个是 Impeccable，配合同一套 SaaS 模板，第四个是 OpenCut。"
        )
        res_bad = run_quality_gate(fake_bad_draft, source_text=source_text)
        self.assertFalse(res_bad.passed)
        self.assertTrue(any("HyperFrames" in v for v in res_bad.violations))

        # 假成稿 2：保留了 HyperFrames是，保留了同一套 SaaS 模板，且包含全部原稿大写专名，必须绿
        fake_good_draft = (
            "欢迎收看本周开源软件汇总。第一个是 HyperFrames是很有用的工具，"
            "第二个是 Agent-Reach，给你的 AI Agent 装上网络能力，去搜索 Reddit 等内容。"
            "第三个是 Impeccable，配合同一套 SaaS 模板，使用 Inter 字体，结合 Skill、Commands、Detector 和 Hook 的组合。"
            "第四个是 OpenCut，解决 CapCut 的问题，未来推出编辑器 API，基于 Rust 多端方案。"
            "最后用 FFmpeg 渲染成 MP4、MOV，写 HTML 代码。这里是 VibeLearning。"
        )
        res_good = run_quality_gate(fake_good_draft, source_text=source_text)
        self.assertTrue(res_good.passed, f"预期通过，实际违规: {res_good.violations}")


if __name__ == "__main__":
    unittest.main()
