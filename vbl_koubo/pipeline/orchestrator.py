"""
端到端口播生成编排流水线 (Orchestrator)
串联：博主技能加载 -> HKR 黄金钩子竞争 -> 4 步母结构展开 -> L1 静态质检哨所 -> 确定性发音与提词排版
"""

import os
import re
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from vbl_koubo.engine.skill_loader import BloggerSkill, load_skill_by_name
from vbl_koubo.engine.normalizer import (
    normalize_numbers,
    clean_spoken_punctuation,
    split_into_breath_chunks,
    calculate_spoken_metrics
)
from vbl_koubo.engine.schemas import TeleprompterScript, ScriptSegment
from vbl_koubo.pipeline.prompts import build_hkr_hook_prompt, build_script_body_prompt
from vbl_koubo.pipeline.checker import run_quality_gate, QualityCheckResult


def extract_json_from_response(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    防御性解析大模型返回的 JSON：
    能自动剔除外层的 ```json ... ``` 或 ``` ... ``` Markdown 围栏，
    并提取出内部的合法 JSON 对象
    """
    cleaned = raw_text.strip()
    # 剥离 markdown 代码围栏
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```[a-zA-Z]*\n', '', cleaned)
        cleaned = re.sub(r'\n```$', '', cleaned)
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        # 如果依然失败，尝试用正则找到最外层的 { ... }
        match = re.search(r'(\{[\s\S]*\})', cleaned)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
    return None


@dataclass
class HookCandidate:
    type: str
    label: str
    text: str
    rationale: str


class KouboOrchestrator:
    """口播端到端流水线控制器"""

    def __init__(self, skill_name: str = "vbl-rational"):
        self.skill: BloggerSkill = load_skill_by_name(skill_name)

    def generate_hooks(self, facts: str, llm_callable=None) -> List[HookCandidate]:
        """
        生成 HKR 黄金 3 秒钩子候选
        如果提供了 llm_callable 则调用真实 LLM，否则运行规则基线
        """
        if llm_callable:
            prompt = build_hkr_hook_prompt(self.skill, facts)
            raw_response = llm_callable(prompt)
            data = extract_json_from_response(raw_response)
            if data and "hooks" in data:
                hooks = []
                for item in data.get("hooks", []):
                    hooks.append(HookCandidate(
                        type=item.get("type", "H"),
                        label=item.get("label", "候选钩子"),
                        text=normalize_numbers(item.get("text", "")),
                        rationale=item.get("rationale", "")
                    ))
                if hooks:
                    return hooks

        # 降级 / 确定性基线生成
        title_snippet = facts.split("\n")[0][:20].strip("# ")
        return [
            HookCandidate(
                type="H",
                label="颠覆认知型",
                text=normalize_numbers(f"大多数人以为这只是常规升级，但这次事实完全不同。"),
                rationale="制造信息落差，留住好奇用户"
            ),
            HookCandidate(
                type="K",
                label="硬核证据型",
                text=normalize_numbers(f"先看一组官方确凿数据：新一代指标提升了近百分之五十。"),
                rationale="数据直给，适合理性与技术受众"
            ),
            HookCandidate(
                type="R",
                label="痛点共鸣型",
                text=normalize_numbers(f"如果今天要在生产环境落地，真正卡住你的不是算法本身。"),
                rationale="切入落地实操痛点，引发同理心"
            )
        ]

    def generate_body(
        self,
        facts: str,
        selected_hook: str,
        llm_callable=None,
        mode: str = "auto",
        target_duration: Optional[int] = None,
        max_retries: int = 2
    ) -> str:
        """
        生成或润色正文
        支持 mode='auto' | 'create' | 'polish'
        根据目标时长或原文字数动态计算字数预算，解耦硬编码限制
        """
        if not llm_callable:
            # 基线降级文案
            return (
                f"这里是 VBL。先看官方页面给出的具体证据。"
                f"在核心测试中，各项指标均有明确数据支撑。"
                f"但在实际部署与可用性上，也有具体的门槛和成本考量。"
                f"先看页面证据，再决定它适不适合你的工作流。"
            )

        # 1. 自动判断模式
        char_count, _ = calculate_spoken_metrics(facts, wpm=250)
        is_long_draft = char_count >= 300 and ("\n" in facts or "。" in facts)
        
        effective_mode = mode
        if effective_mode == "auto":
            effective_mode = "polish" if is_long_draft else "create"

        # 2. 动态计算字数目标预算
        from vbl_koubo.pipeline.prompts import build_script_body_prompt, build_script_polish_prompt
        
        if effective_mode == "polish":
            # 润色模式：字数锚定在原稿的 75% ~ 95%
            target_min = int(char_count * 0.75)
            target_max = int(char_count * 0.95)
            prompt = build_script_polish_prompt(
                self.skill, selected_hook, facts,
                target_words_min=target_min,
                target_words_max=target_max
            )
        else:
            # 起草模式：以目标秒数（默认 60s 或指定）折算 250 WPM
            dur = target_duration or 60
            base_words = int(dur * (250 / 60))
            target_min = int(base_words * 0.85)
            target_max = int(base_words * 1.15)
            prompt = build_script_body_prompt(
                self.skill, selected_hook, facts,
                target_words_min=target_min,
                target_words_max=target_max
            )

        current_prompt = prompt

        for attempt in range(max_retries + 1):
            raw_body = llm_callable(current_prompt)
            # 剥离可能带的代码块标记
            cleaned_body = re.sub(r'^```[a-zA-Z]*\n', '', raw_body.strip())
            cleaned_body = re.sub(r'\n```$', '', cleaned_body).strip()

            # 运行 L1 质检
            gate_res = run_quality_gate(cleaned_body)
            if gate_res.passed or attempt == max_retries:
                return gate_res.clean_text

            # 违规时，构建轻量 Refine Prompt 请求改写
            violations_str = "、".join(gate_res.violations)
            current_prompt = (
                f"{prompt}\n\n"
                f"【上一轮生成的文本存在以下违规，请务必剔除并重新改写】：\n"
                f"发现 AI 套话或禁用连接词：{violations_str}\n"
                f"请保持口播短句，重新输出纯正文："
            )

        return raw_body

    def build_teleprompter_script(
        self,
        title: str,
        selected_hook: str,
        body_text: str,
        source_text: Optional[str] = None
    ) -> TeleprompterScript:
        """
        后处理物理层：过筛禁词、比对原稿专名、数字发音汉化、长句切分、测算时长并组装提词器
        """
        # 1. 质量哨所检查
        hook_clean = selected_hook.strip()
        body_clean = body_text.strip()
        
        # 严格去重：若 body 开头已经包含了 hook（完全相同或去标点后相同），不再重复拼接待选 hook
        def _normalize_cmp(s: str) -> str:
            return re.sub(r'[\s，。！？、]', '', s)

        norm_hook = _normalize_cmp(hook_clean)
        norm_body = _normalize_cmp(body_clean)

        if norm_body.startswith(norm_hook):
            full_raw = body_clean
        else:
            full_raw = f"{hook_clean}\n{body_clean}"
        gate_res: QualityCheckResult = run_quality_gate(full_raw, source_text=source_text)
        clean_base = gate_res.clean_text

        # 2. 物理层发音规范化与标点清理
        spoken_text = normalize_numbers(clean_base)
        spoken_text = clean_spoken_punctuation(spoken_text)

        # 3. 气口切分：真正一句说完才切行，逗号留在一行内
        raw_chunks = split_into_breath_chunks(spoken_text, max_chars=18)
        
        segments: List[ScriptSegment] = []
        for idx, chunk in enumerate(raw_chunks, 1):
            chunk_clean = chunk.strip("，。！？ ")
            if not chunk_clean:
                continue
            
            # 简易角色标注
            role = "hook" if idx <= 2 else ("closing" if idx >= len(raw_chunks) - 1 else "evidence")
            c_count, sec = calculate_spoken_metrics(chunk_clean, wpm=250)
            
            # 针对提词器生成视觉加粗（主重音只落在关键数据、核心动词或关键指标上，每句最多一处）
            marked = f"{chunk_clean}。" if not chunk.endswith("。") else chunk
            
            # 严格控制重音命中范围：优先加粗百分比、数字或关键对比词
            emphasis_targets = ["百分之", "点", "提升", "达到", "卡住", "核心区别", "真正"]
            for target in emphasis_targets:
                if target in chunk_clean:
                    marked = f"**{marked}**"
                    break

            segments.append(ScriptSegment(
                segment_index=idx,
                role=role,
                spoken_text=chunk_clean,
                marked_text=marked,
                emphasis_words=[],
                estimated_seconds=sec
            ))

        total_words, total_seconds = calculate_spoken_metrics(spoken_text, wpm=250)

        # 格式化提词器文本（包含轻量可复现 Manifest）
        import datetime
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        teleprompter_lines = [
            f"/* RUN MANIFEST */",
            f"/* Generated: {timestamp_str} | Skill: {self.skill.name} v{self.skill.version} */",
            f"/* Standard WPM: 250 | Segments: {len(segments)} */\n",
            f"🎙️ 【{title}】 | 风格：{self.skill.name}",
            f"⏱️ 预计总长：{total_seconds} 秒 | 总字数：{total_words} 字\n",
            "──────────────────────────────────────────"
        ]
        for seg in segments:
            cue_tag = "【🔥 黄金钩子】" if seg.role == "hook" else ("【🏁 理性收尾】" if seg.role == "closing" else "【📌 论据展开】")
            teleprompter_lines.append(f"{cue_tag} ({seg.estimated_seconds}s)")
            teleprompter_lines.append(f"  {seg.marked_text}\n")

        return TeleprompterScript(
            title=title,
            skill_used=self.skill.name,
            total_words=total_words,
            total_estimated_seconds=total_seconds,
            wpm_standard=250,
            segments=segments,
            clean_voice_text=spoken_text,
            teleprompter_text="\n".join(teleprompter_lines)
        )
