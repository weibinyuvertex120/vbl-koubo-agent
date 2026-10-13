"""
口语化与文本正则化安全网 (Normalizer)
口播的物理层约束：
1. 确定性将阿拉伯数字、小数、百分比转换为中文发音（如 3.5% -> 百分之三点五）
2. 剔除书面符号（冒号、分号、括号），规范句读气口
3. 单句长度安全网切分（避免长难句导致嘴瓢）
4. 计算口播字数与预估秒数
"""

import re
from typing import List, Tuple

# 数字转汉字字典
DIGIT_MAP = {
    '0': '零', '1': '一', '2': '二', '3': '三', '4': '四',
    '5': '五', '6': '六', '7': '七', '8': '八', '9': '九'
}

UNITS = ['', '十', '百', '千']


def _int_to_chinese(num_str: str) -> str:
    """将整数字符串转换为中文读音（支持常规口播数字范围 0~99999999）"""
    n = int(num_str)
    if n == 0:
        return '零'
    if len(num_str) == 1:
        return DIGIT_MAP[num_str]

    # 特殊规则：口播中年份/版本号逐字念（如 2024 -> 二零二四）
    # 这里处理常规度量数
    def _section_to_chinese(section: int) -> str:
        res = []
        zero_flag = False
        s_str = str(section).zfill(4)
        for i, digit_char in enumerate(s_str):
            digit = int(digit_char)
            if digit != 0:
                if zero_flag:
                    res.append('零')
                    zero_flag = False
                res.append(DIGIT_MAP[digit_char] + UNITS[3 - i])
            else:
                if len(res) > 0:
                    zero_flag = True
        out = ''.join(res)
        # 一十开头的口语化为十（如 15 -> 十五 而不是 一十五）
        if out.startswith('一十'):
            out = out[1:]
        return out

    if n < 10000:
        return _section_to_chinese(n)
    
    wan_part = n // 10000
    rem_part = n % 10000
    res = _section_to_chinese(wan_part) + '万'
    if rem_part > 0:
        if rem_part < 1000:
            res += '零' + _section_to_chinese(rem_part)
        else:
            res += _section_to_chinese(rem_part)
    return res


def normalize_percentage(text: str) -> str:
    """转换百分比：72.6% -> 百分之七十二点六"""
    def _replace_pct(match):
        num_part = match.group(1)
        normalized_num = normalize_numbers(num_part)
        return f"百分之{normalized_num}"

    pattern = r'(\d+(?:\.\d+)?)\s*%'
    return re.sub(pattern, _replace_pct, text)


def normalize_decimal(text: str) -> str:
    """转换小数：2.0 -> 二点零，3.14 -> 三点一四"""
    def _replace_dec(match):
        integer_part = match.group(1)
        decimal_part = match.group(2)
        int_cn = _int_to_chinese(integer_part)
        dec_cn = ''.join(DIGIT_MAP.get(c, c) for c in decimal_part)
        return f"{int_cn}点{dec_cn}"

    pattern = r'(\d+)\.(\d+)'
    return re.sub(pattern, _replace_dec, text)


def normalize_integers(text: str) -> str:
    """转换整数（不仅支持 ASCII 词边界，还支持紧挨着中文字符的数字，如 4090显卡、带来3个优势）"""
    def _replace_int(match):
        num_str = match.group(0)
        # 4位年份或型号逐字读（如 2026 -> 二零二六，4090 -> 四零九零）
        if len(num_str) == 4:
            return ''.join(DIGIT_MAP.get(c, c) for c in num_str)
        return _int_to_chinese(num_str)

    # 匹配不与英文字母或其它数字相连的独立连续数字序列
    pattern = r'(?<![a-zA-Z0-9])\d+(?![a-zA-Z0-9])'
    return re.sub(pattern, _replace_int, text)


def normalize_numbers(text: str) -> str:
    """整合数字发音化转换"""
    text = normalize_percentage(text)
    text = normalize_decimal(text)
    text = normalize_integers(text)
    return text


def clean_spoken_punctuation(text: str) -> str:
    """
    剔除适合眼睛看但不适合口播的符号：
    冒号、分号、中文破折号、括号替换为逗号或空格气口
    注意：保护英文字词中的连字符（如 ScreenSpot-Pro, Terminal-Bench）
    并自动去除中文词与量词之间多余的空格（如 十 美元 -> 十美元）
    同时将句子末尾或中文后的英文句号 '.' 转换为中文句号 '。'，但保护英文小数点（如 2.0、vbl.ai）
    """
    text = re.sub(r'[\(\)（）]', '', text)
    # 将中文全角冒号、分号、破折号转为逗号
    text = re.sub(r'[:：;；——_]', '，', text)
    # 将两边有空格或中文的英文破折号替换，不破坏专有名词英文连字符
    text = re.sub(r'(?<=[\u4e00-\u9fa5\s])-(?=[\u4e00-\u9fa5\s])', '，', text)
    # 将中文后出现的英文句号转换为中文句号（保护 2.0、3.5 不被误伤）
    text = re.sub(r'(?<=[\u4e00-\u9fa5])\.(?=[\u4e00-\u9fa5\s]|$)', '。', text)
    # 去除中文字符之间的多余空格（如 '十 美元' -> '十美元'）
    text = re.sub(r'(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])', '', text)
    # 合并多余标点
    text = re.sub(r'，+', '，', text)
    text = re.sub(r'。+', '。', text)
    text = re.sub(r'，。', '。', text)
    return text.strip()


def split_into_breath_chunks(text: str, max_chars: int = 18) -> List[str]:
    """
    根据气口与最大字数切分长句。
    一句真正结束才换行：只在句子结束标点（句号、问号、叹号、换行）处切分成行。
    逗号是换气，留在这一行里。
    只有长到会念嘴瓢、中间又没有任何停顿（无标点）的超长句，才在达到 max_chars 时切开，
    切开时原样切断，绝不自己补逗号。
    """
    lines = text.splitlines()
    chunks = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # 按句号、问号、叹号切分为真正结束的句子
        sentence_parts = re.split(r'([。！？])', line_str)
        current_sentence = ""

        for part in sentence_parts:
            if not part:
                continue
            if part in "。！？":
                current_sentence += part
                if current_sentence.strip():
                    sent = current_sentence.strip()
                    # 如果句子本身带标点（如逗号），留在一行内，由说话人自行换气
                    # 只有整句超长且没有任何标点停顿，才强切防嘴瓢；切开时不补逗号
                    if len(sent) > max_chars and not any(p in sent for p in "，, 、:：;；"):
                        while len(sent) > max_chars:
                            chunks.append(sent[:max_chars])
                            sent = sent[max_chars:]
                        if sent:
                            chunks.append(sent)
                    else:
                        chunks.append(sent)
                current_sentence = ""
            else:
                current_sentence += part

        if current_sentence.strip():
            sent = current_sentence.strip()
            if len(sent) > max_chars and not any(p in sent for p in "，, 、:：;；"):
                while len(sent) > max_chars:
                    chunks.append(sent[:max_chars])
                    sent = sent[max_chars:]
                if sent:
                    chunks.append(sent)
            else:
                chunks.append(sent)

    return [c for c in chunks if c.strip()]


def calculate_spoken_metrics(text: str, wpm: int = 250) -> Tuple[int, float]:
    """
    计算中文字数与预估朗读时间（秒）
    中文按有效字数（去除标点空格）计，语速通常 240~260 字/分钟
    """
    pure_chars = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
    char_count = len(pure_chars)
    seconds = round((char_count / wpm) * 60, 1)
    return char_count, max(seconds, 1.0)
