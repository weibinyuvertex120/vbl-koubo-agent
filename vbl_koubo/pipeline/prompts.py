"""
口播提示词模板引擎 (Prompt Templates)
吸收 broadcast-craft (HKR 黄金钩子竞争模型) 与 koubo-copywriter-lite (去AI味口语写作)
"""

from typing import List
from vbl_koubo.engine.skill_loader import BloggerSkill


def build_hkr_hook_prompt(skill: BloggerSkill, topic_facts: str) -> str:
    """
    构建 HKR 黄金 3 秒钩子竞争提示词：
    要求 LLM 一次性生成 3 种不同心理动机的黄金开头
    """
    return f"""你是一名顶级短视频口播导演。请阅读当前博主的技能规范与核心事实材料，生成 3 组各具杀伤力的黄金 3 秒钩子（Hook）。

【博主技能与人设要求】
名称：{skill.name}
定位与风格：{skill.description}
详细规约：
{skill.content}

【本期核心事实材料】
{topic_facts}

【生成规则】
请严格按照博主技能规约中的断句与语言风格要求，分别输出 3 种不同心理动机的黄金 Hook。每条钩子必须是一行说完完整意思的句子：
1. [H型 - 好奇悬念/颠覆视角]：颠覆常规认知，制造信息差，让听众瞬间停下来。
2. [K型 - 确凿证据/硬核数据]：先抛出震撼具体数字或官方事实，直接用确定性砸向观众。
3. [R型 - 痛点共鸣/工作流反思]：直击观众在实际场景中的困扰与代价，唤起强烈认同。

【输出格式】
必须输出为标准 JSON 格式，如下：
{{
  "hooks": [
    {{
      "type": "H",
      "label": "颠覆认知型",
      "text": "口播文案（一行完整句子，说完再断）",
      "rationale": "设计意图"
    }},
    {{
      "type": "K",
      "label": "硬核证据型",
      "text": "口播文案（一行完整句子，说完再断）",
      "rationale": "设计意图"
    }},
    {{
      "type": "R",
      "label": "痛点共鸣型",
      "text": "口播文案（一行完整句子，说完再断）",
      "rationale": "设计意图"
    }}
  ]
}}
仅输出合法 JSON，不要附带任何前言或反引号。"""


def build_script_body_prompt(
    skill: BloggerSkill,
    selected_hook: str,
    topic_facts: str,
    target_words_min: int = 200,
    target_words_max: int = 300
) -> str:
    """
    构建【从零起草模式】口播正文生成提示词
    结合选定的黄金 Hook，按照 Skill 定义的母结构推进，动态约束字数预算
    """
    return f"""你是一名专业口播文案创作者。请使用当前博主技能，围绕选定的黄金 Hook 和事实材料起草口播脚本。

【博主规范】
名称：{skill.name}
核心规约：
{skill.content}

【已选定的黄金开场 (Hook)】
"{selected_hook}"

【事实材料】
{topic_facts}

【物理字数与时长要求】
- 目标字数必须严格落在：{target_words_min} ~ {target_words_max} 字之间（按 250字/分钟 语速计算）。
- 严禁随意偷工减料过度压缩，必须充分展开材料中的关键论据和细节。

【写作执行规则】
请严格执行上述博主技能规范中定义的断句律与写作准则：
- 一句一个意思，说完再断。专名和数字留在同一行，不从中间切开。
- 去 AI 味：坚决不用“在当今快节奏的时代”、“综上所述”、“不仅如此”、“让我们拭目以待”。
- 遵循博主母结构推进：
  第 1 段：定位与核心主张（承接 Hook）
  第 2 段：硬核证据与数据拆解（抛出事实与工具细节）
  第 3 段：落地路径与代价/限制（客观公正）
  第 4 段：体系总结收尾（留给观众思考）

【输出格式】
请输出为纯连贯口播文案，每句话单独成行，不带段落标签，不带任何解释。"""


def build_script_polish_prompt(
    skill: BloggerSkill,
    selected_hook: str,
    draft_content: str,
    target_words_min: int = 800,
    target_words_max: int = 1200
) -> str:
    """
    构建【半成品润色/重塑模式】提示词
    严格遵循 Skill 里的规则，不复制额外样例，避免被模型生搬硬套
    """
    return f"""你是一名资深技术口播与中视频文案重塑专家。
你面前是一篇创作者已经写就的半成品口播草稿。原稿包含的工具细节、原理解释、体系串联和片尾互动已经过人工敲定。

【核心重塑准则】
1. 目标字数保持在原稿的 75% ~ 95% 之间，成稿字数区间严格控制在：{target_words_min} ~ {target_words_max} 字。
2. 绝对禁止将长视频粗暴压缩为内容梗概！
3. 请严格遵照下方博主技能规范（Skill）中的断句律与重塑原则进行文本重塑：一句一个意思，说完再断；逗号是句内换气，有逗号的完整意思留在同一行，逗号后面如果才是这句要说的事，这行就不算完。

【博主规范 (Skill)】
名称：{skill.name}
核心规约：
{skill.content}

【已选定/确认的黄金开场】
"{selected_hook}"

【待重塑的原始草稿】
{draft_content}

【输出格式】
直接输出润色重塑后的完整口播文本，每句话单独成行，不带任何解释，不带任何 Markdown 标题或代码围栏。"""
