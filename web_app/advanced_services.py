"""
高级小说生成服务
包含桌面端的所有核心功能：大纲生成、多模型支持、文本润色等
"""

import os
import re
import json
import time
import logging
import threading
import queue
import secrets
import hashlib
from typing import Optional, Dict, List, Tuple, Any, Callable
from google import genai
from google.genai import types

# ==========================================================================
# 常量定义
# ==========================================================================

DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_DOUBAO_MODEL = ""
DEFAULT_DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_CLAUDE_BASE_URL = "https://api.anthropic.com/v1/messages"

# 40+ 小说类型库（与桌面端一致）
NOVEL_TYPES = [
    "官场逆袭", "官场", "体制", "职场", "职场商战", "创业", "商业复仇", "金融风云",
    "都市热血", "都市日常", "都市高武", "灵气复苏", "异能", "系统流", "都市修仙",
    "神医", "鉴宝", "律师", "医生", "娱乐圈",
    "现代言情", "豪门总裁", "先婚后爱", "破镜重圆", "甜宠", "虐恋", "婚恋", "萌宝",
    "青春校园", "都市生活",
    "古代言情", "宫斗宅斗", "女强", "穿越重生", "年代文", "种田", "美食",
    "扫黑除恶", "悬疑破案", "悬疑灵异", "灵异", "犯罪", "推理", "谍战",
    "玄幻", "仙侠", "武侠", "奇幻", "洪荒",
    "科幻", "星际", "赛博朋克", "末世", "无限流",
    "历史", "架空历史", "军事",
    "游戏", "电竞", "体育",
    "同人", "二次元",
    "校园", "纯爱", "百合", "ABO", "克苏鲁", "奇闻怪谈",
    "真人秀", "直播", "无限恐怖", "美娱", "反派", "群像",
]

# 主题建议库（与桌面端一致）
THEME_SUGGESTIONS = {
    "官场逆袭": [
        "草根逆袭官场，卷入扫黑风暴，凭智谋破局",
        "基层小吏被迫入局，反腐风暴中步步上位",
        "纪委暗线+政商勾连，旧案重启牵出保护伞",
        "调岗下放后绝地翻盘，借势改革撬动利益格局",
    ],
    "官场": [
        "基层科员步步为营，博弈人情与规则，破局上位",
        "组织路线与派系斗争，借项目与招商破局晋升",
        "政法系统暗流，规则与底线的长期拉锯",
    ],
    "体制": [
        "单位生态与资源分配，暗战升级，破局上岸",
        "巡察进驻引爆旧账，主角借势清算反杀",
    ],
    "职场": [
        "小镇青年入大厂，项目攻坚与人性博弈双线推进",
        "从背锅到反杀，证据链与舆论战逆转口碑",
        "职场PUA与反PUA，底线与成长的拉扯",
    ],
    "职场商战": [
        "从小职员到掌舵者，资本暗战与人性博弈",
        "并购夺权、财务造假、审计追凶，连环反转",
        "对赌协议与股权暗战，卧底线索撬动巨鳄",
    ],
    "创业": [
        "从0到1创业突围，融资暗战与伙伴背叛",
        "风口项目变局，产品、渠道、资本三线对抗",
    ],
    "商业复仇": [
        "家族企业被夺，主角卧薪尝胆，十年布局复仇",
        "商会与豪门博弈，借势反杀，步步夺回主导权",
    ],
    "金融风云": [
        "量化黑盒与内幕交易疑云，合规与贪婪对决",
        "基金经理沉浮，做空反做空，资本局中局",
    ],
    "都市热血": [
        "落魄高手回归都市，扮猪吃虎，建立商业帝国",
        "兄弟情义+地下势力对抗，升级打脸爽点密集",
    ],
    "都市日常": [
        "普通人逆风翻盘，事业与生活双线成长",
        "邻里烟火与职场成长，温暖治愈中暗藏反转",
    ],
    "都市高武": [
        "热血高燃的都市强者体系，对抗暗流势力",
        "觉醒者与秩序机构对立，能力代价与规则束缚",
    ],
    "灵气复苏": [
        "灵气复苏时代，主角抢占先机，宗门与官方博弈",
        "秘境降临、资源争夺，城市生存与势力争霸",
    ],
    "异能": [
        "超能力觉醒，官方收容与黑市组织双线追杀",
        "能力有代价，越强越失控，靠规则与智谋取胜",
    ],
    "系统流": [
        "系统任务驱动成长，主线暗藏阴谋，爽点密集反转",
        "排行榜与副本机制，奖励诱惑与惩罚代价并存",
    ],
    "都市修仙": [
        "现代都市修仙，隐秘宗门与世俗势力对抗",
        "灵气断绝时代重启修仙路，古今法则碰撞",
    ],
    "神医": [
        "传承医术救死扶伤，医道与权谋双线推进",
        "中西医结合，破解疑难杂症，声名鹊起",
    ],
    "鉴宝": [
        "异能鉴宝，古玩市场风云，捡漏与复仇并行",
        "文物修复与鉴定，揭开历史谜团",
    ],
    "律师": [
        "新人律师接手悬案，法庭辩论与幕后博弈",
        "从小案到大案，正义与利益的天平",
    ],
    "医生": [
        "急诊医生救死扶伤，医疗体制与人性拷问",
        "外科圣手成长之路，医术与医德的抉择",
    ],
    "娱乐圈": [
        "小透明逆袭娱乐圈，作品为王打脸黑粉",
        "资本操控与艺人反抗，流量与实力的较量",
    ],
    "现代言情": [
        "都市男女情感纠葛，误会与和解",
        "职场精英爱情故事，事业爱情双丰收",
    ],
    "豪门总裁": [
        "霸道总裁爱上我，甜宠虐渣双管齐下",
        "豪门恩怨情仇，真爱战胜一切",
    ],
    "先婚后爱": [
        "契约婚姻日久生情，从陌生到挚爱",
        "联姻背后的阴谋与真情",
    ],
    "破镜重圆": [
        "前任回归重新追妻，弥补遗憾",
        "误会解开，真爱重燃",
    ],
    "甜宠": [
        "甜蜜恋爱，无虐纯糖",
        "宠文到底，温馨治愈",
    ],
    "虐恋": [
        "爱而不得，情感拉扯",
        "深情虐恋，最终HE",
    ],
    "婚恋": [
        "婚姻生活百态，柴米油盐中的爱情",
        "婆媳关系与夫妻相处之道",
    ],
    "萌宝": [
        "萌娃助攻父母复合，天使宝宝暖心治愈",
        "带娃日常，温馨搞笑",
    ],
    "青春校园": [
        "校园纯爱，青涩懵懂的初恋",
        "学霸学渣的甜蜜互动",
    ],
    "都市生活": [
        "市井生活百态，小人物的奋斗史",
        "家长里短中的温情与智慧",
    ],
    "古代言情": [
        "穿越古代，改变命运",
        "古代爱情传奇，跨越阶层的真爱",
    ],
    "宫斗宅斗": [
        "后宫争宠，权谋与情感交织",
        "宅门深深，智斗恶毒亲眷",
    ],
    "女强": [
        "女主强势崛起，事业爱情双丰收",
        "巾帼不让须眉，建功立业",
    ],
    "穿越重生": [
        "重生归来，改写命运",
        "穿越异世，开挂人生",
    ],
    "年代文": [
        "七八十年代奋斗史，时代变迁中的个人命运",
        "知青下乡，艰苦岁月中的成长",
    ],
    "种田": [
        "田园生活，发家致富",
        "古代农家女逆袭，种田经商两不误",
    ],
    "美食": [
        "美食征服世界，舌尖上的传奇",
        "厨艺传承，美食与文化",
    ],
}

# ==========================================================================
# 核心提示词构建函数
# ==========================================================================

def build_system_instruction():
    """构建系统指令（与桌面端一致）"""
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
        '7) 章节大纲（至少24章；每章输出一个章节块：### 第N章：标题；并严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...；爽点允许为"暂无"）\n'
        "8) 可扩展支线与后续走向\n"
        "风格：节奏快、冲突密集、反转频繁、爽点直给。\n"
        '重要提示：章节标题中请勿包含"第X章"前缀，仅输出纯标题，例如"风起云涌"而不是"第1章 风起云涌"。'
    )

def build_constraints(novel_type: str, theme: str, channel: str = None) -> str:
    """构建约束条件（与桌面端一致）"""
    t = (novel_type or "").strip()
    allow_fantasy = any(k in t for k in ["仙侠", "玄幻", "奇幻"])
    allow_scifi = any(k in t for k in ["科幻"])
    allow_apocalypse = any(k in t for k in ["末世"])
    allow_supernatural = any(k in t for k in ["灵异", "悬疑灵异", "恐怖"])

    ch = (channel or "").strip()
    base = (
        (f'频道：{ch}\n" if ch else '")
        + f"类型：{novel_type}\n"
        + f"主题/设定：{theme}\n"
        + "必须严格对齐类型与主题，使用中文。\n"
    )
    if ch == "男频":
        base += "频道风格：男频优先，节奏更快，升级打脸与对抗更强。\n"
    elif ch == "女频":
        base += "频道风格：女频优先，情感线更清晰，人物关系与情绪拉扯更强。\n"
    if allow_fantasy:
        return base + "允许玄幻/仙侠设定与超自然能力，但剧情规则需自洽，避免无意义堆砌设定。\n"
    if allow_scifi:
        return base + "允许科幻元素（科技、工程、太空、AI等），但需科学逻辑尽量自洽，避免修真仙侠体系。\n"
    if allow_apocalypse:
        return base + "允许末世元素（灾变、生存、秩序崩坏等），但逻辑自洽，避免修真仙侠体系。\n"
    if allow_supernatural:
        return base + "允许灵异/恐怖氛围与超自然疑团，但需有清晰规则与可解释线索链。\n"
    return base + "本土现实语境优先，避免引入仙侠/修真/法术/赛博/星际/外星/末日/机甲等非现实元素。\n"

def build_user_prompt(novel_type: str, theme: str) -> str:
    """构建用户提示词"""
    return (
        f"类型：{novel_type}\n"
        f"主题/设定：{theme}\n"
        "请严格按系统要求生成结构化中文输出，不要解释流程。"
    )

# ==========================================================================
# 高级小说生成器类
# ==========================================================================

class AdvancedNovelGenerator:
    """
    高级小说生成器
    包含桌面端的所有核心功能
    """

    def __init__(self, config: Dict = None):
        """
        初始化生成器

        Args:
            config: 配置字典，包含API密钥等信息
        """
        self.config = config or {}
        self.logger = logging.getLogger("advanced_novel_gen")
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()

    # ==================== 文本处理工具方法 ====================

    def _sanitize_text(self, text: str) -> str:
        """清理文本，移除无用内容"""
        if not text:
            return ""
        lines = []
        for line in text.splitlines():
            lt = line.strip()
            if not lt:
                continue
            bad_starts = [
                "收到", "感谢", "作为资深", "我将", "我会", "策划案",
                "以下是", "将为您", "为了确保", "基于您", "这里为您提供"
            ]
            if any(lt.startswith(b) for b in bad_starts):
                continue
            lines.append(lt)
        return "\n".join(lines)

    def _parse_json(self, text: str) -> Any:
        """解析JSON文本"""
        if not text:
            return None
        s = text.strip()
        if s.startswith("```json"):
            s = re.sub(r"^```json\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        elif s.startswith("```"):
            s = re.sub(r"^```\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        s = s.strip()
        try:
            return json.loads(s)
        except:
            return None

    def _ensure_list(self, data: Any) -> List:
        """确保数据是列表"""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            chapters_key = next((k for k in data.keys() if "chapter" in k.lower()), None)
            if chapters_key and isinstance(data[chapters_key], list):
                return data[chapters_key]
        return []

    # ==================== API 调用方法 ====================

    def _get_api_key(self, provider: str) -> Optional[str]:
        """获取API密钥"""
        if provider == "Gemini":
            return (
                self.config.get("gemini_api_key") or
                os.environ.get("GEMINI_API_KEY") or
                ""
            )
        elif provider == "Doubao":
            return (
                self.config.get("doubao_api_key") or
                os.environ.get("DOUBAO_API_KEY") or
                ""
            )
        elif provider == "Claude":
            return (
                self.config.get("claude_api_key") or
                os.environ.get("CLAUDE_API_KEY") or
                ""
            )
        return ""

    def _call_gemini(
        self,
        prompt: str,
        system_instruction: str = None,
        model_name: str = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        response_schema: Dict = None
    ) -> str:
        """调用 Gemini API"""
        api_key = self._get_api_key("Gemini")
        if not api_key:
            raise ValueError("Gemini API key not configured")

        client = genai.Client(api_key=api_key)
        model = model_name or DEFAULT_GEMINI_MODEL

        # 构建配置
        system_parts = []
        if system_instruction:
            system_parts.append(types.Part.from_text(text=system_instruction))

        config_params = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "top_p": 0.95,
        }

        if system_parts:
            config_params["system_instruction"] = system_parts

        if response_schema:
            config_params["response_mime_type"] = "application/json"
            config_params["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_params)

        # 构建请求内容
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
        ]

        # 调用API（带重试逻辑）
        models_to_try = [model]
        if model != "gemini-2.5-pro":
            models_to_try.append("gemini-2.5-pro")
        if "gemini-2.0-flash" not in models_to_try:
            models_to_try.append("gemini-2.0-flash")

        for m in models_to_try:
            try:
                resp = client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config
                )
                text = self._extract_gemini_text(resp)
                if text:
                    return text
            except Exception as e:
                self.logger.warning(f"Gemini model {m} failed: {e}")
                continue

        return ""

    def _extract_gemini_text(self, resp) -> str:
        """从Gemini响应中提取文本"""
        if resp is None:
            return ""

        # 尝试直接获取text属性
        text = getattr(resp, "text", None)
        if isinstance(text, str) and text.strip():
            return text

        # 尝试从parts中获取
        parts = getattr(resp, "parts", None)
        if parts:
            try:
                joined = "".join([p.text for p in parts if hasattr(p, "text") and p.text])
                if joined.strip():
                    return joined
            except:
                pass

        # 尝试从candidates中获取
        candidates = getattr(resp, "candidates", None)
        if candidates:
            for c in candidates:
                content = getattr(c, "content", None)
                if content is None:
                    continue
                ctext = getattr(content, "text", None)
                if isinstance(ctext, str) and ctext.strip():
                    return ctext
                cparts = getattr(content, "parts", None)
                if not cparts:
                    continue
                try:
                    joined = "".join([p.text for p in cparts if hasattr(p, "text") and p.text])
                    if joined.strip():
                        return joined
                except:
                    pass

        return ""

    # ==================== 大纲生成核心方法 ====================

    def generate_outline(
        self,
        novel_type: str,
        theme: str,
        chapters: int = 100,
        channel: str = "男频",
        provider: str = "Gemini",
        model_name: str = None,
        progress_callback: Callable = None
    ) -> Dict:
        """
        生成完整的小说大纲

        Args:
            novel_type: 小说类型
            theme: 主题
            chapters: 章节数量
            channel: 频道（男频/女频）
            provider: AI提供商
            model_name: 模型名称
            progress_callback: 进度回调函数 callback(message, progress_percent)

        Returns:
            包含大纲信息的字典
        """
        self.cancel_event.clear()
        self.pause_event.clear()

        result = {
            "success": False,
            "outline_text": "",
            "chapters_data": [],
            "error": None
        }

        try:
            # 步骤1: 优化提示词
            if progress_callback:
                progress_callback("正在优化大纲生成指令...", 5)

            optimized_instruction = self._optimize_prompt(novel_type, theme, provider, model_name)

            # 步骤2: 生成大纲各部分
            constraints_text = build_constraints(novel_type, theme, channel)
            system_inst = optimized_instruction + "\n\n" + constraints_text

            # 构建分段生成任务
            sections = self._build_sections(novel_type, theme, chapters, provider)
            total_sections = len(sections)

            accumulated_text = ""
            all_chapters_data = []

            for i, (section_title, section_prompt, section_schema) in enumerate(sections):
                if self.cancel_event.is_set():
                    result["error"] = "Generation cancelled by user"
                    break

                # 等待如果暂停
                while self.pause_event.is_set() and not self.cancel_event.is_set():
                    time.sleep(0.2)

                progress_percent = 10 + int((i / total_sections) * 80)
                if progress_callback:
                    progress_callback(f"正在生成: {section_title}", progress_percent)

                # 调用API生成此部分
                section_text = self._generate_section(
                    section_title=section_title,
                    section_prompt=section_prompt,
                    section_schema=section_schema,
                    system_instruction=system_inst,
                    accumulated_context=accumulated_text,
                    provider=provider,
                    model_name=model_name
                )

                accumulated_text += f"\n\n### {section_title}\n{section_text}"

                # 如果是章节大纲，解析章节数据
                if "章节大纲" in section_title and section_schema:
                    chapters_list = self._parse_json(section_text)
                    if chapters_list:
                        all_chapters_data.extend(self._ensure_list(chapters_list))

            if not self.cancel_event.is_set():
                result["success"] = True
                result["outline_text"] = accumulated_text
                result["chapters_data"] = all_chapters_data

                if progress_callback:
                    progress_callback("大纲生成完成！", 100)

        except Exception as e:
            self.logger.error(f"Outline generation error: {e}", exc_info=True)
            result["error"] = str(e)
            if progress_callback:
                progress_callback(f"生成失败: {e}", 0)

        return result

    def _optimize_prompt(
        self,
        novel_type: str,
        theme: str,
        provider: str = "Gemini",
        model_name: str = None
    ) -> str:
        """优化大纲生成提示词"""
        prompt = (
            '你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n'
            f'小说类型：{novel_type}\n'
            f'核心主题：{theme}\n\n'
            '要求：\n'
            '1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n'
            '2. 细化对人设、世界观、冲突节奏的具体要求。\n'
            '3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n'
            '4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n'
            '5. 【重点】针对长篇结构，请设计"螺旋式上升"的剧情结构，避免重复套路。\n'
            '6. 章节标题生成时，请只输出标题文字，不要包含"第X章"字样。\n'
            '7. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。'
        )

        try:
            if provider == "Gemini":
                return self._call_gemini(
                    prompt=prompt,
                    model_name=model_name,
                    temperature=0.7,
                    max_tokens=4000
                )
            else:
                return build_system_instruction()
        except:
            return build_system_instruction()

    def _build_sections(
        self,
        novel_type: str,
        theme: str,
        chapters: int,
        provider: str
    ) -> List[Tuple[str, str, Optional[Dict]]]:
        """构建大纲生成的各个部分"""
        sections = []

        # 第1部分：作品基础信息
        sections.append((
            "作品基础信息",
            f'请为类型"{novel_type}"、主题"{theme}"的小说，输出：作品名、类型标签、一句话简介。',
            None
        ))

        # 第2部分：核心人设
        sections.append((
            "核心人设",
            f"请设计主角、主要对手、导师/盟友的详细人设。要求：性格鲜明、有成长弧线、符合{novel_type}类型特点。",
            None
        ))

        # 第3部分：世界观设定
        sections.append((
            "世界观与设定",
            f'请构建符合"{novel_type}'的世界观：时代背景、地域、权力结构、资源分配、核心规则。",
            None
        ))

        # 第4部分：爽点清单
        sections.append((
            "爽点清单",
            f"请列出10-15个核心爽点，包括：冲突点、反转点、打脸点、升级点。每个爽点需说明触发条件和读者预期反应。",
            None
        ))

        # 第5部分：三幕结构
        sections.append((
            "三幕结构梗概",
            f"请设计三幕结构：\n第一幕（起）：5-8个关键节点\n第二幕（承转）：8-12个关键节点\n第三幕（合）：5-8个关键节点",
            None
        ))

        # 第6部分：章节大纲（分批生成）
        # 每20章一批
        batch_size = 20
        num_batches = (chapters + batch_size - 1) // batch_size

        chapter_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapter": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"}
                },
                "required": ["chapter", "title", "summary"]
            }
        }

        for batch_idx in range(num_batches):
            start_ch = batch_idx * batch_size + 1
            end_ch = min((batch_idx + 1) * batch_size, chapters)

            batch_prompt = (
                f"请生成第{start_ch}章到第{end_ch}章的章节大纲。\n"
                f"要求：\n"
                f'1. 每章包含：chapter（章节号）、title（纯标题，不含"第X章'）、summary（梗概）\n"
                f'2. summary格式必须为：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点可为"暂无'）\n"
                f"3. 章节需承接前文，推进主线，设置悬念。\n"
                f"4. 输出JSON数组格式。"
            )

            sections.append((
                f"章节大纲（第{start_ch}-{end_ch}章）",
                batch_prompt,
                chapter_schema
            ))

        # 第7部分：支线与后续走向
        sections.append((
            "可扩展支线与后续走向",
            f"请设计2-3条可扩展支线，以及主线的长期发展方向（100章以上的延展可能性）。",
            None
        ))

        return sections

    def _generate_section(
        self,
        section_title: str,
        section_prompt: str,
        section_schema: Optional[Dict],
        system_instruction: str,
        accumulated_context: str,
        provider: str,
        model_name: str
    ) -> str:
        """生成单个大纲部分"""
        # 构建完整提示词（包含上下文）
        full_prompt = section_prompt

        if accumulated_context:
            context_text = accumulated_context[-15000:]  # 限制上下文长度
            full_prompt = (
                f"【已生成的大纲内容（上下文参考）】\n{context_text}\n\n"
                f"----------------\n"
                f"重要：请基于以上内容继续创作，确保逻辑一致。\n\n"
                f"{section_prompt}"
            )

        if provider == "Gemini":
            text = self._call_gemini(
                prompt=full_prompt,
                system_instruction=system_instruction,
                model_name=model_name,
                temperature=0.7 if not section_schema else 0.5,
                max_tokens=8000,
                response_schema=section_schema
            )
            return self._sanitize_text(text)

        return ""

    # ==================== 章节生成方法 ====================

    def generate_chapter(
        self,
        novel_info: Dict,
        chapter_info: Dict,
        prev_content: str = "",
        provider: str = "Gemini",
        model_name: str = None
    ) -> str:
        """
        生成单章内容

        Args:
            novel_info: 小说信息 {type, theme, outline}
            chapter_info: 章节信息 {num, title, summary}
            prev_content: 上一章内容（最后2000字）
            provider: AI提供商
            model_name: 模型名称

        Returns:
            章节正文
        """
        novel_type = novel_info.get('type', '')
        theme = novel_info.get('theme', '')
        full_outline = novel_info.get('outline', '')

        chap_num = chapter_info.get('num')
        chap_title = chapter_info.get('title')
        chap_summary = chapter_info.get('summary')

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
            f"【小说完整大纲与设定】\n"
            f"小说类型：{novel_type}\n"
            f"主题：{theme}\n"
            f"完整大纲参考：\n{full_outline[:5000]}\n\n"
            f"要求：\n"
            f"1. 字数要求：2000字以上。\n"
            f"2. 剧情紧凑，场景描写生动，人物对话符合性格。\n"
            f"3. 严格贴合本章梗概，承接上文（如果有），铺垫下文。\n"
            f'4. 输出纯正文内容，不要包含"第X章'标题，直接开始正文描写。"
        )

        if provider == "Gemini":
            content = self._call_gemini(
                prompt=prompt,
                model_name=model_name,
                temperature=0.8,
                max_tokens=8000
            )
            return self._sanitize_text(content)

        return ""

    # ==================== 文本润色方法 ====================

    def polish_text(
        self,
        text: str,
        polish_type: str = "enhance",
        provider: str = "Gemini",
        model_name: str = None
    ) -> str:
        """
        文本润色

        Args:
            text: 待润色文本
            polish_type: 润色类型 (enhance/simplify/correct)
            provider: AI提供商
            model_name: 模型名称

        Returns:
            润色后的文本
        """
        polish_instructions = {
            "enhance": "增强表现力，优化描写，使文字更生动、更有感染力",
            "simplify": "简化表达，删除冗余，使文字更简洁、更清晰",
            "correct": "修正语病，规范用词，使文字更规范、更专业"
        }

        instruction = polish_instructions.get(polish_type, polish_instructions["enhance"])

        prompt = (
            f"请对以下文本进行润色。\n"
            f"润色要求：{instruction}\n\n"
            f"【原文】\n{text}\n\n"
            f"请直接输出润色后的文本，不要添加任何解释。"
        )

        if provider == "Gemini":
            result = self._call_gemini(
                prompt=prompt,
                model_name=model_name,
                temperature=0.5,
                max_tokens=8000
            )
            return self._sanitize_text(result)

        return text

    # ==================== 大纲解析与管理 ====================

    def parse_outline(self, outline_text: str) -> List[Dict]:
        """
        从大纲文本中解析章节信息

        Args:
            outline_text: 大纲文本

        Returns:
            章节列表 [{chapter, title, summary}, ...]
        """
        # 尝试多种格式匹配
        matches = list(
            re.finditer(
                r"(?:^|\n)\s*###\s*第\s*(\d+)\s*章\s*(?:[:：]\s*([^\n]*?)\s*)?\n\s*([\s\S]*?)(?=(?:\n\s*###\s*第\s*\d+\s*章)|\s*$)",
                outline_text,
            )
        )

        if not matches:
            matches = list(
                re.finditer(
                    r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)",
                    outline_text,
                )
            )

        chapters = {}
        for m in matches:
            groups = m.groups()
            if len(groups) == 3:
                try:
                    c_num = int(m.group(1))
                except:
                    continue
                title_clean = (m.group(2) or "").strip()
                summary = (m.group(3) or "").strip()
            else:
                try:
                    c_num = int(m.group(2))
                except:
                    continue
                title_only = (m.group(3) or "").strip()
                title_clean = title_only
                summary = (m.group(4) or "").strip()

            if not summary:
                summary = "无内容"

            chapters[c_num] = {
                "chapter": c_num,
                "title": title_clean,
                "summary": summary,
            }

        return [chapters[k] for k in sorted(chapters.keys())]

    # ==================== 控制方法 ====================

    def cancel(self):
        """取消当前生成任务"""
        self.cancel_event.set()

    def pause(self):
        """暂停当前生成任务"""
        self.pause_event.set()

    def resume(self):
        """恢复生成任务"""
        self.pause_event.clear()

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self.cancel_event.is_set()

    def is_paused(self) -> bool:
        """检查是否已暂停"""
        return self.pause_event.is_set()


# ==========================================================================
# 辅助函数
# ==========================================================================

def get_theme_suggestions(novel_type: str) -> List[str]:
    """获取指定类型的主题建议"""
    return THEME_SUGGESTIONS.get(novel_type, [])

def get_all_novel_types() -> List[str]:
    """获取所有小说类型"""
    return NOVEL_TYPES

def load_config_from_file(config_path: str = None) -> Dict:
    """从文件加载配置"""
    if not config_path:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass

    return {}
