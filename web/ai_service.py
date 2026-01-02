import os
import json
import re
import time
import logging
import requests
from google import genai
from google.genai import types

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_service")

class AIService:
    def __init__(self, config_path="../config.json"):
        self.config = self._load_config(config_path)
        self.gemini_key = self.config.get("api_key")
        self.gemini_model = self.config.get("model", "gemini-3-pro-preview")

    def _load_config(self, path):
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Config load error: {e}")
        return {}

    def build_system_instruction(self):
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

    def build_constraints(self, novel_type: str, theme: str) -> str:
        return (
            f"类型：{novel_type}\n"
            f"主题/设定：{theme}\n"
            "必须严格对齐类型与主题，使用中文，本土现实语境。"
            "不得引入仙侠、修真、灵气、法术、赛博、星际、外星、末日等元素。"
            "世界观与角色设定需贴近现实逻辑，避免科幻或玄幻成分。"
        )

    def _call_gemini(self, system, user_msg, temperature=0.7):
        if not self.gemini_key:
            raise ValueError("Gemini API Key not configured")
            
        client = genai.Client(api_key=self.gemini_key)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=8000,
            top_p=0.95,
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])]
        
        # 简单重试逻辑
        models = [self.gemini_model, "gemini-2.5-pro"]
        last_err = None
        for m in models:
            try:
                resp = client.models.generate_content(model=m, contents=contents, config=config)
                return resp.text
            except Exception as e:
                last_err = e
                time.sleep(2)
        raise last_err

    def generate_outline(self, provider, novel_type, theme, chapters):
        """生成大纲的简化版接口，直接返回文本"""
        base_prompt = (
            f"请生成一份完整的《{novel_type}》小说大纲。\n"
            f"主题：{theme}\n"
            f"预估章节：{chapters}章\n"
            f"请包含：作品名、核心人设、世界观、爽点清单、三幕结构、章节大纲（第1-{chapters}章）、后续走向。\n"
            f"请以清晰的 Markdown 格式输出。"
        )
        
        system = self.build_system_instruction() + "\n" + self.build_constraints(novel_type, theme)
        return self._call_gemini(system, base_prompt)

    def generate_chapter(self, provider, novel_type, theme, outline_context, chapter_num, chapter_title, chapter_summary, prev_content=""):
        """生成单章正文"""
        
        prev_context_prompt = ""
        if prev_content:
            prev_segment = prev_content[-2000:]
            prev_context_prompt = (
                f"【上一章（第{chapter_num-1}章）结尾内容回顾】\n"
                f"{prev_segment}\n"
                f"--------------------------------\n"
                f"指令：请务必紧接上一章的结尾剧情继续创作，保持场景、时间、人物状态的连贯性。\n\n"
            )

        prompt = (
            f"你是一位专业畅销小说作家。\n"
            f"任务：请根据提供的大纲和上下文，创作小说第{chapter_num}章的正文。\n"
            f"章节标题：{chapter_title}\n"
            f"本章梗概：{chapter_summary}\n\n"
            f"{prev_context_prompt}"
            f"【小说完整大纲与设定】\n{outline_context[:20000]}\n\n" # 截断以防过长
            f"要求：\n"
            f"1. 字数要求：2000字以上。\n"
            f"2. 剧情紧凑，场景描写生动，人物对话符合性格。\n"
            f"3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。\n"
            f"4. 输出纯正文内容，不要包含“第X章”标题，直接开始正文描写。"
        )

        system = "你是一位专业网文作家。"
        return self._call_gemini(system, prompt, temperature=0.8)

