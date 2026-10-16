"""
VBL 口播 Agent 命令行实用工具入口 (CLI)
用法：
  1. 默认演示模式：
     python3 run.py
  2. 真实生成口播稿：
     python3 run.py --input "你的事实材料或要点" --title "视频主题"
  3. 从文件读取素材生成：
     python3 run.py --file path/to/facts.txt --title "视频主题"
  4. 指定技能风格：
     python3 run.py --skill vbl-rational --input "..."
"""

import sys
import argparse
import datetime
import re
from pathlib import Path

from vbl_koubo.engine.skill_loader import list_available_skills
from vbl_koubo.engine.llm import call_llm, get_llm_config
from vbl_koubo.pipeline.orchestrator import KouboOrchestrator


def slugify(text: str) -> str:
    """生成合规的目录 slug"""
    slug = re.sub(r'[^\w\u4e00-\u9fa5]+', '-', text).strip('-')
    return slug[:30] or "untitled"


def main():
    parser = argparse.ArgumentParser(description="VBL 口播 Agent - 结构化口播生成与提词引擎")
    parser.add_argument("--input", "-i", type=str, help="直接传入事实材料文本")
    parser.add_argument("--file", "-f", type=str, help="从本地文本文件读取事实材料")
    parser.add_argument("--title", "-t", type=str, default="口播视频草案", help="视频主题标题")
    parser.add_argument("--skill", "-s", type=str, default="vbl-rational", help="采用的博主技能 (默认: vbl-rational)")
    parser.add_argument("--hook-index", type=int, default=1, choices=[1, 2, 3], help="采用第几个黄金 Hook (1: 颠覆型, 2: 证据型, 3: 共鸣型)")
    parser.add_argument("--mode", "-m", type=str, default="auto", choices=["auto", "create", "polish"], help="生成模式：auto(自动识别), create(要点起草), polish(草稿润色)")
    parser.add_argument("--duration", "-d", type=int, default=None, help="目标时长（秒，用于 create 模式精确约束字数）")
    parser.add_argument("--mock", action="store_true", help="强制使用规则基线，不调用外部 LLM API")

    args = parser.parse_args()

    # 1. 确定事实输入材料
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ 找不到文件: {file_path}")
            sys.exit(1)
        facts = file_path.read_text(encoding="utf-8").strip()
    elif args.input:
        facts = args.input.strip()
    else:
        # 无参数时，优雅跑出默认示例
        facts = (
            "OpenAI 发布 GPT-6 Astra，定位为新一代智能模型，主打电脑操作、浏览与专业工程协同。\n"
            "基准测试得分：OSWorld 2.0 得分 72.6%，ScreenSpot-Pro 达到 92.7%，Terminal-Bench 4.0 为 57.9%。\n"
            "专业任务方面：AutomationBench 41.4%，BenchCAD 达到 95.9%。\n"
            "API 定价为每百万输入 token 10 美元，每百万输出 token 50 美元，快速模式按标准价 2 倍计费。"
        )
        if args.title == "口播视频草案":
            args.title = "OpenAI GPT-6 Astra 深度评测"

    print("=" * 65)
    print("🎙️  VBL 口播 Agent (vbl-koubo-agent)")
    print("=" * 65)

    # 2. 判断 LLM 是否可用
    cfg = get_llm_config()
    use_real_llm = False
    llm_func = None

    if not args.mock and cfg["api_key"]:
        use_real_llm = True
        llm_func = call_llm
        print(f"🔗 [在线模式] 检测到 API Key，使用模型: {cfg['model']}")
    else:
        print(f"⚙️  [离线/基线模式] 未配置 API Key 或指定了 --mock，采用确定性规则基线")

    # 3. 初始化编排器
    orchestrator = KouboOrchestrator(skill_name=args.skill)
    print(f"📌 采用技能风格: [{orchestrator.skill.name}]")

    # 4. 生成 3 组黄金 Hook 候选
    print(f"\n[1] 正在生成 HKR 黄金 3 秒开场...")
    hooks = orchestrator.generate_hooks(facts, llm_callable=llm_func)
    for idx, h in enumerate(hooks, 1):
        star = "★ [已选]" if idx == args.hook_index else "  "
        print(f"  {star} 钩子 {idx} [{h.type}型 · {h.label}]:")
        print(f"     \"{h.text}\" ({h.rationale})")

    selected_hook = hooks[args.hook_index - 1].text

    # 5. 生成母结构正文（带质检闭环与动态时长/润色模式）
    print(f"\n[2] 正在编排正文结构并执行去 AI 味质检 (模式: {args.mode})...")
    body_text = orchestrator.generate_body(
        facts,
        selected_hook,
        llm_callable=llm_func,
        mode=args.mode,
        target_duration=args.duration
    )

    # 6. 物理层安全网转换与提词排版（传入原稿进行通用专名留存核查）
    script = orchestrator.build_teleprompter_script(
        title=args.title,
        selected_hook=selected_hook,
        body_text=body_text,
        source_text=facts
    )

    # 7. 规范归档
    today_str = datetime.date.today().isoformat()
    folder_slug = f"{today_str}_{slugify(args.title)}"
    out_dir = Path("output") / folder_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    tele_file = out_dir / "teleprompter.txt"
    vo_file = out_dir / "vo-final.txt"

    tele_file.write_text(script.teleprompter_text, encoding="utf-8")
    vo_file.write_text(script.clean_voice_text, encoding="utf-8")

    # 8. 终端呈现
    print("\n" + "=" * 65)
    print(script.teleprompter_text)
    print("=" * 65)

    print(f"\n✅ 交付完毕！")
    print(f"   • 存放路径: {out_dir}")
    print(f"   • 字数/预计耗时: {script.total_words} 字 / {script.total_estimated_seconds} 秒")
    print(f"   • 提词器排版: {tele_file}")
    print(f"   • 纯净口播稿: {vo_file}")


if __name__ == "__main__":
    main()
