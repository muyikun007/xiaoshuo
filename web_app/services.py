import os
import re
import json
import time
import logging
from google import genai
from google.genai import types

# 默认配置
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"

def build_system_instruction():
    return (
        "你是资深网络小说策划编辑，擅长打造强爽点节奏的长篇网文。"
        "你的任务是按要求输出完整的中文小说大纲，语言简洁有力。"
        "输出要求：\n"
        "1) 作品名\n"
        "2) 类型\n"
        "3) 核心人设（主角、对手、导师、盟友）\n"
        "4) 世界观与设定（时代、地域、权力结构、资源）\n"
        "5) 爽点清单（10条以上，明确冲突与反转）\n"
        "6) 三幕结构梗概（每幕5-8个关键节点）\n"
        "7) 章节大纲（至少24章，每章包含标题与1-2句梗概，推进冲突与爽点）\n"
        "8) 可扩展支线与后续走向\n"
        "风格：节奏快、冲突密集、反转频繁、爽点直给。\n"
        "重要提示：章节标题中请勿包含“第X章”前缀，仅输出纯标题，例如“风起云涌”而不是“第1章 风起云涌”。"
    )

def build_constraints(novel_type: str, theme: str) -> str:
    return (
        f"类型：{novel_type}\n"
        f"主题/设定：{theme}\n"
        "必须严格对齐类型与主题，使用中文，本土现实语境。"
        "不得引入仙侠、修真、灵气、法术、赛博、星际、外星、末日等元素。"
        "世界观与角色设定需贴近现实逻辑，避免科幻或玄幻成分。"
    )

class NovelGenerator:
    def __init__(self, api_key, provider="Gemini", model_name=None):
        self.api_key = api_key
        self.provider = provider
        self.model_name = model_name or DEFAULT_GEMINI_MODEL
        self.logger = logging.getLogger("novel_gen")

    def _sanitize_text(self, text: str) -> str:
        if not text:
            return ""
        lines = []
        for line in text.splitlines():
            lt = line.strip()
            if not lt:
                continue
            bad = ["收到", "感谢", "作为资深", "我将", "我会", "策划案", "以下是", "将为您", "为了确保", "基于您", "这里为您提供"]
            if any(lt.startswith(b) for b in bad):
                continue
            lines.append(lt)
        return "\n".join(lines)

    def _call_gemini(self, prompt, system_instruction=None):
        client = genai.Client(api_key=self.api_key)
        models_to_try = [self.model_name]
        if "gemini" in self.model_name.lower() and self.model_name != "gemini-2.5-pro":
             models_to_try.append("gemini-2.5-pro")
        
        config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system_instruction)] if system_instruction else None,
            temperature=0.7,
            max_output_tokens=8000,
            top_p=0.95,
        )
        
        # Reuse the fallback logic structure from original app but simplified
        for m in models_to_try:
            try:
                contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
                resp = client.models.generate_content(model=m, contents=contents, config=config)
                text = getattr(resp, "text", None)
                if not text and hasattr(resp, "parts"):
                     text = "".join([p.text for p in resp.parts if hasattr(p, "text") and p.text])
                if text:
                    return text
            except Exception as e:
                print(f"Gemini Error ({m}): {e}")
                continue
        return ""

    def generate_chapter(self, novel_info, chapter_info, prev_content=""):
        """
        Generates a single chapter.
        novel_info: dict {type, theme, outline}
        chapter_info: dict {num, title, summary}
        prev_content: string (last 2000 chars of previous chapter)
        """
        novel_type = novel_info.get('type', '')
        theme = novel_info.get('theme', '')
        full_outline = novel_info.get('outline', '')
        
        chap_num = chapter_info.get('num')
        chap_title = chapter_info.get('title')
        chap_summary = chapter_info.get('summary')

        context_base = (
            f"小说类型：{novel_type}\n"
            f"主题：{theme}\n"
            f"完整大纲参考：\n{full_outline}" 
        )

        prev_context_prompt = ""
        if prev_content:
            prev_text_segment = prev_content[-2000:]
            prev_context_prompt = (
                f"【上一章（第{chap_num-1}章）结尾内容回顾】\n"
                f"{prev_text_segment}\n"
                f"--------------------------------\n"
                f"指令：请务必紧接上一章的结尾剧情继续创作，保持场景、时间、人物状态的连贯性。\n\n"
            )

        prompt = (
            f"你是一位专业畅销小说作家。\n"
            f"任务：请根据提供的大纲和上下文，创作小说第{chap_num}章的正文。\n"
            f"章节标题：{chap_title}\n"
            f"本章梗概：{chap_summary}\n\n"
            f"{prev_context_prompt}"
            f"【小说完整大纲与设定】\n{context_base}\n\n"
            f"要求：\n"
            f"1. 字数要求：2000字以上。\n"
            f"2. 剧情紧凑，场景描写生动，人物对话符合性格。\n"
            f"3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。\n"
            f"4. 输出纯正文内容，不要包含“第X章”标题，直接开始正文描写。"
        )

        content = self._call_gemini(prompt, system_instruction=None)
        
        return self._sanitize_text(content)

    def generate_chapter_streaming(self, novel_info, chapter_info, prev_content="", on_progress=None):
        novel_type = novel_info.get('type', '')
        theme = novel_info.get('theme', '')
        full_outline = novel_info.get('outline', '')
        chap_num = chapter_info.get('num')
        chap_title = chapter_info.get('title')
        chap_summary = chapter_info.get('summary')
        context_base = (
            f"小说类型：{novel_type}\n"
            f"主题：{theme}\n"
            f"完整大纲参考：\n{full_outline}"
        )
        prev_context_prompt = ""
        if prev_content:
            prev_text_segment = prev_content[-2000:]
            prev_context_prompt = (
                f"【上一章（第{chap_num-1}章）结尾内容回顾】\n"
                f"{prev_text_segment}\n"
                f"--------------------------------\n"
                f"指令：请务必紧接上一章的结尾剧情继续创作，保持场景、时间、人物状态的连贯性。\n\n"
            )
        prompt = (
            f"你是一位专业畅销小说作家。\n"
            f"任务：请根据提供的大纲和上下文，创作小说第{chap_num}章的正文。\n"
            f"章节标题：{chap_title}\n"
            f"本章梗概：{chap_summary}\n\n"
            f"{prev_context_prompt}"
            f"【小说完整大纲与设定】\n{context_base}\n\n"
            f"要求：\n"
            f"1. 字数要求：2000字以上。\n"
            f"2. 剧情紧凑，场景描写生动，人物对话符合性格。\n"
            f"3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。\n"
            f"4. 输出纯正文内容，不要包含“第X章”标题，直接开始正文描写。"
        )
        client = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(
            temperature=0.8,
            max_output_tokens=8000,
            top_p=0.95,
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        buf = []
        try:
            last_len = 0
            for chunk in client.models.generate_content_stream(model=self.model_name, contents=contents, config=config):
                piece = ""
                if hasattr(chunk, "text") and chunk.text:
                    piece = chunk.text
                else:
                    try:
                        parts_text = []
                        if hasattr(chunk, "candidates"):
                            for cand in chunk.candidates:
                                if hasattr(cand, "content") and hasattr(cand.content, "parts"):
                                    for p in cand.content.parts:
                                        if hasattr(p, "text") and p.text:
                                            parts_text.append(p.text)
                        piece = "".join(parts_text)
                    except Exception:
                        piece = ""
                if piece:
                    buf.append(piece)
                    cur_text = self._sanitize_text("".join(buf))
                    if on_progress and len(cur_text) - last_len >= 128:
                        last_len = len(cur_text)
                        on_progress(cur_text)
            return self._sanitize_text("".join(buf))
        except Exception:
            return self.generate_chapter(novel_info, chapter_info, prev_content)

    def optimize_outline_prompt(self, novel_type, theme):
        # Logic to optimize prompt
        prompt = (
            "你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n"
            f"小说类型：{novel_type}\n"
            f"核心主题：{theme}\n\n"
            "要求：\n"
            "1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n"
            "2. 细化对人设、世界观、冲突节奏的具体要求。\n"
            "3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n"
            "4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n"
            "5. 【重点】针对长篇结构，请设计“螺旋式上升”的剧情结构，避免重复套路。\n"
            "6. 章节标题生成时，请只输出标题文字，不要包含“第X章”字样。\n"
            "7. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。"
        )
        
        return self._call_gemini(prompt)

