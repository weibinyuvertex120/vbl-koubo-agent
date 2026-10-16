"""
L1 静态口播质检哨所 (Static Quality Gate)
借鉴 khazix-writer / koubo-copywriter-lite 工业实践：
对生成的口播稿进行静态分析，零容忍拦截 AI 套话、书面连接腔、假大空与升华模板
"""

import re
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass


# 绝对禁词库（命中即判为违规或 AI 味过重）
L1_FORBIDDEN_WORDS = [
    # 总结腔
    "综上所述", "总而言之", "总的来说", "最后我想说", "结语",
    # 连接腔
    "首先", "其次", "再次", "与此同时", "值得一提的是", "毫无疑问",
    # 宏大叙事与万能开头
    "快节奏的时代", "快速发展的时代", "随着科技的发展", "随着社会的发展", "众所周知", "不得不说",
    # 强调腔
    "需要指出的是", "值得注意的是", "我们必须清醒地认识到", "毋庸置疑",
    # 虚假空洞升华
    "不仅让我们看到了", "这不仅仅是", "更是", "人生就是一场",
    # 营销叫卖腔（违背 VBL 客观定位）
    "太炸裂了", "赶紧冲", "必看神器", "彻底颠覆", "史诗级",
]


@dataclass
class QualityCheckResult:
    passed: bool
    violations: List[str]
    clean_text: str


def extract_proper_nouns(text: str) -> List[str]:
    """
    通用动态提取原稿中的大写专有名词与带连字符专名（适用于任何不同选题）：
    - 匹配大写开头或全大写的英文名，保留连字符（如 HyperFrames, Agent-Reach, OpenCut, FFmpeg, HTML, SaaS, Rust）
    - 长度至少为 3（过滤单字母和双字母代号）
    - 不抓小写单词，不抓中英混排词组，不维护静态特定单词黑白名单
    """
    # 匹配大写字母开头的连续字母数字，允许包含连字符连接的后续部分
    pattern = r'\b[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\b'
    candidates = re.findall(pattern, text)
    
    seen: Set[str] = set()
    result: List[str] = []
    
    for word in candidates:
        if len(word) < 3:
            continue
        lower_word = word.lower()
        if lower_word not in seen:
            seen.add(lower_word)
            result.append(word)
            
    return result


def check_proper_nouns_preservation(source_text: str, generated_text: str) -> List[str]:
    """
    通用专名比对：
    - 比对不分大小写
    - 必须是整词（前后不能紧挨着英文字母或数字，但后面紧挨汉字如 'HyperFrames是' 算整词在列）
    - 返回在原稿中存在、但在成稿中彻底丢失的专名列表
    """
    source_nouns = extract_proper_nouns(source_text)
    missing: List[str] = []

    for noun in source_nouns:
        # 使用前后非英文字母/数字的断言，确保是英文整词，同时兼容中文紧挨场景
        escaped_noun = re.escape(noun)
        check_pattern = rf'(?<![a-zA-Z0-9]){escaped_noun}(?![a-zA-Z0-9])'
        if not re.search(check_pattern, generated_text, re.IGNORECASE):
            missing.append(noun)

    return missing


def check_forbidden_words(text: str) -> List[str]:
    """扫描文本中出现的禁词"""
    found = []
    for word in L1_FORBIDDEN_WORDS:
        if word in text:
            found.append(word)
    return found


def sanitize_ai_patterns(text: str) -> str:
    """自动清理或替换常见轻度书面词"""
    replacements = {
        "综上所述，": "",
        "总而言之，": "",
        "总的来说，": "",
        "毋庸置疑，": "",
        "显而易见，": "",
        "鉴于此，": "所以，",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def run_quality_gate(text: str, source_text: Optional[str] = None) -> QualityCheckResult:
    """
    运行质检哨所：
    - 静态禁词扫描与自动净化
    - 若传入原稿 source_text，则动态比对原稿大写专名是否全部留存
    """
    sanitized = sanitize_ai_patterns(text)
    violations = check_forbidden_words(sanitized)
    
    if source_text:
        missing_nouns = check_proper_nouns_preservation(source_text, sanitized)
        for noun in missing_nouns:
            violations.append(f"原稿专名丢失: {noun}")

    passed = len(violations) == 0
    return QualityCheckResult(
        passed=passed,
        violations=violations,
        clean_text=sanitized
    )
