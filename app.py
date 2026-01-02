if __name__ == "__main__":
    import marshal
    from pathlib import Path

    _recovered = Path(__file__).with_name("recovered_app_20260102_1249.code")
    exec(marshal.loads(_recovered.read_bytes()), globals())
    raise SystemExit

import os
import sys
import re
import time
import logging
import threading
import queue
import json
import zipfile
import requests
from datetime import datetime
import secrets
import uuid
import platform
import hashlib
import hmac
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from google import genai
from google.genai import types

APP_TITLE = "小说大纲生成器"
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_DOUBAO_MODEL = ""
DEFAULT_DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_CLAUDE_BASE_URL = "https://api.anthropic.com/v1/messages"

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
        "7) 章节大纲（至少24章；每章输出一个章节块：### 第N章：标题；并严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...；爽点允许为“暂无”）\n"
        "8) 可扩展支线与后续走向\n"
        "风格：节奏快、冲突密集、反转频繁、爽点直给。\n"
        "重要提示：章节标题中请勿包含“第X章”前缀，仅输出纯标题，例如“风起云涌”而不是“第1章 风起云涌”。"
    )

def build_constraints(novel_type: str, theme: str, channel: str | None = None) -> str:
    t = (novel_type or "").strip()
    allow_fantasy = any(k in t for k in ["仙侠", "玄幻", "奇幻"])
    allow_scifi = any(k in t for k in ["科幻"])
    allow_apocalypse = any(k in t for k in ["末世"])
    allow_supernatural = any(k in t for k in ["灵异", "悬疑灵异", "恐怖"])

    ch = (channel or "").strip()
    base = (
        (f"频道：{ch}\n" if ch else "")
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
    return (
        f"类型：{novel_type}\n"
        f"主题/设定：{theme}\n"
        "请严格按系统要求生成结构化中文输出，不要解释流程。"
    )

def _gen_salt(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def hash_password(password: str) -> str:
    salt = _gen_salt(16)
    algo = "sha256"
    iters = 260000
    dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt.encode("utf-8"), iters, dklen=64)
    return f"pbkdf2:{algo}:{iters}${salt}${dk.hex()}"

def check_password(password_hash: str, password: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("scrypt:"):
        try:
            method, rest = password_hash.split("$", 1)
            params = method.split(":")
            n = int(params[1])
            r = int(params[2])
            p = int(params[3])
            salt, expected_hex = rest.split("$", 1)
            dk = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), n=n, r=r, p=p, dklen=len(bytes.fromhex(expected_hex)))
            return hmac.compare_digest(dk.hex(), expected_hex)
        except Exception:
            return False
    if password_hash.startswith("pbkdf2:"):
        try:
            method, rest = password_hash.split("$", 1)
            parts = method.split(":")
            algo = parts[1]
            iters = int(parts[2]) if len(parts) > 2 else 260000
            salt, expected_hex = rest.split("$", 1)
            dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt.encode("utf-8"), iters, dklen=len(bytes.fromhex(expected_hex)))
            return hmac.compare_digest(dk.hex(), expected_hex)
        except Exception:
            return False
    return False

def _humanize_mysql_connect_error(host: str, user: str, database: str, exc: Exception) -> str:
    try:
        code = int(getattr(exc, "args", [None])[0])
    except Exception:
        code = None
    if code == 1045:
        return (
            "MySQL鉴权失败（1045 Access denied）。\n"
            f"当前配置：host={host}  user={user}  database={database}\n"
            "这通常不是软件问题，需要在MySQL服务器端为该来源IP开通权限。\n"
            "建议不要使用root远程连接，改用独立账号。\n"
            "服务器端示例（在MySQL里执行，按需替换账号/密码/库名）：\n"
            "CREATE USER 'xiaoshuo_app'@'%' IDENTIFIED BY '强密码';\n"
            f"GRANT ALL PRIVILEGES ON `{database}`.* TO 'xiaoshuo_app'@'%';\n"
            "FLUSH PRIVILEGES;\n"
            "同时确认MySQL已开放3306端口且允许远程连接（bind-address/防火墙/安全组）。"
        )
    return f"MySQL连接失败：{exc}"

def _clear_root(root: tk.Tk):
    for w in list(root.winfo_children()):
        try:
            w.destroy()
        except Exception:
            pass

def show_main_screen(root: tk.Tk, user_row: dict):
    if (not isinstance(user_row, dict)) or (not user_row.get("id")):
        show_auth_screen(root)
        return
    _clear_root(root)
    root.title(APP_TITLE)
    root.geometry("1000x800")
    root.resizable(True, True)
    app = OutlineApp(root)
    try:
        root._outline_app = app
    except Exception:
        pass
    if isinstance(user_row, dict):
        app._set_logged_in_user(user_row)

def show_auth_screen(root: tk.Tk):
    _clear_root(root)
    w = AuthWindow(root)
    try:
        root._auth_window = w
    except Exception:
        pass

class AuthWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} - 登录/注册")
        self.root.geometry("800x520")
        self.root.resizable(False, False)

        self._auth_busy = False
        self.status_var = tk.StringVar(value="")
        self.login_username_var = tk.StringVar()
        self.login_password_var = tk.StringVar()
        self.reg_username_var = tk.StringVar()
        self.reg_password_var = tk.StringVar()
        self.reg_password2_var = tk.StringVar()
        self.reg_captcha_var = tk.StringVar()
        self._reg_captcha_code = ""
        self._reg_captcha_canvas = None

        self._build_ui()
        self._center_window()

    def _new_captcha_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(4))

    def _refresh_register_captcha(self):
        self._reg_captcha_code = self._new_captcha_code()
        self.reg_captcha_var.set("")
        canvas = self._reg_captcha_canvas
        if canvas is None:
            return
        try:
            w = int(canvas.winfo_reqwidth() or 110)
            h = int(canvas.winfo_reqheight() or 36)
        except Exception:
            w, h = 110, 36
        canvas.delete("all")
        bg = "#F2F2F2"
        canvas.create_rectangle(0, 0, w, h, fill=bg, outline="#D0D0D0")
        for _ in range(10):
            x1 = secrets.randbelow(w)
            y1 = secrets.randbelow(h)
            x2 = secrets.randbelow(w)
            y2 = secrets.randbelow(h)
            color = "#%02X%02X%02X" % (
                120 + secrets.randbelow(80),
                120 + secrets.randbelow(80),
                120 + secrets.randbelow(80),
            )
            canvas.create_line(x1, y1, x2, y2, fill=color, width=1)
        for _ in range(40):
            x = secrets.randbelow(w)
            y = secrets.randbelow(h)
            color = "#%02X%02X%02X" % (
                140 + secrets.randbelow(80),
                140 + secrets.randbelow(80),
                140 + secrets.randbelow(80),
            )
            canvas.create_oval(x, y, x + 1, y + 1, outline=color, fill=color)
        code = self._reg_captcha_code
        for i, ch in enumerate(code):
            x = 12 + i * 22 + secrets.randbelow(6)
            y = 8 + secrets.randbelow(6)
            color = "#%02X%02X%02X" % (
                30 + secrets.randbelow(120),
                30 + secrets.randbelow(120),
                30 + secrets.randbelow(120),
            )
            canvas.create_text(x, y, text=ch, anchor="nw", fill=color, font=("Consolas", 14, "bold"))

    def _center_window(self):
        try:
            self.root.update_idletasks()
            w = int(self.root.winfo_width() or 0)
            h = int(self.root.winfo_height() or 0)
            if w <= 1:
                w = int(self.root.winfo_reqwidth() or 800)
            if h <= 1:
                h = int(self.root.winfo_reqheight() or 520)
            if w < 300:
                w = 300
            if h < 200:
                h = 200
            x = (self.root.winfo_screenwidth() - w) // 2
            y = (self.root.winfo_screenheight() - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _get_app_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_external_config_path(self) -> str:
        return os.path.join(self._get_app_base_dir(), "config.json")

    def _get_bundled_config_path(self) -> str:
        meipass = getattr(sys, "_MEIPASS", "")
        if not meipass:
            return ""
        return os.path.join(meipass, "config.json")

    def _find_config_path(self) -> str:
        env_path = (os.environ.get("CONFIG_JSON_PATH", "") or os.environ.get("OUTLINE_APP_CONFIG", "") or "").strip()
        if env_path and os.path.exists(env_path):
            return env_path
        candidates = []
        external = self._get_external_config_path()
        if external:
            candidates.append(external)
        try:
            candidates.append(os.path.join(os.getcwd(), "config.json"))
        except Exception:
            pass
        try:
            base_dir = self._get_app_base_dir()
            parent_dir = os.path.dirname(base_dir)
            if parent_dir and parent_dir != base_dir:
                candidates.append(os.path.join(parent_dir, "config.json"))
        except Exception:
            pass
        bundled = self._get_bundled_config_path()
        if bundled:
            candidates.append(bundled)
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return ""

    def _load_config_json(self) -> dict:
        paths = []
        env_path = (os.environ.get("CONFIG_JSON_PATH", "") or os.environ.get("OUTLINE_APP_CONFIG", "") or "").strip()
        if env_path and os.path.exists(env_path):
            paths.append(env_path)
        bundled = self._get_bundled_config_path()
        if bundled and os.path.exists(bundled):
            paths.append(bundled)
        external = self._get_external_config_path()
        if external and os.path.exists(external):
            paths.append(external)
        try:
            cwd_cfg = os.path.join(os.getcwd(), "config.json")
            if os.path.exists(cwd_cfg):
                paths.append(cwd_cfg)
        except Exception:
            pass
        try:
            base_dir = self._get_app_base_dir()
            parent_cfg = os.path.join(os.path.dirname(base_dir), "config.json")
            if os.path.exists(parent_cfg):
                paths.append(parent_cfg)
        except Exception:
            pass

        merged = {}
        for p in list(dict.fromkeys(paths)):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        merged.update(data)
            except Exception:
                continue
        return merged

    def _load_type_library(self) -> list[str]:
        cfg = self._load_config_json()
        raw = cfg.get("type_library")
        items = []
        if isinstance(raw, list):
            for it in raw:
                s = str(it or "").strip()
                if s:
                    items.append(s)
        elif isinstance(raw, str):
            s = raw.strip()
            if s:
                items.append(s)
        if not items:
            return []
        seen = set()
        out = []
        for it in items:
            if it not in seen:
                seen.add(it)
                out.append(it)
        return out[:200]

    def _save_type_library(self) -> bool:
        cfg_path = self._get_external_config_path()
        if not (cfg_path and os.path.exists(cfg_path)):
            return False
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}
        except Exception:
            cfg = {}
        cfg["type_library"] = list(getattr(self, "type_library", []) or [])
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _load_theme_library(self) -> dict:
        cfg = self._load_config_json()
        raw = cfg.get("theme_library")
        if not isinstance(raw, dict):
            return {}
        out = {}
        for k, v in raw.items():
            key = str(k).strip()
            if not key:
                continue
            items = []
            if isinstance(v, list):
                for it in v:
                    s = str(it or "").strip()
                    if s:
                        items.append(s)
            elif isinstance(v, str):
                s = v.strip()
                if s:
                    items.append(s)
            if items:
                seen = set()
                dedup = []
                for it in items:
                    if it not in seen:
                        seen.add(it)
                        dedup.append(it)
                out[key] = dedup[:200]
        return out

    def _save_theme_library(self) -> bool:
        cfg_path = self._get_external_config_path()
        if not (cfg_path and os.path.exists(cfg_path)):
            return False
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}
        except Exception:
            cfg = {}
        cfg["theme_library"] = self.theme_library
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _get_theme_suggestions(self, novel_type: str) -> list[str]:
        t = (novel_type or "").strip()
        builtin = {
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
                "隐世传承回归都市，医道符箓双修，权贵圈反杀",
                "灵脉争夺与世家暗战，凡尘因果与渡劫危机",
            ],
            "神医": [
                "针灸医术逆袭，救人打脸两不误，牵出权钱黑幕",
                "名院暗战+医患悬疑，医学推理破局反转",
            ],
            "鉴宝": [
                "凭眼力破局，赌石鉴宝起势，牵出古玩圈阴谋",
                "文物流转与走私链条，真假局中局，线索链追凶",
            ],
            "律师": [
                "金牌律师卷入权贵案，证据链对决与舆论翻盘",
                "律所合伙人暗战，利益与正义的长期拉扯",
            ],
            "医生": [
                "急诊高压与人性选择，医疗事故背后另有真相",
                "医院派系暗斗，科研造假与救赎反转",
            ],
            "娱乐圈": [
                "从小透明到顶流，资本围猎与舆论反杀",
                "黑料与公关战，恋综与剧组双线升级打脸",
            ],
            "现代言情": [
                "成年人的情感拉扯与事业选择，甜虐交织",
                "势均力敌的双强恋爱，误会反转与共同成长",
            ],
            "豪门总裁": [
                "契约与真心博弈，强强对撞，甜宠反转",
                "联姻局中局，家族利益与真心救赎双线推进",
            ],
            "先婚后爱": [
                "假结婚真相爱，家庭与事业双线拉扯反转",
                "先冷后热，误会解除与信任重建",
            ],
            "破镜重圆": [
                "旧爱重逢，真相揭开，情感拉扯与事业反杀",
                "当年分手另有隐情，追妻火葬场与救赎反转",
            ],
            "甜宠": [
                "高糖恋爱与误会反转，撒糖中推进主线",
                "同居/契约/救赎设定，甜度拉满但主线不松",
            ],
            "虐恋": [
                "误会与救赎交织，极致情绪拉扯与反转",
                "身份错位与命运捉弄，真相揭开后反杀逆转",
            ],
            "婚恋": [
                "婚姻与成长的现实博弈，信任与底线重建",
                "出轨疑云与家庭战争，法律与情感双线对抗",
            ],
            "萌宝": [
                "带娃日常+情感修复，萌点与反转并行",
                "萌宝助攻破局，豪门与职场双线升级",
            ],
            "青春校园": [
                "暗恋与成长并行，青春群像与救赎",
                "校园到都市跨度，梦想与现实的分岔反转",
            ],
            "古代言情": [
                "权谋与情感纠缠，家国与私情两难",
                "边关将军与谋士女主，战事与朝局双线推进",
            ],
            "宫斗宅斗": [
                "深宅权谋与人心算计，步步惊心反杀上位",
                "后宅斗争牵出朝堂阴谋，智斗升级反转不断",
            ],
            "女强": [
                "女主高智商布局，权谋与复仇双线升级",
                "破局反杀，掌控资源与人心，爽点密集",
            ],
            "穿越重生": [
                "重来一世改写命运，布局复仇与成长",
                "前世惨死真相揭开，今生步步反杀登顶",
            ],
            "年代文": [
                "时代洪流里的人生选择，家庭事业并进",
                "知青返城与家长里短，温情治愈中暗藏危机",
            ],
            "种田": [
                "从一穷二白到富甲一方，经营发家致富",
                "家族经营+产业升级，乡土人情与暗线冲突",
            ],
            "美食": [
                "美食经营+成长逆袭，菜谱与人情两条线",
                "厨艺比拼与商战暗斗，温暖治愈里暗藏反转",
            ],
            "扫黑除恶": [
                "一线刑警深挖保护伞，黑白对决，正义必胜",
                "旧案重启牵出商会与家族势力，专案组破局",
            ],
            "悬疑破案": [
                "连环离奇案件，法医与刑警联手破局",
                "多案串联，线索链推进，真凶反转层层揭开",
            ],
            "悬疑灵异": [
                "诡秘案件与规则怪谈，线索链推理破局",
                "看似灵异实则人心，双线叙事反转揭真相",
            ],
            "灵异": [
                "诡事缠身与规则探索，抽丝剥茧寻找真相",
                "禁忌场域与代价规则，靠推理与胆识破局",
            ],
            "犯罪": [
                "灰黑边缘的生死局，卧底与反卧底的博弈",
                "犯罪心理与黑产链条，追凶与自救双线推进",
            ],
            "推理": [
                "多案串联与逻辑推演，反转与证据链对决",
                "密室/不在场/叙述性诡计，多重反转破局",
            ],
            "谍战": [
                "潜伏身份多重反转，情报战与心理战并行",
                "敌我难辨的局中局，信任崩塌与牺牲抉择",
            ],
            "玄幻": [
                "异世大陆崛起升级，势力争霸与血脉秘密",
                "天赋觉醒与宗门暗战，资源争夺螺旋升级",
            ],
            "仙侠": [
                "修行与因果纠缠，宗门风云与天命博弈",
                "秘境机缘与天劫代价，正邪拉扯与情义抉择",
            ],
            "武侠": [
                "江湖恩怨与门派暗战，快意恩仇，反转不断",
                "名门正派阴影，主角以智破局再立新规矩",
            ],
            "奇幻": [
                "新奇世界规则与冒险成长，秘密与反转不断",
                "多种族与魔法体系，代价规则清晰，剧情升级",
            ],
            "洪荒": [
                "洪荒神话重构，因果与气运争夺，势力博弈升级",
                "圣人布局与棋局反转，主角逆天改命",
            ],
            "科幻": [
                "硬核推演与惊险任务，科技阴谋与人性抉择",
                "星际远征与文明冲突，资源与信仰的对抗",
            ],
            "星际": [
                "星际佣兵成长，军团与财阀对抗，升级反转",
                "殖民地阴谋与叛乱，战场与政治双线推进",
            ],
            "赛博朋克": [
                "义体改造与数据阴谋，黑客与财阀对抗",
                "城市底层逆袭，AI与人性的边界反转",
            ],
            "末世": [
                "灾变生存，团队与秩序重建，对抗人性黑暗",
                "基地经营与资源争夺，强规则与成长升级",
            ],
            "无限流": [
                "规则副本闯关，反转不断，生死博弈",
                "队友互坑与合作共赢，世界观层层揭开",
            ],
            "历史": [
                "大时代权谋与战争，人物命运沉浮",
                "乱世崛起，谋略与军功双线升级",
            ],
            "架空历史": [
                "架空王朝权谋，改革破局，反转不断",
                "朝堂斗争牵动战场，家国与个人命运交织",
            ],
            "军事": [
                "边境暗战与强军征程，热血与牺牲并行",
                "特战行动与情报战，战术推进与反转升级",
            ],
            "游戏": [
                "系统机制与副本博弈，竞技与成长爽点",
                "公会暗战与赛事升级，现实与游戏双线推进",
            ],
            "电竞": [
                "职业战队逆袭，天才新人与老将救赎并行",
                "舆论黑点与赛场翻盘，热血高燃反转",
            ],
            "体育": [
                "从低谷到巅峰，训练与赛场高燃逆转",
                "伤病与复出，团队与个人荣誉双线拉扯",
            ],
            "同人": [
                "在熟悉世界观中改写命运，展开新故事",
                "补全原作遗憾，主线不崩，反转与成长并行",
            ],
            "二次元": [
                "轻松热血与羁绊成长，世界观脑洞与反转",
                "社团日常与主线冒险双线推进，节奏明快",
            ],
        }
        base = builtin.get(t, [])
        extra = []
        if isinstance(getattr(self, "theme_library", None), dict):
            extra = self.theme_library.get(t, []) or []
        generic = [
            "小人物逆袭入局，利益与底线拉扯，反转不断",
            "双线推进：主线升级+暗线真相，节奏明快",
            "旧案牵引当下危机，线索链推理破局",
            "强规则设定：能力体系清晰，代价与限制明确",
            "从局部冲突到体系对抗，螺旋式升级避免重复",
        ]
        merged = []
        seen = set()
        for it in (base + extra + generic):
            s = (it or "").strip()
            if s and s not in seen:
                seen.add(s)
                merged.append(s)
        return merged[:80]

    def on_add_theme(self):
        t = (self.type_var.get() or "").strip()
        theme = (self.theme_var.get() or "").strip()
        if not t:
            messagebox.showwarning("提示", "请先选择小说类型")
            return
        if not theme:
            messagebox.showwarning("提示", "请输入主题/设定")
            return
        if not isinstance(getattr(self, "theme_library", None), dict):
            self.theme_library = {}
        items = list(self.theme_library.get(t, []) or [])
        if theme not in items:
            items.insert(0, theme)
        self.theme_library[t] = items[:200]
        if hasattr(self, "theme_combo"):
            try:
                self.theme_combo["values"] = self._get_theme_suggestions(t)
            except Exception:
                pass
        saved = self._save_theme_library()
        if saved:
            messagebox.showinfo("已加入", "主题已加入主题库，并已保存。")
        else:
            messagebox.showinfo("已加入", "主题已加入主题库（未找到可写 config.json，重启后可能不保留）。")

    def on_add_type(self):
        t = (self.type_var.get() or "").strip()
        if not t:
            messagebox.showwarning("提示", "请输入小说类型")
            return
        if not isinstance(getattr(self, "type_library", None), list):
            self.type_library = []
        items = [str(x or "").strip() for x in (self.type_library or [])]
        items = [x for x in items if x]
        if t not in items:
            items.insert(0, t)
        self.type_library = items[:200]
        if hasattr(self, "type_combo"):
            try:
                values = list(self.type_combo["values"] or [])
            except Exception:
                values = []
            values = [str(x or "").strip() for x in values]
            values = [x for x in values if x]
            values = list(dict.fromkeys([t] + values))
            try:
                self.type_combo["values"] = values
            except Exception:
                pass
        saved = self._save_type_library()
        if saved:
            messagebox.showinfo("已加入", "类型已加入类型库，并已保存。")
        else:
            messagebox.showinfo("已加入", "类型已加入类型库（未找到可写 config.json，重启后可能不保留）。")

    def _load_mysql_config(self) -> dict:
        cfg = self._load_config_json()
        mysql = cfg.get("mysql")
        defaults = {
            "host": (os.environ.get("MYSQL_HOST") or "localhost").strip(),
            "port": int(os.environ.get("MYSQL_PORT") or 3306),
            "user": (os.environ.get("MYSQL_USER") or "root").strip(),
            "password": os.environ.get("MYSQL_PASSWORD") or "",
            "database": (os.environ.get("MYSQL_DATABASE") or "xiaoshuo").strip(),
            "charset": "utf8mb4",
        }
        if isinstance(mysql, dict):
            merged = dict(defaults)
            for k, v in mysql.items():
                if v is None:
                    continue
                if isinstance(v, str) and (not v.strip()):
                    continue
                merged[k] = v
            return merged
        return defaults

    def _normalize_phone(self, raw: str) -> str:
        s = (raw or "").strip()
        s = re.sub(r"[\s\-]", "", s)
        if s.startswith("+86"):
            s = s[3:]
        return s

    def _is_valid_phone(self, phone: str) -> bool:
        return bool(re.fullmatch(r"1\d{10}", phone or ""))

    def _users_has_phone_column(self, conn) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM users LIKE 'phone'")
                return cur.fetchone() is not None
        except Exception:
            return False

    def _users_has_column(self, conn, column: str) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM users LIKE %s", (str(column),))
                return cur.fetchone() is not None
        except Exception:
            return False

    def _ensure_users_antifraud_columns(self, conn):
        try:
            cols = {
                "register_ip": "VARCHAR(64) NULL",
                "register_mac": "VARCHAR(32) NULL",
                "register_env": "VARCHAR(64) NULL",
            }
            with conn.cursor() as cur:
                for col, ddl in cols.items():
                    cur.execute("SHOW COLUMNS FROM users LIKE %s", (col,))
                    if cur.fetchone() is None:
                        cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
            try:
                conn.commit()
            except Exception:
                pass
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

    def _get_device_mac_raw(self) -> str:
        try:
            node = uuid.getnode()
            if not isinstance(node, int):
                return ""
            mac_hex = f"{node:012x}"
            return ":".join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper()
        except Exception:
            return ""

    def _fingerprint_mac(self, mac_raw: str) -> str:
        try:
            v = (mac_raw or "").strip().upper()
            if not v:
                return ""
            return hashlib.md5(v.encode("utf-8")).hexdigest().upper()
        except Exception:
            return ""

    def _get_system_env_fingerprint(self) -> str:
        raw = ""
        try:
            if sys.platform.startswith("win"):
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                        raw = str(winreg.QueryValueEx(key, "MachineGuid")[0] or "").strip()
                except Exception:
                    raw = ""
        except Exception:
            raw = ""

        if not raw:
            try:
                raw = "|".join(
                    [
                        platform.platform(),
                        platform.node(),
                        platform.machine(),
                        platform.processor(),
                    ]
                )
            except Exception:
                raw = ""

        raw = (raw or "").strip()
        if not raw:
            return ""
        try:
            return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
        except Exception:
            return ""

    def _get_device_mac(self) -> str:
        mac_raw = self._get_device_mac_raw()
        if not mac_raw:
            return ""
        return self._fingerprint_mac(mac_raw)

    def _get_best_effort_ip(self) -> str:
        ip = ""
        try:
            resp = requests.get("https://api.ipify.org?format=json", timeout=3)
            if resp.ok:
                data = resp.json()
                v = (data.get("ip") if isinstance(data, dict) else "") or ""
                v = str(v).strip()
                if v:
                    ip = v
        except Exception:
            pass
        if ip:
            return ip
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = (s.getsockname()[0] or "").strip()
            finally:
                try:
                    s.close()
                except Exception:
                    pass
        except Exception:
            ip = ""
        return ip

    def _mysql_connect(self, show_ui: bool = True):
        try:
            import pymysql
        except Exception:
            msg = "未安装 pymysql，无法连接MySQL。请先安装：pip install pymysql"
            if show_ui:
                messagebox.showerror("缺少依赖", msg, parent=self.root)
                return None
            raise RuntimeError(msg)

        cfg = self._load_mysql_config()
        host = (cfg.get("host") or os.environ.get("MYSQL_HOST") or "").strip()
        port = int(cfg.get("port") or os.environ.get("MYSQL_PORT") or 3306)
        user = (cfg.get("user") or os.environ.get("MYSQL_USER") or "").strip()
        password = cfg.get("password") or os.environ.get("MYSQL_PASSWORD") or ""
        database = (cfg.get("database") or os.environ.get("MYSQL_DATABASE") or "").strip()
        charset = (cfg.get("charset") or "utf8mb4").strip()

        if not host or not user or not database:
            cfg_path = self._find_config_path()
            expected = self._get_external_config_path()
            msg = (
                "MySQL 配置不完整，请在 config.json 的 mysql 节点中填写 host/user/database。\n"
                f"已尝试读取配置：{cfg_path or '未找到配置文件'}\n"
                f"建议放置配置文件：{expected}\n"
                "也可设置环境变量 CONFIG_JSON_PATH 指向配置文件。"
            )
            if show_ui:
                messagebox.showerror("配置缺失", msg, parent=self.root)
                return None
            raise RuntimeError(msg)

        try:
            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset=charset,
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
            )
        except Exception as e:
            msg = _humanize_mysql_connect_error(host, user, database, e)
            if show_ui:
                messagebox.showerror("连接失败", msg, parent=self.root)
                return None
            raise RuntimeError(msg)

    def _set_auth_busy(self, busy: bool, status: str | None = None):
        self._auth_busy = busy
        if status is not None:
            self.status_var.set(status)

        cursor = "watch" if busy else ""
        try:
            self.root.configure(cursor=cursor)
        except Exception:
            pass

        state = tk.DISABLED if busy else tk.NORMAL
        for w in self.form_frame.winfo_children():
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _build_ui(self):
        bg = "#F5F5F5"
        fg = "#000000"
        try:
            self.root.configure(bg=bg)
        except Exception:
            pass

        main = tk.Frame(self.root, bg=bg)
        main.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self.title_var = tk.StringVar(value="登录")
        self.subtitle_var = tk.StringVar(value="")

        header = tk.Frame(main, bg=bg)
        header.pack(fill=tk.X, pady=(0, 10))
        tk.Label(header, textvariable=self.title_var, bg=bg, fg=fg, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="center")
        tk.Label(header, textvariable=self.subtitle_var, bg=bg, fg=fg, font=("Microsoft YaHei UI", 10)).pack(anchor="center")

        self.form_frame = tk.Frame(main, bg=bg)
        self.form_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.status_label = tk.Label(main, textvariable=self.status_var, bg=bg, fg=fg, wraplength=520, justify=tk.LEFT)
        self.status_label.pack(fill=tk.X, pady=(10, 0))

        self.footer_frame = tk.Frame(main, bg=bg)
        self.footer_frame.pack(fill=tk.X, pady=(12, 0))

        self.is_login_mode = True
        self._render_login_form()

    def _render_login_form(self):
        self.is_login_mode = True
        self.title_var.set("登录")
        self.subtitle_var.set("")
        self.status_var.set("")
        
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        for widget in self.footer_frame.winfo_children():
            widget.destroy()

        bg = "#F5F5F5"
        fg = "#000000"

        wrap = tk.Frame(self.form_frame, bg=bg)
        wrap.pack(expand=True)

        grid = tk.Frame(wrap, bg=bg)
        grid.pack(anchor="center")

        tk.Label(grid, text="手机号：", bg=bg, fg=fg).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        username = tk.Entry(grid, textvariable=self.login_username_var, width=28)
        username.grid(row=0, column=1, sticky="w", pady=(0, 8))

        tk.Label(grid, text="密码：", bg=bg, fg=fg).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 12))
        password = tk.Entry(grid, textvariable=self.login_password_var, show="*", width=28)
        password.grid(row=1, column=1, sticky="w", pady=(0, 12))

        btns = tk.Frame(wrap, bg=bg)
        btns.pack(anchor="center", pady=(6, 0))
        tk.Button(btns, text="登录", command=self._do_login, width=10).pack(side=tk.LEFT)
        tk.Button(btns, text="注册", command=self._render_register_form, width=10).pack(side=tk.LEFT, padx=8)

        username.bind("<Return>", lambda e: password.focus_set())
        password.bind("<Return>", lambda e: self._do_login())
        username.focus_set()

    def _render_register_form(self):
        self.is_login_mode = False
        self.title_var.set("注册")
        self.subtitle_var.set("")
        self.status_var.set("")
        
        for widget in self.form_frame.winfo_children():
            widget.destroy()
        for widget in self.footer_frame.winfo_children():
            widget.destroy()

        bg = "#F5F5F5"
        fg = "#000000"

        wrap = tk.Frame(self.form_frame, bg=bg)
        wrap.pack(expand=True)

        grid = tk.Frame(wrap, bg=bg)
        grid.pack(anchor="center")

        tk.Label(grid, text="手机号：", bg=bg, fg=fg).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        username = tk.Entry(grid, textvariable=self.reg_username_var, width=28)
        username.grid(row=0, column=1, sticky="w", pady=(0, 8))

        tk.Label(grid, text="密码：", bg=bg, fg=fg).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        pwd1 = tk.Entry(grid, textvariable=self.reg_password_var, show="*", width=28)
        pwd1.grid(row=1, column=1, sticky="w", pady=(0, 8))

        tk.Label(grid, text="确认密码：", bg=bg, fg=fg).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 12))
        pwd2 = tk.Entry(grid, textvariable=self.reg_password2_var, show="*", width=28)
        pwd2.grid(row=2, column=1, sticky="w", pady=(0, 12))

        tk.Label(grid, text="验证码：", bg=bg, fg=fg).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 12))
        captcha_row = tk.Frame(grid, bg=bg)
        captcha_row.grid(row=3, column=1, sticky="w", pady=(0, 12))
        captcha_entry = tk.Entry(captcha_row, textvariable=self.reg_captcha_var, width=10)
        captcha_entry.pack(side=tk.LEFT)
        self._reg_captcha_canvas = tk.Canvas(captcha_row, width=110, height=36, highlightthickness=0)
        self._reg_captcha_canvas.pack(side=tk.LEFT, padx=(8, 0))
        self._reg_captcha_canvas.bind("<Button-1>", lambda e: self._refresh_register_captcha())
        tk.Button(captcha_row, text="换一张", command=self._refresh_register_captcha).pack(side=tk.LEFT, padx=(8, 0))
        self._refresh_register_captcha()

        btns = tk.Frame(wrap, bg=bg)
        btns.pack(anchor="center", pady=(6, 0))
        tk.Button(btns, text="创建账号", command=self._do_register, width=10).pack(side=tk.LEFT)
        tk.Button(btns, text="返回登录", command=self._render_login_form, width=10).pack(side=tk.LEFT, padx=8)

        username.bind("<Return>", lambda e: pwd1.focus_set())
        pwd1.bind("<Return>", lambda e: pwd2.focus_set())
        pwd2.bind("<Return>", lambda e: captcha_entry.focus_set())
        captcha_entry.bind("<Return>", lambda e: self._do_register())
        username.focus_set()

    def _do_test_db(self):
        self.status_var.set("")
        started = time.perf_counter()
        conn = self._mysql_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS v, DATABASE() AS d, USER() AS u")
                info = cur.fetchone() or {}
            conn.close()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            messagebox.showinfo(
                "连接成功",
                "数据库连接成功\n"
                f"耗时：{elapsed_ms}ms\n"
                f"服务器版本：{info.get('v')}\n"
                f"当前用户：{info.get('u')}\n"
                f"当前库：{info.get('d')}",
                parent=self.root,
            )
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            messagebox.showerror("测试失败", f"测试失败：{e}", parent=self.root)

    def _do_login(self):
        self.status_var.set("")
        phone = self._normalize_phone(self.login_username_var.get() or "")
        password = (self.login_password_var.get() or "").strip()
        if (not phone) or (not password):
            self.status_var.set("请输入手机号和密码")
            return
        if not self._is_valid_phone(phone):
            self.status_var.set("请输入正确的手机号")
            return

        conn = self._mysql_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                has_phone = self._users_has_phone_column(conn)
                if has_phone:
                    cur.execute(
                        "SELECT id, username, phone, password_hash, token_balance FROM users WHERE phone=%s OR username=%s",
                        (phone, phone),
                    )
                else:
                    cur.execute("SELECT id, username, password_hash, token_balance FROM users WHERE username=%s", (phone,))
                row = cur.fetchone()
                if (not row) or (not check_password(row.get("password_hash") or "", password)):
                    conn.close()
                    self.status_var.set("手机号或密码错误")
                    return
                cur.execute("UPDATE users SET last_login_at = NOW() WHERE id=%s", (row["id"],))
                cur.execute("SELECT id, username, token_balance FROM users WHERE id=%s", (row["id"],))
                row2 = cur.fetchone()
            conn.commit()
            conn.close()
            show_main_screen(self.root, row2 or {})
        except Exception as e:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            self.status_var.set(f"登录失败：{e}")

    def _do_register(self):
        if self._auth_busy:
            return
        self.status_var.set("")
        phone = self._normalize_phone(self.reg_username_var.get() or "")
        p1 = (self.reg_password_var.get() or "").strip()
        p2 = (self.reg_password2_var.get() or "").strip()
        captcha_in = (self.reg_captcha_var.get() or "").strip().upper()
        if (not phone) or (not p1):
            self.status_var.set("请输入手机号和密码")
            return
        if not self._is_valid_phone(phone):
            self.status_var.set("请输入正确的手机号")
            return
        if p1 != p2:
            self.status_var.set("两次密码不一致")
            return
        if (not captcha_in) or (captcha_in != (self._reg_captcha_code or "").upper()):
            self.status_var.set("验证码错误")
            self._refresh_register_captcha()
            return

        self._set_auth_busy(True, "正在注册，请稍候…")
        threading.Thread(target=self._do_register_worker, args=(phone, p1), daemon=True).start()

    def _do_register_worker(self, phone: str, password: str):
        conn = None
        try:
            register_ip = self._get_best_effort_ip()
            register_mac_raw = self._get_device_mac_raw()
            register_mac = self._fingerprint_mac(register_mac_raw) if register_mac_raw else ""
            register_env = self._get_system_env_fingerprint()
            conn = self._mysql_connect(show_ui=False)
            self._ensure_users_antifraud_columns(conn)
            has_phone = self._users_has_phone_column(conn)
            has_reg_ip = self._users_has_column(conn, "register_ip")
            has_reg_mac = self._users_has_column(conn, "register_mac")
            has_reg_env = self._users_has_column(conn, "register_env")
            with conn.cursor() as cur:
                if has_phone:
                    cur.execute("SELECT id FROM users WHERE phone=%s OR username=%s", (phone, phone))
                else:
                    cur.execute("SELECT id FROM users WHERE username=%s", (phone,))
                if cur.fetchone():
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self.root.after(0, lambda: self._set_auth_busy(False, "手机号已存在"))
                    return

                limit_conds = []
                limit_params = []
                if has_reg_ip and register_ip:
                    limit_conds.append("register_ip=%s")
                    limit_params.append(register_ip)
                if has_reg_mac and register_mac:
                    limit_conds.append("register_mac=%s")
                    limit_params.append(register_mac)
                if has_reg_env and register_env:
                    limit_conds.append("register_env=%s")
                    limit_params.append(register_env)
                if limit_conds:
                    cur.execute(
                        f"SELECT COUNT(*) AS c FROM users WHERE {' OR '.join(limit_conds)}",
                        tuple(limit_params),
                    )
                    row = cur.fetchone() or {}
                    if int(row.get("c") or 0) >= 2:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        self.root.after(0, lambda: self._set_auth_busy(False, "同一个IP、设备MAC、同一个系统环境，只能注册2个账号"))
                        return

                gift_times = 3

                pwd_hash = hash_password(password)
                if has_phone:
                    cols = ["username", "phone", "password_hash", "status", "token_balance"]
                    params = [phone, phone, pwd_hash, 1, int(gift_times)]
                    if has_reg_ip:
                        cols.append("register_ip")
                        params.append(register_ip or None)
                    if has_reg_mac:
                        cols.append("register_mac")
                        params.append(register_mac or None)
                    if has_reg_env:
                        cols.append("register_env")
                        params.append(register_env or None)
                    placeholders = ", ".join(["%s"] * len(params))
                    cur.execute(
                        f"INSERT INTO users ({', '.join(cols)}, created_at) VALUES ({placeholders}, NOW())",
                        tuple(params),
                    )
                    cur.execute(
                        "SELECT id, username, token_balance FROM users WHERE phone=%s OR username=%s",
                        (phone, phone),
                    )
                else:
                    cols = ["username", "password_hash", "status", "token_balance"]
                    params = [phone, pwd_hash, 1, int(gift_times)]
                    if has_reg_ip:
                        cols.append("register_ip")
                        params.append(register_ip or None)
                    if has_reg_mac:
                        cols.append("register_mac")
                        params.append(register_mac or None)
                    if has_reg_env:
                        cols.append("register_env")
                        params.append(register_env or None)
                    placeholders = ", ".join(["%s"] * len(params))
                    cur.execute(
                        f"INSERT INTO users ({', '.join(cols)}, created_at) VALUES ({placeholders}, NOW())",
                        tuple(params),
                    )
                    cur.execute("SELECT id, username, token_balance FROM users WHERE username=%s", (phone,))
                row2 = cur.fetchone()
            conn.commit()
            try:
                conn.close()
            except Exception:
                pass
            self.root.after(0, lambda r=(row2 or {}): (self._set_auth_busy(False, ""), show_main_screen(self.root, r)))
        except Exception as e:
            try:
                if conn:
                    conn.rollback()
                    conn.close()
            except Exception:
                pass
            err_msg = str(e)
            self.root.after(0, lambda m=err_msg: self._set_auth_busy(False, f"注册失败：{m}"))

class OutlineApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1000x800")
        
        # 模型与服务配置
        self.provider_var = tk.StringVar(value="Gemini")
        self.model_var = tk.StringVar(value=DEFAULT_GEMINI_MODEL)
        self.model_name_var = tk.StringVar(value=DEFAULT_GEMINI_MODEL)
        self.channel_var = tk.StringVar(value="男频")
        
        self.type_var = tk.StringVar(value="官场逆袭")
        self.theme_var = tk.StringVar(value="草根逆袭官场，卷入扫黑风暴，凭智谋破局")
        self.chapters_var = tk.IntVar(value=100)
        self.expand_to_var = tk.IntVar(value=100)
        self.volumes_var = tk.IntVar(value=5)
        self.max_retries = 3
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.StringVar(value="进度 0/0")
        self.start_time = None
        self.completed_sections = 0
        self.total_sections = 0
        self.logger = None
        self.log_path = None
        self.chapters_data = []
        self.full_outline_context = ""
        self.all_chapter_summaries = []
        self.last_outline_path = None
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self.generation_variation = ""
        self.last_optimized_instruction = ""
        self.last_constraints_text = ""
        self.user_id = None
        self.username = None
        self.token_balance = 0
        self.user_status_var = tk.StringVar(value="未登录")
        self.user_token_var = tk.StringVar(value="0")
        self._pay_callback_server = None
        self._pay_callback_thread = None
        self._pay_callback_bind = ""
        self._pay_callback_port = 0
        self._pay_callback_secret = ""
        self._is_working = False
        self.type_library = self._load_type_library()
        self.theme_library = self._load_theme_library()
        self._build_ui()
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass

    def _wait_if_paused(self):
        while self._pause_event.is_set() and (not self._cancel_event.is_set()):
            time.sleep(0.2)

    def _on_close(self):
        try:
            if getattr(self, "_is_working", False) and (not self._cancel_event.is_set()):
                ok = messagebox.askyesno("正在生成中", "当前正在生成任务中，关闭将停止生成并退出。确定要关闭吗？")
                if not ok:
                    return
                try:
                    self._cancel_event.set()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self._stop_pay_callback_server()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _require_login_and_token(self) -> bool:
        if not self.user_id:
            messagebox.showinfo("提示", "请先登录后使用。")
            show_auth_screen(self.root)
            return False
        if int(self.token_balance or 0) <= 0:
            messagebox.showerror("次数卡不足", "次数卡不足，无法继续生成。")
            return False
        return True

    def _get_app_base_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_external_config_path(self) -> str:
        return os.path.join(self._get_app_base_dir(), "config.json")

    def _get_bundled_config_path(self) -> str:
        meipass = getattr(sys, "_MEIPASS", "")
        if not meipass:
            return ""
        return os.path.join(meipass, "config.json")

    def _find_config_path(self) -> str:
        env_path = (os.environ.get("CONFIG_JSON_PATH", "") or os.environ.get("OUTLINE_APP_CONFIG", "") or "").strip()
        if env_path and os.path.exists(env_path):
            return env_path
        candidates = []
        external = self._get_external_config_path()
        if external:
            candidates.append(external)
        try:
            candidates.append(os.path.join(os.getcwd(), "config.json"))
        except Exception:
            pass
        try:
            base_dir = self._get_app_base_dir()
            parent_dir = os.path.dirname(base_dir)
            if parent_dir and parent_dir != base_dir:
                candidates.append(os.path.join(parent_dir, "config.json"))
        except Exception:
            pass
        bundled = self._get_bundled_config_path()
        if bundled:
            candidates.append(bundled)
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return ""

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)
        try:
            ttk.Style().configure("RechargeHint.TLabel", foreground="red")
        except Exception:
            pass

        # --- Row 0: 模型设置 ---
        row0 = ttk.LabelFrame(main, text="模型设置", padding=(10, 5))
        row0.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(row0, text="大模型：").pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(row0, textvariable=self.model_var, width=25, state="readonly")
        self.model_combo.pack(side=tk.LEFT, padx=5)
        self.model_combo["values"] = [DEFAULT_GEMINI_MODEL, "gemini-2.5-pro", "gemini-2.0-flash"]
        self.model_var.set(DEFAULT_GEMINI_MODEL)

        # --- Row 1: 小说基础信息 ---
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=8)
        ttk.Label(row1, text="频道：").pack(side=tk.LEFT)
        self.channel_combo = ttk.Combobox(row1, textvariable=self.channel_var, values=["男频", "女频"], state="readonly", width=6)
        self.channel_combo.pack(side=tk.LEFT, padx=6)
        ttk.Label(row1, text="小说类型：").pack(side=tk.LEFT)
        types_list = [
            "官场逆袭", "官场", "体制", "职场", "职场商战", "创业", "商业复仇", "金融风云",
            "都市热血", "都市日常", "都市高武", "灵气复苏", "异能", "系统流", "都市修仙",
            "神医", "鉴宝", "律师", "医生", "娱乐圈",
            "现代言情", "豪门总裁", "先婚后爱", "破镜重圆", "甜宠", "虐恋", "婚恋", "萌宝", "青春校园", "都市生活",
            "古代言情", "宫斗宅斗", "女强", "穿越重生", "年代文", "种田", "美食",
            "扫黑除恶", "悬疑破案", "悬疑灵异", "灵异", "犯罪", "推理", "谍战",
            "玄幻", "仙侠", "武侠", "奇幻", "洪荒",
            "科幻", "星际", "赛博朋克", "末世", "无限流",
            "历史", "架空历史", "军事",
            "游戏", "电竞", "体育",
            "同人", "二次元",
            "校园", "纯爱", "百合", "ABO", "克苏鲁", "奇闻怪谈", "真人秀", "直播", "无限恐怖", "美娱", "反派", "群像",
        ]
        extra_types = []
        try:
            extra_types = list(getattr(self, "type_library", []) or [])
        except Exception:
            extra_types = []
        all_types = list(dict.fromkeys([x for x in (types_list + extra_types) if (x or "").strip()]))
        self.type_combo = ttk.Combobox(row1, textvariable=self.type_var, values=all_types, state="normal", width=20)
        self.type_combo.pack(side=tk.LEFT, padx=6)
        self.type_combo.bind("<<ComboboxSelected>>", self.on_type_changed)
        self.type_combo.bind("<Return>", lambda e: self.on_type_changed(e))
        self.add_type_btn = ttk.Button(row1, text="加入类型库", command=self.on_add_type)
        self.add_type_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Label(row1, text="主题/设定：").pack(side=tk.LEFT, padx=(18, 0))
        self.theme_combo = ttk.Combobox(
            row1,
            textvariable=self.theme_var,
            values=self._get_theme_suggestions(self.type_var.get()),
            state="normal",
            width=34,
        )
        self.theme_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.add_theme_btn = ttk.Button(row1, text="加入主题库", command=self.on_add_theme)
        self.add_theme_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Label(row1, text="章节数：").pack(side=tk.LEFT, padx=(18, 0))
        self.chapters_spin = ttk.Spinbox(row1, from_=1, to=1000, textvariable=self.chapters_var, width=6)
        self.chapters_spin.pack(side=tk.LEFT)

        row_user = ttk.LabelFrame(main, text="个人中心", padding=(10, 5))
        row_user.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row_user, textvariable=self.user_status_var).pack(side=tk.LEFT)
        ttk.Label(row_user, text="次数卡：").pack(side=tk.LEFT, padx=(18, 0))
        ttk.Label(row_user, textvariable=self.user_token_var).pack(side=tk.LEFT)
        ttk.Label(
            row_user,
            text="新用户免费使用3次，充值次数请加微信号：dddjs003，备注：小说作家，活动价格：100元10次，最低购买10次",
            style="RechargeHint.TLabel",
            wraplength=520,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)

        self.logout_btn = ttk.Button(row_user, text="退出登录", command=self.on_logout, state=tk.DISABLED)
        self.logout_btn.pack(side=tk.RIGHT)
        self.refresh_token_btn = ttk.Button(row_user, text="刷新次数卡", command=self.on_refresh_token, state=tk.DISABLED)
        self.refresh_token_btn.pack(side=tk.RIGHT, padx=8)

        # --- Row 2: 操作按钮 ---
        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=5)
        self.generate_btn = ttk.Button(row2, text="生成大纲", command=self.on_generate)
        self.generate_btn.pack(side=tk.LEFT)

        self.pause_btn = ttk.Button(row2, text="暂停", command=self.on_toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=8)

        self.import_outline_btn = ttk.Button(row2, text="上传大纲", command=self.on_import_outline)
        self.import_outline_btn.pack(side=tk.LEFT, padx=8)

        self.export_outline_btn = ttk.Button(row2, text="导出大纲", command=self.on_save)
        self.export_outline_btn.pack(side=tk.LEFT, padx=8)

        row_feedback = ttk.LabelFrame(main, text="修改大纲（填写修改要求后点击“修改大纲”）", padding=(10, 6))
        row_feedback.pack(fill=tk.X, pady=(8, 0))
        feedback_wrap = ttk.Frame(row_feedback)
        feedback_wrap.pack(fill=tk.X, expand=True)
        self.feedback_text = tk.Text(feedback_wrap, height=4, wrap=tk.WORD, font=("Consolas", 10))
        self.feedback_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        fb_scroll = ttk.Scrollbar(feedback_wrap, orient=tk.VERTICAL, command=self.feedback_text.yview)
        fb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.feedback_text.configure(yscrollcommand=fb_scroll.set)

        row_feedback_btns = ttk.Frame(row_feedback)
        row_feedback_btns.pack(fill=tk.X, pady=(6, 0))
        self.regen_btn = ttk.Button(row_feedback_btns, text="修改大纲", command=self.on_regenerate_with_feedback)
        self.regen_btn.pack(side=tk.LEFT)
        ttk.Button(row_feedback_btns, text="清空意见", command=lambda: self.feedback_text.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=8)

        # --- Status Row ---
        row_status = ttk.Frame(main)
        row_status.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(row_status, textvariable=self.progress_var).pack(side=tk.LEFT)
        ttk.Label(row_status, text="    ").pack(side=tk.LEFT)
        ttk.Label(row_status, textvariable=self.status_var).pack(side=tk.LEFT)

        # --- Text Output ---
        row3 = ttk.Frame(main)
        row3.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.output = tk.Text(row3, wrap=tk.WORD, font=("Consolas", 11))
        self.output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(row3, orient=tk.VERTICAL, command=self.output.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.output.configure(yscrollcommand=scrollbar.set)
        self._update_account_ui()

    def on_test_db(self):
        started = time.perf_counter()
        conn = self._mysql_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS v, DATABASE() AS d, USER() AS u")
                info = cur.fetchone() or {}
            conn.close()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            messagebox.showinfo(
                "连接成功",
                "数据库连接成功\n"
                f"耗时：{elapsed_ms}ms\n"
                f"服务器版本：{info.get('v')}\n"
                f"当前用户：{info.get('u')}\n"
                f"当前库：{info.get('d')}",
            )
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            messagebox.showerror("测试失败", f"测试失败：{e}")

    def _load_config_json(self) -> dict:
        paths = []
        env_path = (os.environ.get("CONFIG_JSON_PATH", "") or os.environ.get("OUTLINE_APP_CONFIG", "") or "").strip()
        if env_path and os.path.exists(env_path):
            paths.append(env_path)
        bundled = self._get_bundled_config_path()
        if bundled and os.path.exists(bundled):
            paths.append(bundled)
        external = self._get_external_config_path()
        if external and os.path.exists(external):
            paths.append(external)
        try:
            cwd_cfg = os.path.join(os.getcwd(), "config.json")
            if os.path.exists(cwd_cfg):
                paths.append(cwd_cfg)
        except Exception:
            pass
        try:
            base_dir = self._get_app_base_dir()
            parent_cfg = os.path.join(os.path.dirname(base_dir), "config.json")
            if os.path.exists(parent_cfg):
                paths.append(parent_cfg)
        except Exception:
            pass

        merged = {}
        for p in list(dict.fromkeys(paths)):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        merged.update(data)
            except Exception:
                continue
        return merged

    def _load_theme_library(self) -> dict:
        cfg = self._load_config_json()
        raw = cfg.get("theme_library")
        if not isinstance(raw, dict):
            return {}
        out = {}
        for k, v in raw.items():
            key = str(k).strip()
            if not key:
                continue
            items = []
            if isinstance(v, list):
                for it in v:
                    s = str(it or "").strip()
                    if s:
                        items.append(s)
            elif isinstance(v, str):
                s = v.strip()
                if s:
                    items.append(s)
            if items:
                seen = set()
                dedup = []
                for it in items:
                    if it not in seen:
                        seen.add(it)
                        dedup.append(it)
                out[key] = dedup[:200]
        return out

    def _save_theme_library(self) -> bool:
        cfg_path = self._get_external_config_path()
        if not (cfg_path and os.path.exists(cfg_path)):
            return False
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if not isinstance(cfg, dict):
                    cfg = {}
        except Exception:
            cfg = {}
        cfg["theme_library"] = self.theme_library
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _get_theme_suggestions(self, novel_type: str) -> list[str]:
        t = (novel_type or "").strip()
        builtin = {
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
                "能力代价反噬，越强越危险，反转不断",
            ],
            "系统流": [
                "任务系统强制推进，失败惩罚严苛，爽点密集",
                "系统BUG与隐藏任务，主角卡规则逆天改命",
            ],
            "都市修仙": [
                "末法回归，灵脉复苏，都市里修行与权势碰撞",
                "隐世宗门入世，资源争夺引爆暗战",
            ],
            "神医": [
                "绝世医术+人情冷暖，救人亦破局，打脸爽点",
                "疑难杂症与权贵斗法，医道即江湖",
            ],
            "鉴宝": [
                "古玩圈局中局，真假迷局与人性博弈",
                "捡漏逆袭，赌石拍卖连环反转",
            ],
            "律师": [
                "大案连环，证据链翻盘，法庭对决高能",
                "委托人隐瞒真相，主角在灰色地带求解",
            ],
            "医生": [
                "急诊高压生死线，医患矛盾与人性抉择",
                "医疗黑幕与行业博弈，主角破局自救",
            ],
            "娱乐圈": [
                "练习生逆袭，资源争夺与舆论战",
                "塌房危机与公关反杀，爽点反转",
            ],
            "现代言情": [
                "双向救赎，暧昧拉扯与成长线并行",
                "误会-破局-复合，情绪张力强",
            ],
            "豪门总裁": [
                "契约婚姻开局，利益联姻到真心沦陷",
                "家族争权与情感对抗双线推进",
            ],
            "先婚后爱": [
                "冷婚开局，日常细节升温，甜虐交织",
                "误解解除后高甜反转，情绪爆点",
            ],
            "破镜重圆": [
                "旧爱重逢，真相揭开，反复拉扯",
                "过往伤痕与当下选择，情绪对冲",
            ],
            "甜宠": [
                "高糖日常，双向奔赴，甜而不腻",
                "事业线轻推进，情感线强节奏",
            ],
            "虐恋": [
                "误会与代价堆叠，结局反转救赎",
                "爱而不得与成长线并行",
            ],
            "婚恋": [
                "婚后磨合与家庭矛盾，现实向细节",
                "亲密关系修复，事业与生活双线成长",
            ],
            "萌宝": [
                "带娃日常+身份反转，轻松治愈",
                "萌宝助攻，破局复合高甜",
            ],
            "青春校园": [
                "从同桌到心动，成长与梦想并行",
                "暗恋修成正果，青春遗憾与救赎",
            ],
            "古代言情": [
                "宅斗权谋与情感线交织，反转不断",
                "家族兴衰与个人命运相扣",
            ],
            "宫斗宅斗": [
                "后宅规则与权力斗争，步步惊心",
                "反杀打脸，借势上位，智斗为主",
            ],
            "女强": [
                "女主事业线强推进，情感线不拖沓",
                "爽点：反杀、夺权、打脸、成长",
            ],
            "穿越重生": [
                "重生回到节点，提前布局逆天改命",
                "穿越带金手指，规则清晰，爽点密集",
            ],
            "年代文": [
                "年代烟火与奋斗史，细节真实",
                "家长里短+事业成长双线",
            ],
            "种田": [
                "从贫到富的经营升级，家族发展",
                "田园烟火与商路开拓，节奏轻快",
            ],
            "美食": [
                "以菜品推动剧情，食客故事串联主线",
                "从小摊到名店，经营升级爽点",
            ],
            "扫黑除恶": [
                "扫黑专案组入城，线索链层层反转",
                "保护伞与利益网，主角破局反杀",
            ],
            "悬疑破案": [
                "连环案推进，线索闭环，推理破局",
                "主角带硬核技能，节奏快反转多",
            ],
            "悬疑灵异": [
                "诡案背后有人为操盘，真相反转",
                "规则怪谈与线索推理并行",
            ],
            "犯罪": [
                "黑白对峙，卧底与反卧底局中局",
                "证据链翻盘，追凶高能",
            ],
            "谍战": [
                "潜伏暗战，电报密码与反间计",
                "组织与信仰考验，强悬念推进",
            ],
            "玄幻": [
                "清晰升级体系，资源争夺与宗门对抗",
                "秘境探险与反派压迫，热血高燃",
            ],
            "仙侠": [
                "修行体系严谨，因果代价明确",
                "门派纷争与天道博弈，反转不断",
            ],
            "武侠": [
                "江湖恩怨与门派纷争，拳拳到肉",
                "侠义抉择与权谋交织",
            ],
            "科幻": [
                "硬核科技设定+阴谋反转，节奏明快",
                "星际探索与文明冲突，高燃推进",
            ],
            "赛博朋克": [
                "义体改造与黑客战争，阶层对抗",
                "公司巨头阴谋，反抗者破局",
            ],
            "末世": [
                "灾变求生，基地经营与势力争霸",
                "进化体系清晰，资源争夺反转",
            ],
            "无限流": [
                "副本规则严谨，通关策略与人性博弈",
                "层层升级，隐藏任务反转不断",
            ],
            "历史": [
                "权谋与战争，人物群像，史实氛围",
                "从小人物入局，推动时代洪流",
            ],
            "架空历史": [
                "制度与战争推演，主角借势改制",
                "朝堂党争与边境危机双线推进",
            ],
            "军事": [
                "硬核战术与装备，战场节奏紧凑",
                "军旅成长线，荣誉与牺牲",
            ],
            "游戏": [
                "电竞与现实双线成长，赛场爽点密集",
                "公会争霸与隐藏剧情反转",
            ],
            "电竞": [
                "草根战队逆袭，训练与比赛高燃",
                "团队羁绊与宿敌对抗，爽点反转",
            ],
            "体育": [
                "热血训练与赛事夺冠，成长线清晰",
                "逆风翻盘，团队协作与个人突破",
            ],
            "同人": [
                "在原作世界观内补全遗憾，剧情反转",
                "与原作主线交织，爽点密集",
            ],
            "二次元": [
                "轻松热血与羁绊成长，世界观脑洞与反转",
                "社团日常与主线冒险双线推进，节奏明快",
            ],
        }
        base = builtin.get(t, [])
        extra = []
        if isinstance(getattr(self, "theme_library", None), dict):
            extra = self.theme_library.get(t, []) or []
        generic = [
            "小人物逆袭入局，利益与底线拉扯，反转不断",
            "双线推进：主线升级+暗线真相，节奏明快",
            "旧案牵引当下危机，线索链推理破局",
            "强规则设定：能力体系清晰，代价与限制明确",
            "从局部冲突到体系对抗，螺旋式升级避免重复",
        ]
        merged = []
        seen = set()
        for it in (base + extra + generic):
            s = (it or "").strip()
            if s and s not in seen:
                seen.add(s)
                merged.append(s)
        return merged[:80]

    def on_add_theme(self):
        t = (self.type_var.get() or "").strip()
        theme = (self.theme_var.get() or "").strip()
        if not t:
            messagebox.showwarning("提示", "请先选择小说类型")
            return
        if not theme:
            messagebox.showwarning("提示", "请输入主题/设定")
            return
        if not isinstance(getattr(self, "theme_library", None), dict):
            self.theme_library = {}
        items = list(self.theme_library.get(t, []) or [])
        if theme not in items:
            items.insert(0, theme)
        self.theme_library[t] = items[:200]
        if hasattr(self, "theme_combo"):
            try:
                self.theme_combo["values"] = self._get_theme_suggestions(t)
            except Exception:
                pass
        saved = self._save_theme_library()
        if saved:
            messagebox.showinfo("已加入", "主题已加入主题库，并已保存。")
        else:
            messagebox.showinfo("已加入", "主题已加入主题库（未找到可写 config.json，重启后可能不保留）。")

    def _load_mysql_config(self) -> dict:
        cfg = self._load_config_json()
        mysql = cfg.get("mysql")
        defaults = {
            "host": (os.environ.get("MYSQL_HOST") or "localhost").strip(),
            "port": int(os.environ.get("MYSQL_PORT") or 3306),
            "user": (os.environ.get("MYSQL_USER") or "root").strip(),
            "password": os.environ.get("MYSQL_PASSWORD") or "",
            "database": (os.environ.get("MYSQL_DATABASE") or "xiaoshuo").strip(),
            "charset": "utf8mb4",
        }
        if isinstance(mysql, dict):
            merged = dict(defaults)
            for k, v in mysql.items():
                if v is None:
                    continue
                if isinstance(v, str) and (not v.strip()):
                    continue
                merged[k] = v
            return merged
        return defaults

    def _mysql_connect(self, show_ui: bool = True):
        try:
            import pymysql
        except Exception:
            if show_ui:
                self.root.after(0, messagebox.showerror, "缺少依赖", "未安装 pymysql，无法连接MySQL。请先安装：pip install pymysql")
            return None

        cfg = self._load_mysql_config()
        host = (cfg.get("host") or os.environ.get("MYSQL_HOST") or "").strip()
        port = int(cfg.get("port") or os.environ.get("MYSQL_PORT") or 3306)
        user = (cfg.get("user") or os.environ.get("MYSQL_USER") or "").strip()
        password = cfg.get("password") or os.environ.get("MYSQL_PASSWORD") or ""
        database = (cfg.get("database") or os.environ.get("MYSQL_DATABASE") or "").strip()
        charset = (cfg.get("charset") or "utf8mb4").strip()

        if not host or not user or not database:
            if show_ui:
                cfg_path = self._find_config_path()
                expected = self._get_external_config_path()
                self.root.after(
                    0,
                    messagebox.showerror,
                    "配置缺失",
                    "MySQL 配置不完整，请在 config.json 的 mysql 节点中填写 host/user/database。\n"
                    f"已尝试读取配置：{cfg_path or '未找到配置文件'}\n"
                    f"建议放置配置文件：{expected}\n"
                    "也可设置环境变量 CONFIG_JSON_PATH 指向配置文件。",
                )
            return None

        try:
            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset=charset,
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception as e:
            if show_ui:
                self.root.after(0, messagebox.showerror, "连接失败", _humanize_mysql_connect_error(host, user, database, e))
            return None

    def _consume_token(self, amount: int) -> bool:
        if amount <= 0:
            return True
        if not self.user_id:
            return False

        conn = self._mysql_connect(show_ui=False)
        if not conn:
            self.root.after(0, messagebox.showerror, "扣减失败", "无法连接数据库，无法核减次数卡。")
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT token_balance FROM users WHERE id=%s FOR UPDATE", (self.user_id,))
                row = cur.fetchone() or {}
                bal = int(row.get("token_balance") or 0)
                if bal < amount:
                    conn.rollback()
                    self.token_balance = bal
                    self.root.after(0, self._update_account_ui)
                    return False
                cur.execute("UPDATE users SET token_balance = token_balance - %s WHERE id=%s", (amount, self.user_id))
                cur.execute("SELECT token_balance FROM users WHERE id=%s", (self.user_id,))
                row2 = cur.fetchone() or {}
                new_bal = int(row2.get("token_balance") or 0)
            conn.commit()
            conn.close()
            self.token_balance = new_bal
            self.root.after(0, self._update_account_ui)
            return True
        except Exception:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            self.root.after(0, messagebox.showerror, "扣减失败", "次数卡核减失败，请稍后重试。")
            return False

    def _calc_token_cost_from_text(self, text: str) -> int:
        s = (text or "").strip()
        if not s:
            return 0
        try:
            wc = len(re.sub(r"\s+", "", s))
        except Exception:
            wc = len(s)
        return max(1, (int(wc) + 2) // 3)

    def _update_account_ui(self):
        has_access = bool(self.user_id) and int(self.token_balance or 0) > 0
        if self.user_id:
            self.user_status_var.set(f"已登录：{self.username}")
            self.user_token_var.set(str(int(self.token_balance or 0)))
            self.logout_btn.config(state=tk.NORMAL)
            self.refresh_token_btn.config(state=tk.NORMAL)
        else:
            self.user_status_var.set("未登录")
            self.user_token_var.set("0")
            self.logout_btn.config(state=tk.DISABLED)
            self.refresh_token_btn.config(state=tk.DISABLED)

        state = tk.NORMAL if has_access else tk.DISABLED
        for name in [
            "generate_btn",
            "regen_btn",
        ]:
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.config(state=state)
                except Exception:
                    pass

    def _set_logged_in_user(self, user_row: dict):
        self.user_id = user_row.get("id")
        self.username = user_row.get("username")
        self.token_balance = int(user_row.get("token_balance") or 0)
        self._update_account_ui()

    def on_register(self):
        show_auth_screen(self.root)

    def on_login(self):
        show_auth_screen(self.root)

    def on_logout(self):
        self.user_id = None
        self.username = None
        self.token_balance = 0
        self._update_account_ui()
        show_auth_screen(self.root)

    def on_refresh_token(self):
        if not self.user_id:
            messagebox.showinfo("提示", "请先登录以刷新次数卡")
            return
        conn = self._mysql_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, token_balance FROM users WHERE id=%s", (self.user_id,))
                row = cur.fetchone()
            conn.close()
            if not row:
                messagebox.showerror("刷新失败", "用户不存在或已被删除。")
                self.on_logout()
                return
            self._set_logged_in_user(row)
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            messagebox.showerror("刷新失败", f"刷新次数卡失败：{e}")

    def on_recharge_token(self):
        if not self.user_id:
            messagebox.showinfo("提示", "请先登录以充值Token")
            return
        win = tk.Toplevel(self.root)
        win.title("充值Token")
        win.geometry("420x260")
        win.transient(self.root)
        win.grab_set()

        token_per_yuan = self._load_token_per_yuan()
        yuan_var = tk.StringVar(value="10")
        ttk.Label(win, text="充值金额（元）：").pack(anchor="w", padx=12, pady=(12, 6))

        quick_yuan_var = tk.IntVar(value=10)
        quick = ttk.Frame(win)
        quick.pack(fill=tk.X, padx=12)

        def apply_quick_yuan():
            v = int(quick_yuan_var.get() or 0)
            if v > 0:
                yuan_var.set(str(v))

        ttk.Radiobutton(quick, text="10", variable=quick_yuan_var, value=10, command=apply_quick_yuan).pack(side=tk.LEFT)
        ttk.Radiobutton(quick, text="20", variable=quick_yuan_var, value=20, command=apply_quick_yuan).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(quick, text="50", variable=quick_yuan_var, value=50, command=apply_quick_yuan).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(quick, text="100", variable=quick_yuan_var, value=100, command=apply_quick_yuan).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Radiobutton(quick, text="自定义", variable=quick_yuan_var, value=0).pack(side=tk.RIGHT)

        entry = ttk.Entry(win, textvariable=yuan_var)
        entry.pack(fill=tk.X, padx=12, pady=(8, 0))
        entry.focus_set()

        info_var = tk.StringVar(value="")
        ttk.Label(win, textvariable=info_var, wraplength=390).pack(anchor="w", padx=12, pady=(8, 0))

        qr_wrap = ttk.Frame(win)
        qr_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(10, 0))

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=12)

        alive = True
        polling = False
        start_balance = int(self.token_balance or 0)
        expected_yuan = 0
        expected_token = 0

        def close_win():
            nonlocal alive
            alive = False
            try:
                win.destroy()
            except Exception:
                pass

        def _parse_yuan() -> int | None:
            raw = (yuan_var.get() or "").strip()
            try:
                v = int(raw)
            except Exception:
                return None
            return v

        def update_info():
            v = _parse_yuan()
            if not v or v <= 0:
                info_var.set(f"兑换比例：1元 = {token_per_yuan} Token")
                return
            info_var.set(f"兑换比例：1元 = {token_per_yuan} Token    预计获得：{v * token_per_yuan} Token")

        def _clear_qr():
            for w in qr_wrap.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

        def _render_qr(amount_yuan: int, token_amount: int):
            _clear_qr()
            path = self._load_wechat_pay_qr_path(amount_yuan=amount_yuan, amount_fen=amount_yuan * 100)
            if not path:
                messagebox.showerror("未配置", "未配置微信支付二维码路径，请在 config.json 设置 wechat_pay_qr_path。", parent=win)
                return False
            if not os.path.exists(path):
                fallback = self._load_wechat_pay_qr_path()
                if fallback and os.path.exists(fallback):
                    path = fallback
                else:
                    messagebox.showerror("文件不存在", f"找不到二维码图片：\n{path}", parent=win)
                    return False

            ttk.Label(qr_wrap, text=f"请扫码支付：{amount_yuan} 元").pack(pady=(0, 6))
            ttk.Label(qr_wrap, text=f"支付成功后自动到账：{token_amount} Token").pack(pady=(0, 10))
            wrap = ttk.Frame(qr_wrap)
            wrap.pack(fill=tk.BOTH, expand=True)
            try:
                img = tk.PhotoImage(file=path)
                w = int(img.width() or 0)
                h = int(img.height() or 0)
                max_dim = max(w, h)
                if max_dim > 360:
                    k = (max_dim + 359) // 360
                    img = img.subsample(k, k)
            except Exception as e:
                messagebox.showerror("加载失败", f"二维码图片加载失败：{e}\n\n建议使用PNG格式。", parent=win)
                return False
            lbl = ttk.Label(wrap)
            lbl.pack(expand=True)
            lbl.configure(image=img)
            lbl.image = img
            ttk.Label(qr_wrap, text="支付成功后会自动到账，无需手动操作。").pack(pady=(10, 0))
            return True

        def poll_balance():
            nonlocal alive, polling
            if not alive or not polling:
                return
            conn = self._mysql_connect(show_ui=False)
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT token_balance FROM users WHERE id=%s", (self.user_id,))
                        row = cur.fetchone() or {}
                    try:
                        conn.close()
                    except Exception:
                        pass
                    new_bal = int(row.get("token_balance") or 0)
                    if new_bal != int(self.token_balance or 0):
                        self.token_balance = new_bal
                        try:
                            self.root.after(0, self._update_account_ui)
                        except Exception:
                            pass
                    if new_bal > start_balance:
                        messagebox.showinfo("充值成功", f"已到账 {new_bal - start_balance} Token\n当前余额：{new_bal}", parent=win)
                        close_win()
                        return
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
            try:
                self.root.after(2000, poll_balance)
            except Exception:
                pass

        def confirm_pay():
            nonlocal polling, start_balance, expected_yuan, expected_token
            v = _parse_yuan()
            if v is None:
                messagebox.showerror("输入错误", "请输入整数金额（元）。", parent=win)
                return
            if v <= 0:
                messagebox.showerror("输入错误", "金额必须大于0。", parent=win)
                return
            expected_yuan = v
            expected_token = v * token_per_yuan
            if not _render_qr(expected_yuan, expected_token):
                return
            start_balance = int(self.token_balance or 0)
            polling = True
            try:
                win.geometry("420x620")
            except Exception:
                pass
            poll_balance()

        def paid_refresh():
            poll_balance()

        apply_quick_yuan()
        update_info()
        try:
            yuan_var.trace_add("write", lambda *_: update_info())
        except Exception:
            pass

        ttk.Button(btns, text="确定支付", command=confirm_pay).pack(side=tk.LEFT)
        ttk.Button(btns, text="我已支付", command=paid_refresh).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="取消", command=close_win).pack(side=tk.RIGHT)
        try:
            win.protocol("WM_DELETE_WINDOW", close_win)
        except Exception:
            pass

    def _load_token_per_yuan(self) -> int:
        cfg = self._load_config_json()
        raw = (cfg.get("token_per_yuan") if isinstance(cfg, dict) else None)
        if raw is None:
            raw = os.environ.get("TOKEN_PER_YUAN")
        try:
            v = int(raw)
        except Exception:
            v = 400000
        return v if v > 0 else 400000

    def _load_wechat_pay_qr_path(self, amount_yuan: int | None = None, amount_fen: int | None = None) -> str:
        cfg = self._load_config_json()
        p = (cfg.get("wechat_pay_qr_path") if isinstance(cfg, dict) else "") or ""
        p = str(p).strip()
        if not p:
            p = (os.environ.get("WECHAT_PAY_QR_PATH", "") or "").strip()
        if not p:
            return ""
        if ("{amount_yuan}" in p) or ("{amount_fen}" in p):
            try:
                ay = "" if amount_yuan is None else str(int(amount_yuan))
                af = "" if amount_fen is None else str(int(amount_fen))
                p = p.replace("{amount_yuan}", ay).replace("{amount_fen}", af)
            except Exception:
                pass
        if not os.path.isabs(p):
            p = os.path.join(self._get_app_base_dir(), p)
        return p

    def _load_pay_callback_bind(self) -> str:
        cfg = self._load_config_json()
        bind = (cfg.get("pay_callback_bind") if isinstance(cfg, dict) else "") or ""
        bind = str(bind).strip()
        if not bind:
            bind = (os.environ.get("PAY_CALLBACK_BIND", "") or "").strip()
        return bind or "127.0.0.1"

    def _load_pay_callback_port(self) -> int:
        cfg = self._load_config_json()
        raw = (cfg.get("pay_callback_port") if isinstance(cfg, dict) else None)
        if raw is None:
            raw = os.environ.get("PAY_CALLBACK_PORT")
        try:
            port = int(raw)
        except Exception:
            port = 8765
        if port <= 0 or port > 65535:
            return 8765
        return port

    def _load_pay_callback_secret(self) -> str:
        cfg = self._load_config_json()
        s = (cfg.get("pay_callback_secret") if isinstance(cfg, dict) else "") or ""
        s = str(s).strip()
        if not s:
            s = (os.environ.get("PAY_CALLBACK_SECRET", "") or "").strip()
        return s

    def _get_pay_callback_url(self) -> str:
        bind = self._pay_callback_bind or self._load_pay_callback_bind()
        port = self._pay_callback_port or self._load_pay_callback_port()
        return f"http://{bind}:{port}/pay/wechat/notify"

    def _start_pay_callback_server(self):
        if self._pay_callback_server is not None:
            return

        bind = self._load_pay_callback_bind()
        port = self._load_pay_callback_port()
        secret = self._load_pay_callback_secret()
        self._pay_callback_bind = bind
        self._pay_callback_port = port
        self._pay_callback_secret = secret

        import socketserver
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import urlparse, parse_qs

        app = self

        class _ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
            daemon_threads = True

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _send_json(self, code: int, payload: dict):
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path.rstrip("/") == "/health":
                    self._send_json(200, {"ok": True})
                    return
                self._send_json(404, {"ok": False, "error": "not found"})

            def do_POST(self):
                u = urlparse(self.path)
                if u.path.rstrip("/") not in ("/pay/wechat/notify", "/api/pay/wechat/notify"):
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return

                if app._pay_callback_secret:
                    header_secret = (self.headers.get("X-Callback-Secret", "") or "").strip()
                    qs_secret = (parse_qs(u.query or "").get("secret", [""])[0] or "").strip()
                    if header_secret != app._pay_callback_secret and qs_secret != app._pay_callback_secret:
                        self._send_json(401, {"ok": False, "error": "unauthorized"})
                        return
                else:
                    if (self.client_address[0] or "") not in ("127.0.0.1", "::1"):
                        self._send_json(401, {"ok": False, "error": "unauthorized"})
                        return

                try:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                except Exception:
                    length = 0
                body = self.rfile.read(length) if length > 0 else b""
                try:
                    payload = json.loads(body.decode("utf-8") or "{}")
                except Exception:
                    self._send_json(400, {"ok": False, "error": "invalid json"})
                    return

                if not isinstance(payload, dict):
                    self._send_json(400, {"ok": False, "error": "invalid payload"})
                    return

                resp = app._handle_wechat_pay_callback(payload, raw_body=body.decode("utf-8", errors="ignore"))
                self._send_json(200 if resp.get("ok") else 400, resp)

        try:
            server = _ThreadingHTTPServer((bind, port), _Handler)
        except Exception:
            return

        self._pay_callback_server = server
        t = threading.Thread(target=server.serve_forever, daemon=True)
        self._pay_callback_thread = t
        t.start()

    def _stop_pay_callback_server(self):
        server = self._pay_callback_server
        self._pay_callback_server = None
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

    def _handle_wechat_pay_callback(self, payload: dict, raw_body: str = "") -> dict:
        user_id = payload.get("user_id")
        token_amount = payload.get("token_amount")
        amount_fen = payload.get("amount_fen")
        amount_yuan = payload.get("amount_yuan")
        status = (payload.get("status") or payload.get("trade_state") or payload.get("result_code") or "").strip()
        order_no = (
            (payload.get("out_trade_no") or "")
            or (payload.get("order_no") or "")
            or (payload.get("transaction_id") or "")
        )
        order_no = str(order_no).strip()
        if not order_no:
            order_no = hashlib.sha256((raw_body or json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode("utf-8")).hexdigest()

        try:
            user_id = int(user_id)
        except Exception:
            return {"ok": False, "error": "missing user_id"}
        if user_id <= 0:
            return {"ok": False, "error": "invalid user_id"}

        token_per_yuan = self._load_token_per_yuan()
        resolved_token_amount = None
        try:
            resolved_token_amount = int(token_amount)
        except Exception:
            resolved_token_amount = None
        if resolved_token_amount is None or resolved_token_amount <= 0:
            resolved_fen = None
            if amount_fen is not None:
                try:
                    resolved_fen = int(amount_fen)
                except Exception:
                    resolved_fen = None
            if resolved_fen is not None and resolved_fen > 0:
                resolved_token_amount = int(round((resolved_fen * token_per_yuan) / 100.0))
            elif amount_yuan is not None:
                try:
                    d = Decimal(str(amount_yuan))
                    if d > 0:
                        resolved_token_amount = int((d * Decimal(token_per_yuan)).to_integral_value())
                except InvalidOperation:
                    resolved_token_amount = None

        if resolved_token_amount is None or resolved_token_amount <= 0:
            return {"ok": False, "error": "missing token_amount/amount"}

        paid = str(status).upper() in ("SUCCESS", "PAID", "PAY_SUCCESS", "TRADE_SUCCESS")
        if not paid:
            return {"ok": True, "paid": False, "order_no": order_no}

        conn = self._mysql_connect(show_ui=False)
        if not conn:
            return {"ok": False, "error": "db connect failed"}

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pay_callback_events (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        order_no VARCHAR(128) NOT NULL,
                        user_id BIGINT NOT NULL,
                        token_amount BIGINT NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        raw_body LONGTEXT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY uniq_order_no (order_no)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    "INSERT IGNORE INTO pay_callback_events (order_no, user_id, token_amount, status, raw_body) VALUES (%s, %s, %s, %s, %s)",
                    (order_no, user_id, resolved_token_amount, "SUCCESS", raw_body or ""),
                )
                inserted = int(getattr(cur, "rowcount", 0) or 0) > 0
                if inserted:
                    cur.execute("UPDATE users SET token_balance = token_balance + %s WHERE id=%s", (resolved_token_amount, user_id))
                cur.execute("SELECT token_balance FROM users WHERE id=%s", (user_id,))
                row = cur.fetchone() or {}
                new_bal = int(row.get("token_balance") or 0)
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            return {"ok": False, "error": str(e)}
        try:
            conn.close()
        except Exception:
            pass

        if inserted and self.user_id == user_id:
            self.token_balance = new_bal
            try:
                self.root.after(0, self._update_account_ui)
            except Exception:
                pass

        return {"ok": True, "paid": True, "order_no": order_no, "credited": bool(inserted), "token_balance": new_bal}

    def _show_wechat_pay_qr(self, parent=None, amount_yuan: int | None = None, token_amount: int | None = None):
        fen = None if amount_yuan is None else int(amount_yuan) * 100
        path = self._load_wechat_pay_qr_path(amount_yuan=amount_yuan, amount_fen=fen)
        if not path:
            messagebox.showerror("未配置", "未配置微信支付二维码路径，请在 config.json 设置 wechat_pay_qr_path。", parent=parent or self.root)
            return
        if not os.path.exists(path):
            fallback = self._load_wechat_pay_qr_path()
            if fallback and os.path.exists(fallback):
                path = fallback
            else:
                messagebox.showerror("文件不存在", f"找不到二维码图片：\n{path}", parent=parent or self.root)
                return

        win = tk.Toplevel(parent or self.root)
        win.title("微信支付二维码")
        win.geometry("420x520")
        win.transient(parent or self.root)
        win.grab_set()

        ttk.Label(win, text="请使用微信扫码支付").pack(padx=12, pady=(12, 6))
        if amount_yuan:
            ttk.Label(win, text=f"支付金额：{int(amount_yuan)} 元").pack(padx=12, pady=(0, 2))
        if token_amount:
            ttk.Label(win, text=f"到账Token：{int(token_amount)}").pack(padx=12, pady=(0, 8))
        wrap = ttk.Frame(win)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        try:
            img = tk.PhotoImage(file=path)
            w = int(img.width() or 0)
            h = int(img.height() or 0)
            max_dim = max(w, h)
            if max_dim > 360:
                k = (max_dim + 359) // 360
                img = img.subsample(k, k)
        except Exception as e:
            messagebox.showerror("加载失败", f"二维码图片加载失败：{e}\n\n建议使用PNG格式。", parent=win)
            win.destroy()
            return

        lbl = ttk.Label(wrap)
        lbl.pack(expand=True)
        lbl.configure(image=img)
        lbl.image = img
        ttk.Label(win, text="支付成功后将自动到账，可在主界面查看Token余额。").pack(padx=12, pady=(8, 12))

    def _open_auth_dialog(self, mode: str):
        win = tk.Toplevel(self.root)
        win.title("注册" if mode == "register" else "登录")
        win.geometry("360x220")
        win.transient(self.root)
        win.grab_set()

        username_var = tk.StringVar()
        password_var = tk.StringVar()

        ttk.Label(win, text="用户名：").pack(anchor="w", padx=12, pady=(12, 6))
        username_entry = ttk.Entry(win, textvariable=username_var)
        username_entry.pack(fill=tk.X, padx=12)

        ttk.Label(win, text="密码：").pack(anchor="w", padx=12, pady=(12, 6))
        password_entry = ttk.Entry(win, textvariable=password_var, show="*")
        password_entry.pack(fill=tk.X, padx=12)

        btns = ttk.Frame(win)
        btns.pack(fill=tk.X, padx=12, pady=12)

        def submit():
            username = (username_var.get() or "").strip()
            password = (password_var.get() or "").strip()
            if not username or not password:
                messagebox.showerror("输入错误", "请输入用户名和密码。", parent=win)
                return

            conn = self._mysql_connect()
            if not conn:
                return

            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, username, password_hash, token_balance FROM users WHERE username=%s", (username,))
                    row = cur.fetchone()

                    if mode == "register":
                        if row:
                            messagebox.showerror("注册失败", "用户名已存在。", parent=win)
                            conn.close()
                            return
                        pwd_hash = hash_password(password)
                        register_ip = ""
                        register_mac_raw = ""
                        register_mac = ""
                        try:
                            resp = requests.get("https://api.ipify.org?format=json", timeout=3)
                            if resp.ok:
                                data = resp.json()
                                v = (data.get("ip") if isinstance(data, dict) else "") or ""
                                register_ip = str(v).strip()
                        except Exception:
                            register_ip = ""
                        try:
                            node = uuid.getnode()
                            if isinstance(node, int):
                                mac_hex = f"{node:012x}"
                                register_mac_raw = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper()
                        except Exception:
                            register_mac_raw = ""
                        try:
                            if register_mac_raw:
                                register_mac = hashlib.md5(register_mac_raw.encode("utf-8")).hexdigest().upper()
                        except Exception:
                            register_mac = ""
                        has_reg_ip = False
                        has_reg_mac = False
                        try:
                            cur.execute("SHOW COLUMNS FROM users LIKE 'register_ip'")
                            has_reg_ip = cur.fetchone() is not None
                        except Exception:
                            has_reg_ip = False
                        try:
                            cur.execute("SHOW COLUMNS FROM users LIKE 'register_mac'")
                            has_reg_mac = cur.fetchone() is not None
                        except Exception:
                            has_reg_mac = False
                        gift_times = 3
                        try:
                            gift_times = 3
                        except Exception:
                            gift_times = 3
                        cols = ["username", "password_hash", "status", "token_balance"]
                        params = [username, pwd_hash, 1, int(gift_times)]
                        if has_reg_ip:
                            cols.append("register_ip")
                            params.append(register_ip or None)
                        if has_reg_mac:
                            cols.append("register_mac")
                            params.append(register_mac or None)
                        placeholders = ", ".join(["%s"] * len(params))
                        cur.execute(
                            f"INSERT INTO users ({', '.join(cols)}, created_at) VALUES ({placeholders}, NOW())",
                            tuple(params),
                        )
                        cur.execute("SELECT id, username, token_balance FROM users WHERE username=%s", (username,))
                        row2 = cur.fetchone()
                        conn.commit()
                        conn.close()
                        if row2:
                            self._set_logged_in_user(row2)
                        win.destroy()
                        return

                    if not row or not check_password(row.get("password_hash") or "", password):
                        messagebox.showerror("登录失败", "用户名或密码错误。", parent=win)
                        conn.close()
                        return
                    cur.execute("UPDATE users SET last_login_at = NOW() WHERE id=%s", (row["id"],))
                    cur.execute("SELECT id, username, token_balance FROM users WHERE id=%s", (row["id"],))
                    row2 = cur.fetchone()
                conn.commit()
                conn.close()
                if row2:
                    self._set_logged_in_user(row2)
                win.destroy()
            except Exception as e:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
                messagebox.showerror("操作失败", f"{e}", parent=win)

        ttk.Button(btns, text="确认", command=submit).pack(side=tk.RIGHT)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side=tk.RIGHT, padx=8)
        username_entry.focus_set()

    def on_provider_changed(self):
        p = self.provider_var.get()
        if p == "Gemini":
            self.model_combo['values'] = [DEFAULT_GEMINI_MODEL, "gemini-2.5-pro", "gemini-2.0-flash"]
            self.model_var.set(DEFAULT_GEMINI_MODEL)
        elif p == "Claude":
            self.model_combo['values'] = [
                DEFAULT_CLAUDE_MODEL,
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
            ]
            self.model_var.set(DEFAULT_CLAUDE_MODEL)
        else:
            default_model = (self._load_doubao_model() or "").strip()
            values = []
            if default_model:
                values.append(default_model)
            values.extend(["ep-xxxxxxxxxxxxxxxx-xxxxx"])
            self.model_combo['values'] = list(dict.fromkeys(values))
            self.model_var.set(default_model)

    def on_type_changed(self, event):
        t = self.type_var.get()
        suggestions = self._get_theme_suggestions(t)
        if hasattr(self, "theme_combo"):
            try:
                self.theme_combo["values"] = suggestions
            except Exception:
                pass
        if suggestions:
            self.theme_var.set(suggestions[0])

    def on_generate(self):
        if not self._require_login_and_token():
            return
        if not self._consume_token(1):
            messagebox.showerror("次数卡不足", "次数卡不足，无法继续生成。")
            return

        provider = "Gemini"
        api_key = self._load_api_key("Gemini")
        
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return
            
        novel_type = self.type_var.get().strip()
        theme = self.theme_var.get().strip()
        model = (self.model_var.get() or DEFAULT_GEMINI_MODEL).strip()
        if not model:
            model = DEFAULT_GEMINI_MODEL
            self.model_var.set(model)
        
        self._cancel_event.clear()
        self._pause_event.clear()
        self.generate_btn.config(state=tk.DISABLED)
        self.regen_btn.config(state=tk.DISABLED)
        try:
            self.pause_btn.config(state=tk.NORMAL, text="暂停")
        except Exception:
            pass
        
        self.output.delete("1.0", tk.END)
        self.output.insert(
            tk.END,
            "温馨提示：大纲生成过程中请不要关闭软件，以免浪费次数并造成不必要的损失。\n\n",
        )
        self.output.insert(tk.END, f"正在生成大纲...（模型：{model}）\n\n")
        self.status_var.set("预计完成时间计算中...")
        self.progress_var.set("进度 0/0")
        self.chapters_data = []
        self.all_chapter_summaries = [] 
        self.last_optimized_instruction = ""
        self.last_constraints_text = ""
        
        try:
            chapters = int(self.chapters_var.get())
        except ValueError:
            chapters = 24
        
        chapters = max(1, min(1000, chapters)) 

        try:
            volumes = int(self.volumes_var.get())
        except ValueError:
            volumes = 1
        volumes = max(1, min(100, volumes))
        volumes = min(volumes, chapters)
        
        threading.Thread(target=self._run_generation, args=(provider, api_key, model, novel_type, theme, chapters, volumes), daemon=True).start()

    def on_regenerate_with_feedback(self):
        if not self._require_login_and_token():
            return
        if not self._consume_token(1):
            messagebox.showerror("次数卡不足", "次数卡不足，无法继续生成。")
            return

        provider = "Gemini"
        api_key = self._load_api_key("Gemini")
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return

        feedback = (self.feedback_text.get("1.0", tk.END) if hasattr(self, "feedback_text") else "").strip()
        if not feedback:
            messagebox.showwarning("提示", "请先粘贴修改意见")
            return

        base_outline = (self.full_outline_context or "").strip()
        if not base_outline:
            base_outline = self.output.get("1.0", tk.END).strip()
        if not base_outline:
            messagebox.showwarning("提示", "当前没有可修改的大纲，请先生成或粘贴大纲")
            return

        novel_type = self.type_var.get().strip()
        theme = self.theme_var.get().strip()
        model = (self.model_var.get() or DEFAULT_GEMINI_MODEL).strip()
        if not model:
            model = DEFAULT_GEMINI_MODEL
            self.model_var.set(model)

        try:
            chapters = int(self.chapters_var.get())
        except ValueError:
            chapters = 24
        chapters = max(1, min(1000, chapters))

        try:
            volumes = int(self.volumes_var.get())
        except ValueError:
            volumes = 1
        volumes = max(1, min(100, volumes))
        volumes = min(volumes, chapters)

        self._cancel_event.clear()
        self._pause_event.clear()
        self.generate_btn.config(state=tk.DISABLED)
        self.regen_btn.config(state=tk.DISABLED)
        try:
            self.pause_btn.config(state=tk.NORMAL, text="暂停")
        except Exception:
            pass

        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, f"正在修改大纲（{provider} / {model}）...\n\n")
        self.status_var.set("预计完成时间计算中...")
        self.progress_var.set("进度 0/0")
        self.chapters_data = []
        self.all_chapter_summaries = []

        threading.Thread(
            target=self._run_regenerate_outline,
            args=(provider, api_key, model, novel_type, theme, chapters, volumes, base_outline, feedback),
            daemon=True,
        ).start()

    def on_import_outline(self):
        path = filedialog.askopenfilename(
            title="选择大纲文件",
            filetypes=[("Text/Markdown", "*.txt *.md"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = (f.read() or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        if not text:
            messagebox.showwarning("提示", "文件内容为空")
            return

        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text + "\n")
        self.full_outline_context = text
        self.last_outline_path = path
        self._sync_chapters_from_text(text, show_message=True)

    def on_apply_feedback_to_chapters(self):
        if not self._require_login_and_token():
            return
        provider = "Gemini"
        api_key = self._load_api_key("Gemini")
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return

        feedback = (self.feedback_text.get("1.0", tk.END) if hasattr(self, "feedback_text") else "").strip()
        if not feedback:
            messagebox.showwarning("提示", "请先粘贴修改意见")
            return

        base_outline = (self.full_outline_context or "").strip()
        if not base_outline:
            base_outline = self.output.get("1.0", tk.END).strip()
        if not base_outline:
            messagebox.showwarning("提示", "当前没有可修改的大纲，请先上传/生成/粘贴大纲")
            return

        novel_type = self.type_var.get().strip()
        theme = self.theme_var.get().strip()
        model = self.model_var.get().strip()
        if provider == "Doubao" and (not model):
            messagebox.showerror("错误", "豆包模型请填写 Ark 的 Endpoint ID（形如 ep-...），可在火山引擎 Ark 控制台获取")
            return

        self._sync_chapters_from_text(base_outline, show_message=False)
        if not self.chapters_data:
            messagebox.showwarning("提示", "未能从大纲解析出章节（请确保包含“第X章”格式或“### 第X章”格式）")
            return

        self._cancel_event.clear()
        self.generate_btn.config(state=tk.DISABLED)
        self.regen_btn.config(state=tk.DISABLED)
        if hasattr(self, "apply_feedback_btn"):
            self.apply_feedback_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.DISABLED)
        self.export_zip_btn.config(state=tk.DISABLED)
        self.generate_novel_btn.config(state=tk.DISABLED)
        if hasattr(self, "generate_novel_zip_btn"):
            self.generate_novel_zip_btn.config(state=tk.DISABLED)
        self.parse_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)
        self.polish_btn.config(state=tk.DISABLED)

        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, f"正在按修改意见修改指定章节（{provider} / {model}）...\n\n")
        self.status_var.set("预计完成时间计算中...")
        self.progress_var.set("进度 0/0")

        threading.Thread(
            target=self._run_apply_feedback_to_chapters,
            args=(provider, api_key, model, novel_type, theme, base_outline, feedback),
            daemon=True,
        ).start()

    def on_stop(self):
        self._cancel_event.set()
        try:
            if hasattr(self, "pause_btn"):
                self.pause_btn.config(state=tk.DISABLED, text="暂停")
        except Exception:
            pass
        self.status_var.set("正在停止...")
        self._append_text("\n\n[系统] 收到停止指令，正在尽快停止...\n")

    def on_toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            try:
                self.pause_btn.config(text="暂停")
            except Exception:
                pass
            self.status_var.set("继续生成中...")
            self._append_text("\n\n[系统] 已继续生成。\n")
            return

        self._pause_event.set()
        try:
            self.pause_btn.config(text="继续")
        except Exception:
            pass
        self.status_var.set("已暂停")
        self._append_text("\n\n[系统] 已暂停，点击“继续”恢复生成。\n")

    def _parse_chapters_from_outline_text(self, text: str):
        matches = list(
            re.finditer(
                r"(?:^|\n)\s*###\s*第\s*(\d+)\s*章\s*(?:[:：]\s*([^\n]*?)\s*)?\n\s*([\s\S]*?)(?=(?:\n\s*###\s*第\s*\d+\s*章)|\s*$)",
                text,
            )
        )
        if not matches:
            matches = list(
                re.finditer(
                    r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)",
                    text,
                )
            )
        if not matches:
            matches = list(
                re.finditer(
                    r"(第\s*(\d+)\s*章\s*([^\n:：]*?))\s*(?:[:：\n]|-{2,}|—{2,})\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)",
                    text,
                )
            )
        chapters = {}
        for m in matches:
            groups = m.groups()
            if len(groups) == 3:
                try:
                    c_num = int(m.group(1))
                except Exception:
                    continue
                title_clean = (m.group(2) or "").strip()
                summary = (m.group(3) or "").strip()
            else:
                try:
                    c_num = int(m.group(2))
                except Exception:
                    continue
                title_only = (m.group(3) or "").strip()
                full_title_part = (m.group(1) or "").strip()
                title_clean = re.sub(r"^第\s*\d+\s*章\s*", "", full_title_part).strip()
                if title_only:
                    title_clean = title_only
                summary = (m.group(4) or "").strip()
            if not title_clean and summary:
                m2 = re.match(r"^([^\n:：]{1,40})\s*[:：]\s*(.+)$", summary)
                if m2:
                    title_clean = (m2.group(1) or "").strip()
                    summary = (m2.group(2) or "").strip()
            if not summary:
                summary = "无内容"
            chapters[c_num] = {
                "chapter": c_num,
                "title": title_clean,
                "summary": summary,
            }
        return chapters

    def _detect_outline_missing(self, text: str):
        missing = []
        if "作品名：" not in text or "类型：" not in text:
            missing.append("作品名与类型")
        if len(re.findall(r"角色：", text)) < 3:
            missing.append("核心人设")
        if ("时代：" not in text) and ("权力结构：" not in text) and ("世界观" not in text):
            missing.append("世界观与设定")
        if len(re.findall(r"^\s*-\s+", text, flags=re.MULTILINE)) < 8:
            missing.append("爽点清单")
        if ("ACT1" not in text) and ("ACT2" not in text) and ("ACT3" not in text) and ("三幕" not in text):
            missing.append("三幕结构梗概")
        if ("short_term：" not in text) and ("mid_term：" not in text) and ("long_term：" not in text) and ("钩子" not in text) and ("悬念" not in text):
            missing.append("读者钩子与悬念设计")
        if ("支线：" not in text) and ("后续走向" not in text) and ("future_arcs" not in text):
            missing.append("可扩展支线与后续走向")
        return missing

    def _synthesize_missing_chapter(self, existing: dict, n: int):
        prev_item = existing.get(n - 1) if n > 1 else None
        next_item = existing.get(n + 1)
        prev_title = (prev_item.get("title") or "").strip() if isinstance(prev_item, dict) else ""
        prev_summary = (prev_item.get("summary") or "").strip() if isinstance(prev_item, dict) else ""
        next_title = (next_item.get("title") or "").strip() if isinstance(next_item, dict) else ""
        next_summary = (next_item.get("summary") or "").strip() if isinstance(next_item, dict) else ""

        title = "线索回扣"
        if prev_title and next_title:
            title = f"{prev_title}后的余波"
        elif prev_title:
            title = f"{prev_title}的转折"
        elif next_title:
            title = f"通往{next_title}"

        if prev_title or prev_summary:
            content = "承接上一章余波，主角顶住压力推进关键行动，拿到阶段性成果并稳住局面。"
        else:
            content = "主线快速推进，主角做出关键决策并立即付诸行动，剧情节点清晰落点。"
        suspense = "推进过程中出现反常细节与矛盾证据，线索隐隐指向更深层的幕后势力。"
        shuang = "主角抓住破绽强势反制，拿到关键证据/资源，令对手短暂吃亏。"
        summary = f"**内容**：{content}\n**【悬疑点】**：{suspense}\n**【爽点】**：{shuang}"
        return title, summary

    def _build_chapter_range_context(self, full_text: str, existing: dict, a: int, b: int) -> str:
        head = (full_text or "")[:5000].strip()
        lines = []
        start = max(1, a - 12)
        end = b + 12
        for k in range(start, end + 1):
            if k in existing:
                t = (existing[k].get("title") or "").strip()
                s = (existing[k].get("summary") or "").strip()
                if t or s:
                    lines.append(f"第{k}章 {t}：{s}")
        block = "\n".join(lines).strip()
        if head and block:
            return head + "\n\n【相关章节上下文】\n" + block
        if block:
            return "【相关章节上下文】\n" + block
        return head

    def on_check_and_fill_outline(self):
        if not self._require_login_and_token():
            return
        provider = "Gemini"
        api_key = self._load_api_key("Gemini")
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return

        novel_type = self.type_var.get().strip()
        theme = self.theme_var.get().strip()
        model = self.model_var.get().strip()
        if provider == "Doubao" and (not model):
            messagebox.showerror("错误", "豆包模型请填写 Ark 的 Endpoint ID（形如 ep-...），可在火山引擎 Ark 控制台获取")
            return

        text = self.output.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "当前没有大纲内容，请先生成或粘贴大纲")
            return

        try:
            desired_chapters = int(self.expand_to_var.get())
        except ValueError:
            try:
                desired_chapters = int(self.chapters_var.get())
            except ValueError:
                desired_chapters = 24
        desired_chapters = max(1, min(1000, desired_chapters))

        try:
            volumes = int(self.volumes_var.get())
        except ValueError:
            volumes = 1
        volumes = max(1, min(100, volumes))

        self.generate_btn.config(state=tk.DISABLED)
        self.regen_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.export_zip_btn.config(state=tk.DISABLED)
        self.generate_novel_btn.config(state=tk.DISABLED)
        if hasattr(self, "generate_novel_zip_btn"):
            self.generate_novel_zip_btn.config(state=tk.DISABLED)
        self.parse_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)
        self.polish_btn.config(state=tk.DISABLED)
        self._cancel_event.clear()
        self.stop_btn.config(state=tk.NORMAL)

        self.root.after(0, self._append_text, "\n\n[系统] 开始检查大纲完整性，并补全缺失内容...\n")
        threading.Thread(
            target=self._run_check_and_fill_outline,
            args=(provider, api_key, model, novel_type, theme, desired_chapters, volumes, text),
            daemon=True,
        ).start()

    def on_check_outline_suggestions(self):
        if not self._require_login_and_token():
            return
        provider = "Gemini"
        api_key = self._load_api_key("Gemini")
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return

        novel_type = self.type_var.get().strip()
        theme = self.theme_var.get().strip()
        model = self.model_var.get().strip()
        if provider == "Doubao" and (not model):
            messagebox.showerror("错误", "豆包模型请填写 Ark 的 Endpoint ID（形如 ep-...），可在火山引擎 Ark 控制台获取")
            return

        text = (self.full_outline_context or "").strip()
        if not text:
            text = self.output.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "当前没有大纲内容，请先上传/生成/粘贴大纲")
            return

        self._sync_chapters_from_text(text, show_message=False)

        self.generate_btn.config(state=tk.DISABLED)
        if hasattr(self, "regen_btn"):
            self.regen_btn.config(state=tk.DISABLED)
        if hasattr(self, "apply_feedback_btn"):
            self.apply_feedback_btn.config(state=tk.DISABLED)
        if hasattr(self, "check_suggest_btn"):
            self.check_suggest_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.export_zip_btn.config(state=tk.DISABLED)
        self.generate_novel_btn.config(state=tk.DISABLED)
        if hasattr(self, "generate_novel_zip_btn"):
            self.generate_novel_zip_btn.config(state=tk.DISABLED)
        self.parse_btn.config(state=tk.DISABLED)
        self.check_btn.config(state=tk.DISABLED)
        self.polish_btn.config(state=tk.DISABLED)
        self._cancel_event.clear()
        self.stop_btn.config(state=tk.NORMAL)

        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, f"正在检查大纲并生成修改意见（{provider} / {model}）...\n\n")
        self.status_var.set("预计完成时间计算中...")
        self.progress_var.set("进度 0/0")

        threading.Thread(
            target=self._run_check_outline_suggestions,
            args=(provider, api_key, model, novel_type, theme, text),
            daemon=True,
        ).start()

    def _generate_json_via_provider(self, provider, api_key, model_name, novel_type, theme, contents_text, user_prompt, schema):
        system_text = build_system_instruction() + "\n" + build_constraints(novel_type, theme, self.channel_var.get()) + "\n你正在对已有大纲做完整性校验与补全。必须承接已有内容，不得推翻重写；只补全缺失项。严格按要求输出。"

        if provider in ("Doubao", "Claude"):
            base_url = self._load_doubao_base_url() if provider == "Doubao" else ""
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                prompt = (
                    f"【已有大纲内容（上下文参考）】\n{ctx}\n"
                    f"----------------\n"
                    f"{user_prompt}\n\n"
                    f"请务必严格输出合法的 JSON，不要包含 Markdown 代码块标记。"
                )
                try:
                    if provider == "Claude":
                        text_out = self._call_claude(api_key, model_name, system_text, prompt, temperature=0.4, max_tokens=4096)
                    else:
                        text_out = self._call_compat_chat(api_key, model_name, system_text, prompt, temperature=0.4, base_url=base_url)
                except Exception:
                    text_out = ""
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fix_prompt = f"上一次输出的 JSON 格式有误，请修正为合法的 JSON，且严格匹配 schema：\n{json.dumps(schema, ensure_ascii=False)}\n\n原输出：\n{text_out}"
                    try:
                        if provider == "Claude":
                            fixed = self._call_claude(api_key, model_name, system_text, fix_prompt, temperature=0.1, max_tokens=4096)
                        else:
                            fixed = self._call_compat_chat(api_key, model_name, system_text, fix_prompt, temperature=0.1, base_url=base_url)
                    except Exception:
                        fixed = ""
                    json_data = self._parse_json(fixed)
                    if json_data is not None:
                        return json_data
            return None

        client = genai.Client(api_key=api_key)
        tools = []
        base_models = [model_name]
        if "gemini" in model_name.lower() and model_name != "gemini-2.5-pro":
            base_models.append("gemini-2.5-pro")
        if "gemini" in model_name.lower() and model_name != "gemini-2.0-flash":
            base_models.append("gemini-2.0-flash")

        for max_tokens in [2500, 1800, 1200]:
            config = types.GenerateContentConfig(
                system_instruction=[types.Part.from_text(text=system_text)],
                tools=tools,
                temperature=0.6,
                max_output_tokens=max_tokens,
                top_p=0.95,
            )
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=user_prompt),
                            types.Part.from_text(text=f"\n\n【上下文参考】\n{ctx}\n"),
                        ],
                    )
                ]
                config_local = types.GenerateContentConfig(
                    system_instruction=config.system_instruction,
                    tools=config.tools,
                    temperature=0.4,
                    max_output_tokens=config.max_output_tokens,
                    top_p=config.top_p,
                    response_mime_type="application/json",
                    response_schema=schema,
                )
                text_out = self._generate_with_fallback(client, base_models, contents, config_local, max_request_retries=4, max_empty_retries=10)
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fixed_json_text = self._correct_section_json(client, base_models, "补全", text_out, user_prompt, config_local, schema)
                    json_data = self._parse_json(fixed_json_text)
                    if json_data is not None:
                        return json_data
        return None

    def _post_fill_missing_after_generation(self, provider, api_key, model_name, novel_type, theme, desired_chapters, volumes, text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.strip()
        if not text:
            return ""

        try:
            desired = max(1, min(1000, int(desired_chapters or 1)))
        except Exception:
            desired = 24
        try:
            volumes = max(1, min(100, int(volumes or 1)))
        except Exception:
            volumes = 1

        missing_sections = self._detect_outline_missing(text)
        for sec in missing_sections:
            if self._cancel_event.is_set():
                return text
            if sec == "作品名与类型":
                schema = {
                    "type": "OBJECT",
                    "required": ["title", "genre"],
                    "properties": {"title": {"type": "STRING"}, "genre": {"type": "STRING"}},
                }
                prompt = "任务：补全《作品名与类型》。请只输出 JSON，其中包含 title 与 genre。"
            elif sec == "核心人设":
                schema = {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "required": ["role", "name", "identity", "desire", "weakness", "growth"],
                        "properties": {
                            "role": {"type": "STRING"},
                            "name": {"type": "STRING"},
                            "identity": {"type": "STRING"},
                            "desire": {"type": "STRING"},
                            "weakness": {"type": "STRING"},
                            "growth": {"type": "STRING"},
                        },
                    },
                }
                prompt = "任务：补全《核心人设》。请只输出 JSON 数组，必须包含主角、对手、导师、盟友四类角色。"
            elif sec == "世界观与设定":
                schema = {
                    "type": "OBJECT",
                    "required": ["era", "region", "power_structure", "resources", "rules", "scenes"],
                    "properties": {
                        "era": {"type": "STRING"},
                        "region": {"type": "STRING"},
                        "power_structure": {"type": "STRING"},
                        "resources": {"type": "STRING"},
                        "rules": {"type": "STRING"},
                        "scenes": {"type": "STRING"},
                    },
                }
                prompt = "任务：补全《世界观与设定》。请只输出 JSON，包含 era、region、power_structure、resources、rules、scenes。"
            elif sec == "爽点清单":
                schema = {"type": "ARRAY", "items": {"type": "STRING"}}
                prompt = "任务：补全《爽点清单》。请只输出 JSON 数组，不少于12条，每条一句。"
            elif sec == "三幕结构梗概":
                schema = {
                    "type": "OBJECT",
                    "required": ["act1", "act2", "act3"],
                    "properties": {
                        "act1": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "act2": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "act3": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                }
                prompt = "任务：补全《三幕结构梗概》。请只输出 JSON，包含 act1、act2、act3 三个数组，每幕不少于5项。"
            elif sec == "读者钩子与悬念设计":
                schema = {
                    "type": "OBJECT",
                    "required": ["short_term", "mid_term", "long_term"],
                    "properties": {
                        "short_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "mid_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "long_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                }
                prompt = "任务：补全《读者钩子与悬念设计》。请只输出 JSON，包含 short_term、mid_term、long_term 三个数组。"
            else:
                schema = {
                    "type": "OBJECT",
                    "required": ["side_plots", "future_arcs"],
                    "properties": {
                        "side_plots": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "future_arcs": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                }
                prompt = "任务：补全《可扩展支线与后续走向》。请只输出 JSON，包含 side_plots 与 future_arcs 两个数组。"

            data = self._generate_json_via_provider(provider, api_key, model_name, novel_type, theme, text, prompt, schema)
            if data is None:
                continue
            formatted = self._format_from_data(sec, data)
            if formatted:
                add_block = f"\n\n### 补全：{sec}\n{formatted}\n"
                text += add_block
                self.root.after(0, self._append_text, add_block)

        existing = self._parse_chapters_from_outline_text(text)
        missing_nums = [n for n in range(1, desired + 1) if n not in existing]
        if missing_nums:
            self.root.after(0, self._append_text, f"\n\n[系统] 检测到缺失章节 {len(missing_nums)} 章，开始补全...\n")

        ranges = []
        for n in missing_nums:
            if not ranges or n != ranges[-1][1] + 1:
                ranges.append([n, n])
            else:
                ranges[-1][1] = n

        schema_chaps = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["chapter", "title", "summary"],
                "properties": {
                    "chapter": {"type": "INTEGER"},
                    "title": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                },
            },
        }

        def fill_range(a: int, b: int):
            nonlocal text, existing
            if self._cancel_event.is_set():
                return
            need_nums = [n for n in range(a, b + 1) if n not in existing]
            if not need_nums:
                return
            need_str = ", ".join(str(x) for x in need_nums[:40])
            prompt = (
                f"任务：补全章节大纲缺失章节。\n"
                f"范围：第{a}章-第{b}章。\n"
                f"只补全这些缺失章号：{need_str}。\n"
                f"要求：\n"
                f"1. 只输出 JSON 数组；每项包含 chapter(整数)、title(章节标题)、summary。\n"
                f"2. title 不要带“第X章”。\n"
                f"3. summary 必须严格使用如下格式（爽点允许为“暂无”，其余不得留空）：**内容**：... **【悬疑点】**：... **【爽点】**：...\n"
                f"4. 必须承接上下文，避免逻辑冲突。\n"
            )
            range_context = self._build_chapter_range_context(text, existing, a, b)
            data = self._generate_json_via_provider(provider, api_key, model_name, novel_type, theme, range_context, prompt, schema_chaps)
            items = self._ensure_list(data) if data is not None else []
            by_ch = {}
            for it in items:
                if not isinstance(it, dict) or "chapter" not in it:
                    continue
                try:
                    cn = int(it.get("chapter"))
                except Exception:
                    continue
                if cn not in need_nums:
                    continue
                by_ch[cn] = {
                    "chapter": cn,
                    "title": (it.get("title") or "").strip() or "未命名",
                    "summary": (it.get("summary") or "").strip() or "无内容",
                }
            if not by_ch:
                return
            for cn, it in by_ch.items():
                if cn not in existing:
                    existing[cn] = it
            ordered = [existing[n] for n in sorted(by_ch.keys())]
            formatted = self._format_from_data(f"章节大纲 第{a}-{b}章", ordered)
            if formatted:
                add_block = f"\n\n### 补全：章节大纲 第{a}-{b}章\n{formatted}\n"
                text += add_block
                self.root.after(0, self._append_text, add_block)

        stack = [(r[0], r[1]) for r in ranges]
        while stack and (not self._cancel_event.is_set()):
            a, b = stack.pop()
            need = [n for n in range(a, b + 1) if n not in existing]
            if not need:
                continue
            if len(need) > 15:
                cur = a
                while cur <= b:
                    ce = min(cur + 14, b)
                    stack.append((cur, ce))
                    cur = ce + 1
                continue
            fill_range(a, b)

        existing = self._parse_chapters_from_outline_text(text)
        final_missing = [n for n in range(1, desired + 1) if n not in existing]
        if final_missing:
            for n in final_missing:
                title, summary = self._synthesize_missing_chapter(existing, n)
                existing[n] = {"chapter": n, "title": title, "summary": summary}
            ordered = [existing[n] for n in range(1, desired + 1)]
            formatted = self._format_from_data(f"章节大纲 第1-{desired}章", ordered)
            if formatted:
                add_block = f"\n\n### 补全：章节大纲 第1-{desired}章（兜底）\n{formatted}\n"
                text += add_block
                self.root.after(0, self._append_text, add_block)

        existing = self._parse_chapters_from_outline_text(text)
        if isinstance(existing, dict) and existing:
            self.chapters_data = [existing[k] for k in sorted(existing.keys()) if 1 <= int(k) <= desired]
            self.all_chapter_summaries = [
                f"第{it.get('chapter')}章：{(it.get('summary') or '').strip()}"
                for it in self.chapters_data
                if isinstance(it, dict) and it.get("chapter") is not None
            ]
        self.full_outline_context = text.strip()
        return text

    def _run_check_and_fill_outline(self, provider, api_key, model_name, novel_type, theme, desired_chapters, volumes, text):
        try:
            self._setup_logger(novel_type, theme, desired_chapters)
            if self.logger:
                self.logger.info("开始检查并补全大纲")

            existing = self._parse_chapters_from_outline_text(text)
            max_found = max(existing.keys()) if existing else 0
            desired = max(desired_chapters, max_found)
            desired = max(1, min(1000, desired))
            volumes = max(1, min(int(volumes or 1), desired))

            missing_sections = self._detect_outline_missing(text)
            if missing_sections:
                self.root.after(0, self._append_text, f"[系统] 发现缺失关键模块：{', '.join(missing_sections)}\n")

            for sec in missing_sections:
                if sec == "作品名与类型":
                    schema = {
                        "type": "OBJECT",
                        "required": ["title", "genre"],
                        "properties": {"title": {"type": "STRING"}, "genre": {"type": "STRING"}},
                    }
                    prompt = "任务：补全《作品名与类型》。请只输出 JSON，其中包含 title 与 genre。"
                elif sec == "核心人设":
                    schema = {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "required": ["role", "name", "identity", "desire", "weakness", "growth"],
                            "properties": {
                                "role": {"type": "STRING"},
                                "name": {"type": "STRING"},
                                "identity": {"type": "STRING"},
                                "desire": {"type": "STRING"},
                                "weakness": {"type": "STRING"},
                                "growth": {"type": "STRING"},
                            },
                        },
                    }
                    prompt = "任务：补全《核心人设》。请只输出 JSON 数组，必须包含主角、对手、导师、盟友四类角色。"
                elif sec == "世界观与设定":
                    schema = {
                        "type": "OBJECT",
                        "required": ["era", "region", "power_structure", "resources", "rules", "scenes"],
                        "properties": {
                            "era": {"type": "STRING"},
                            "region": {"type": "STRING"},
                            "power_structure": {"type": "STRING"},
                            "resources": {"type": "STRING"},
                            "rules": {"type": "STRING"},
                            "scenes": {"type": "STRING"},
                        },
                    }
                    prompt = "任务：补全《世界观与设定》。请只输出 JSON，包含 era、region、power_structure、resources、rules、scenes。"
                elif sec == "爽点清单":
                    schema = {"type": "ARRAY", "items": {"type": "STRING"}}
                    prompt = "任务：补全《爽点清单》。请只输出 JSON 数组，不少于12条，每条一句。"
                elif sec == "三幕结构梗概":
                    schema = {
                        "type": "OBJECT",
                        "required": ["act1", "act2", "act3"],
                        "properties": {
                            "act1": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "act2": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "act3": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    }
                    prompt = "任务：补全《三幕结构梗概》。请只输出 JSON，包含 act1、act2、act3 三个数组，每幕不少于5项。"
                elif sec == "读者钩子与悬念设计":
                    schema = {
                        "type": "OBJECT",
                        "required": ["short_term", "mid_term", "long_term"],
                        "properties": {
                            "short_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "mid_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "long_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    }
                    prompt = "任务：补全《读者钩子与悬念设计》。请只输出 JSON，包含 short_term、mid_term、long_term 三个数组。"
                else:
                    schema = {
                        "type": "OBJECT",
                        "required": ["side_plots", "future_arcs"],
                        "properties": {
                            "side_plots": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "future_arcs": {"type": "ARRAY", "items": {"type": "STRING"}},
                        },
                    }
                    prompt = "任务：补全《可扩展支线与后续走向》。请只输出 JSON，包含 side_plots 与 future_arcs 两个数组。"

                data = self._generate_json_via_provider(provider, api_key, model_name, novel_type, theme, text, prompt, schema)
                if data is None:
                    continue
                formatted = self._format_from_data(sec, data)
                if formatted:
                    add_block = f"\n\n### 补全：{sec}\n{formatted}\n"
                    text += add_block
                    if self.logger:
                        self.logger.info(f"已补全模块: {sec}")

            existing = self._parse_chapters_from_outline_text(text)
            present = sorted([c for c in existing.keys() if 1 <= c <= desired])
            missing_nums = [n for n in range(1, desired + 1) if n not in existing]

            if missing_nums:
                self.root.after(0, self._append_text, f"[系统] 发现缺失章节：{len(missing_nums)} 章，开始补全...\n")
                if self.logger:
                    self.logger.info(f"缺失章节数: {len(missing_nums)}")

            ranges = []
            for n in missing_nums:
                if not ranges or n != ranges[-1][1] + 1:
                    ranges.append([n, n])
                else:
                    ranges[-1][1] = n

            schema_chaps = {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "required": ["chapter", "title", "summary"],
                    "properties": {
                        "chapter": {"type": "INTEGER"},
                        "title": {"type": "STRING"},
                        "summary": {"type": "STRING"},
                    },
                },
            }

            def try_fill_range(a: int, b: int) -> int:
                need_nums = [n for n in range(a, b + 1) if n not in existing]
                context_lines = []
                for k in range(a - 3, a):
                    if k in existing:
                        context_lines.append(f"第{k}章 {existing[k].get('title','')}：{existing[k].get('summary','')}")
                for k in range(b + 1, b + 4):
                    if k in existing:
                        context_lines.append(f"第{k}章 {existing[k].get('title','')}：{existing[k].get('summary','')}")
                neighbor_context = "\n".join(context_lines)

                prompt = (
                    f"任务：补全章节大纲，范围：第{a}章 - 第{b}章。\n"
                    f"要求：\n"
                    f"1. 只输出 JSON 数组，每个元素包含 chapter(整数)、title(章节标题)、summary(中文1-2句)。\n"
                    f"2. title 不要带“第X章”。\n"
                    f"3. 必须承接已有剧情，避免与上下文冲突。\n"
                    f"4. 每章都要有明确推进与冲突/转折。\n"
                )
                if need_nums:
                    prompt += f"5. 只补全这些缺失章号：{', '.join(str(x) for x in need_nums)}；不要输出其他章。\n"
                if neighbor_context:
                    prompt += f"\n【相邻章节参考】\n{neighbor_context}\n"

                if self.logger:
                    self.logger.info(f"开始补全章节范围 {a}-{b}")
                range_context = self._build_chapter_range_context(text, existing, a, b)
                data = self._generate_json_via_provider(provider, api_key, model_name, novel_type, theme, range_context, prompt, schema_chaps)
                items = self._ensure_list(data) if data is not None else []
                added = 0
                for it in items:
                    if isinstance(it, dict) and "chapter" in it:
                        try:
                            cn = int(it.get("chapter"))
                        except Exception:
                            continue
                        if need_nums and cn not in need_nums:
                            continue
                        if 1 <= cn <= desired and cn not in existing:
                            t = (it.get("title") or "").strip()
                            if not t:
                                t = "未命名"
                            existing[cn] = {
                                "chapter": cn,
                                "title": t,
                                "summary": (it.get("summary") or "").strip() or "无内容",
                            }
                            added += 1
                return added

            stack = []
            for r in ranges:
                stack.append((r[0], r[1]))

            while stack:
                a, b = stack.pop()
                need = [n for n in range(a, b + 1) if n not in existing]
                if not need:
                    continue
                size = len(need)
                if size > 15:
                    cur = a
                    while cur <= b:
                        ce = min(cur + 14, b)
                        stack.append((cur, ce))
                        cur = ce + 1
                    continue

                before = len(existing)
                added = try_fill_range(a, b)
                after = len(existing)
                if self.logger:
                    self.logger.info(f"补全章节范围 {a}-{b}，新增 {added}，当前总章节 {after}")

                still = [n for n in range(a, b + 1) if n not in existing]
                if still:
                    if b > a:
                        mid = (a + b) // 2
                        stack.append((a, mid))
                        stack.append((mid + 1, b))
                    else:
                        if self.logger:
                            self.logger.warning(f"单章补全失败: 第{a}章")

            final_missing = [n for n in range(1, desired + 1) if n not in existing]
            if final_missing:
                if self.logger:
                    self.logger.warning(f"模型补全仍缺失章节，启动兜底填充: {final_missing[:20]}{'...' if len(final_missing) > 20 else ''}")
                for n in final_missing:
                    title, summary = self._synthesize_missing_chapter(existing, n)
                    existing[n] = {"chapter": n, "title": title, "summary": summary}

            rebuilt_lines = []
            self.chapters_data = []
            self.all_chapter_summaries = []
            for n in range(1, desired + 1):
                item = existing.get(n)
                if not item:
                    continue
                t = (item.get("title") or "").strip()
                t = re.sub(r"^第\\s*\\d+\\s*章\\s*", "", t).strip()
                s = (item.get("summary") or "").strip()
                rebuilt_lines.append(f"第{n}章 {t}：{s}")
                self.chapters_data.append({"chapter": n, "title": t, "summary": s})
                self.all_chapter_summaries.append(f"第{n}章：{s[:50]}...")

            if rebuilt_lines:
                chapter_block = "\n".join(rebuilt_lines)
                matches = list(re.finditer(r"(第\\s*(\\d+)\\s*章\\s*(.*?))\\s*[:：\\n]\\s*([\\s\\S]*?)(?=(?:\\n\\s*第\\s*\\d+\\s*章)|$)", text))
                if matches:
                    start_idx = matches[0].start()
                    end_idx = matches[-1].end()
                    text = text[:start_idx].rstrip() + "\n" + chapter_block + "\n" + text[end_idx:].lstrip()
                else:
                    text += "\n\n### 章节大纲（补全版）\n" + chapter_block + "\n"

            self.full_outline_context = text
            self.root.after(0, lambda: self.output.delete("1.0", tk.END))
            self.root.after(0, lambda: self.output.insert(tk.END, text))

            wrote_back = False
            if self.last_outline_path and os.path.exists(self.last_outline_path):
                try:
                    with open(self.last_outline_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    wrote_back = True
                    if self.logger:
                        self.logger.info(f"已回写大纲文件: {self.last_outline_path}")
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"回写大纲文件失败: {e}")

            self.root.after(0, lambda: self.save_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.export_zip_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.polish_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.generate_novel_btn.config(state=tk.NORMAL))
            if wrote_back:
                self.root.after(0, messagebox.showinfo, "完成", f"检查与补全完成，已回写原文件：\n{self.last_outline_path}")
            else:
                self.root.after(0, messagebox.showinfo, "完成", "检查与补全完成（未找到可回写的原文件路径，可点击“保存到本地”覆盖保存）。")
            if self.logger:
                self.logger.info("检查与补全完成")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "补全失败", err_msg)
            if self.logger:
                self.logger.error(f"补全失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _append_text(self, text: str):
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def _new_generation_variation(self, novel_type: str, theme: str) -> str:
        nonce = uuid.uuid4().hex[:10]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        surnames = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
        given1 = ["志", "明", "宏", "建", "国", "峰", "涛", "强", "远", "杰", "成", "凯", "宇", "哲", "安", "卓", "衡", "航"]
        given2 = ["轩", "辰", "阳", "文", "武", "然", "之", "一", "宁", "川", "廷", "浩", "瑞", "诚", "策", "言", "清", "鸣"]
        cities = ["江州", "临川", "南陵", "北海", "清河", "东城", "西江", "云港"]
        depts = ["市公安局", "区纪委监委", "市政法委", "检察院", "组织部", "信访办", "国资委", "开发区管委会"]
        orgs = ["明远集团", "恒盛实业", "天启资本", "金桥建设", "宏达矿业", "瑞景置业", "东晟物流", "华腾担保"]
        clues = ["行车记录仪备份", "匿名U盘", "被改写的案卷页", "消失的通话清单", "水下拖捞照片", "旧账本", "审计底稿", "内部工作群截图"]
        openers = ["雨夜车祸", "匿名举报", "突发坠楼", "暗箱招标", "专案组成立", "调岗下放", "突袭抓捕", "巡察进驻"]

        def pick_name():
            return secrets.choice(surnames) + secrets.choice(given1) + secrets.choice(given2)

        protagonist = pick_name()
        rival = pick_name()
        mentor = pick_name()
        ally = pick_name()

        city = secrets.choice(cities)
        dept = secrets.choice(depts)
        org = secrets.choice(orgs)
        clue = secrets.choice(clues)
        opener = secrets.choice(openers)

        return (
            "【本次随机变体（用于避免人物/情节雷同）】\n"
            f"变体ID：{nonce}\n"
            f"生成时间：{ts}\n"
            "人物命名（必须使用，且四人姓名互不重复）：\n"
            f"- 主角：{protagonist}\n"
            f"- 对手：{rival}\n"
            f"- 导师：{mentor}\n"
            f"- 盟友：{ally}\n"
            "地点与势力（优先采用，可按类型微调但不得照搬上一次）：\n"
            f"- 城市：{city}\n"
            f"- 部门：{dept}\n"
            f"- 反派势力：{org}\n"
            f"- 开局触发：{opener}\n"
            f"- 关键线索：{clue}\n"
            "硬性要求：本次输出不得沿用上一次的人名、组织名、开局事件表述；必须生成新的冲突走向与线索链。\n"
        )

    def _optimize_prompt(self, client, models, novel_type, theme, config) -> str:
        prompt = (
            "你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n"
            f"小说类型：{novel_type}\n"
            f"核心主题：{theme}\n\n"
            "要求：\n"
            "1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n"
            "2. 细化对人设、世界观、冲突节奏的具体要求。\n"
            "3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n"
            "4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n"
            "5. 【重点】针对长篇结构，请设计“螺旋式上升”的剧情结构，避免重复套路。明确要求随着章节推进，冲突的规模（个人->势力->体系）、性质（生存->利益->信仰）和爽点类型必须不断演变升级，防止读者审美疲劳。\n"
            "6. 章节标题生成时，请只输出标题文字，不要包含“第X章”字样。\n"
            "7. 【章节强制格式】每一章的 summary 必须严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”，其余不得留空）。\n"
            "8. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。"
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        optimized = self._generate_with_fallback(client, models, contents, config)
        return optimized.strip() if optimized else build_system_instruction()

    def _run_regenerate_outline(self, provider, api_key, model_name, novel_type, theme, chapters, volumes, base_outline: str, feedback: str):
        try:
            self._wait_if_paused()
            if self._cancel_event.is_set():
                self.root.after(0, self._append_text, "\n\n[系统] 已停止重生成。\n")
                return

            self.generation_variation = ""
            self._setup_logger(novel_type, theme, chapters)
            self.start_time = time.time()

            constraints_text = build_constraints(novel_type, theme, self.channel_var.get())
            self.last_constraints_text = constraints_text

            optimized_instruction = (self.last_optimized_instruction or "").strip() or build_system_instruction()
            if not (self.last_optimized_instruction or "").strip():
                if provider in ("Doubao", "Claude"):
                    system_prompt = build_system_instruction() + "\n" + constraints_text
                    optimize_prompt = (
                        "你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n"
                        f"小说类型：{novel_type}\n"
                        f"核心主题：{theme}\n\n"
                        "要求：\n"
                        "1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n"
                        "2. 细化对人设、世界观、冲突节奏的具体要求。\n"
                        "3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n"
                        "4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n"
                        "5. 针对长篇结构，设计“螺旋式上升”的剧情结构，避免重复。\n"
                        "6. 章节标题生成时，请只输出标题文字，不要包含“第X章”字样。\n"
                        "7. 【章节强制格式】每一章的 summary 必须严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”，其余不得留空）。\n"
                        "8. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。"
                    )
                    oi = ""
                    if provider == "Claude":
                        oi = self._call_claude(api_key, model_name, system_prompt, optimize_prompt, temperature=0.7, max_tokens=2048)
                    else:
                        base_url = self._load_doubao_base_url() if provider == "Doubao" else ""
                        oi = self._call_compat_chat(api_key, model_name, system_prompt, optimize_prompt, temperature=0.7, base_url=base_url)
                    if oi and isinstance(oi, str):
                        optimized_instruction = oi.strip()
                else:
                    client = genai.Client(api_key=api_key)
                    models = [DEFAULT_GEMINI_MODEL]
                    if model_name and model_name != DEFAULT_GEMINI_MODEL:
                        models.append(model_name)
                    if "gemini-2.5-pro" not in models:
                        models.append("gemini-2.5-pro")
                    if "gemini-2.0-flash" not in models:
                        models.append("gemini-2.0-flash")
                    config = types.GenerateContentConfig(
                        system_instruction=[
                            types.Part.from_text(text=build_system_instruction()),
                            types.Part.from_text(text=constraints_text),
                        ],
                        temperature=0.7,
                        max_output_tokens=4000,
                        top_p=0.95,
                    )
                    optimized_instruction = self._optimize_prompt(client, models, novel_type, theme, config)
                self.last_optimized_instruction = (optimized_instruction or "").strip()

            base_outline_text = (base_outline or "").strip()
            if len(base_outline_text) > 60000:
                base_outline_text = base_outline_text[-60000:]

            user_prompt = (
                "任务：根据【修改意见】，在尽量保留原有设定与人物命名的前提下，重写并输出一份完整大纲。\n"
                "强制要求：\n"
                "1. 必须输出完整大纲，不要输出解释性文字。\n"
                "2. 必须保留并对齐现有大纲的模块顺序与层级（如“作品名与类型/核心人设/世界观与设定/爽点清单/三幕结构梗概/章节大纲/读者钩子与悬念设计/可扩展支线与后续走向”等）。\n"
                f"3. 章节数必须严格为 {chapters} 章；每章必须使用章节块格式：\n"
                "   ### 第N章：标题\n"
                "   **内容**：...\n"
                "   **【悬疑点】**：...\n"
                "   **【爽点】**：...（开局悲剧铺垫允许“暂无”）\n"
                "4. 标题不要额外包含“第N章”字样（章节块前缀已经包含）。\n"
                "5. 必须承接原大纲的逻辑链条；除非修改意见要求，否则不要重置为全新故事。\n"
                "\n【当前大纲】\n"
                f"{base_outline_text}\n"
                "\n【修改意见】\n"
                f"{feedback.strip()}\n"
            )

            if self.logger:
                self.logger.info("=== 修改意见重生成 ===")
                self.logger.info(f"provider={provider} model={model_name}")
                self.logger.info(f"chapters={chapters} volumes={volumes}")
                self.logger.info(f"feedback:\n{feedback}")

            self.root.after(
                0,
                self._append_text,
                "\n\n### 专业提示词（本次用于重生成大纲）\n"
                + optimized_instruction.strip()
                + "\n\n",
            )
            self.root.after(0, self._append_text, "\n\n### 修改意见\n" + feedback.strip() + "\n\n")

            text_out = ""
            if provider in ("Doubao", "Claude"):
                system_prompt = optimized_instruction.strip() + "\n" + constraints_text
                if provider == "Claude":
                    text_out = self._call_claude(api_key, model_name, system_prompt, user_prompt, temperature=0.6, max_tokens=8192)
                else:
                    base_url = self._load_doubao_base_url() if provider == "Doubao" else ""
                    text_out = self._call_compat_chat(api_key, model_name, system_prompt, user_prompt, temperature=0.6, base_url=base_url)
            else:
                client = genai.Client(api_key=api_key)
                models = [DEFAULT_GEMINI_MODEL]
                if model_name and model_name != DEFAULT_GEMINI_MODEL:
                    models.append(model_name)
                if "gemini-2.5-pro" not in models:
                    models.append("gemini-2.5-pro")
                if "gemini-2.0-flash" not in models:
                    models.append("gemini-2.0-flash")
                config = types.GenerateContentConfig(
                    system_instruction=[
                        types.Part.from_text(text=optimized_instruction.strip()),
                        types.Part.from_text(text=constraints_text),
                    ],
                    temperature=0.7,
                    max_output_tokens=8000,
                    top_p=0.95,
                )
                contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]
                text_out = self._generate_with_fallback(client, models, contents, config)

            text_out = self._sanitize_text(text_out or "")
            self._wait_if_paused()
            if self._cancel_event.is_set():
                self.root.after(0, self._append_text, "\n\n[系统] 已停止重生成。\n")
                return

            if not text_out.strip():
                self.root.after(0, messagebox.showwarning, "重生成失败", "模型返回了空内容")
                return

            self.root.after(0, lambda: self.output.delete("1.0", tk.END))
            self.root.after(0, self._append_text, text_out.strip() + "\n")

            accumulated = text_out.strip()
            accumulated = self._post_fill_missing_after_generation(
                provider, api_key, model_name, novel_type, theme, chapters, volumes, accumulated
            )

            self.full_outline_context = accumulated.strip()
            self.root.after(0, lambda: self.output.delete("1.0", tk.END))
            self.root.after(0, self._append_text, self.full_outline_context + "\n")

            self.root.after(0, messagebox.showinfo, "完成", "大纲修改完成")
            if self.logger:
                self.logger.info("修改意见重生成完成")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "重生成失败", err_msg)
            if self.logger:
                self.logger.error(f"重生成失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _run_generation(self, provider, api_key, model_name, novel_type, theme, chapters, volumes):
        # Gemini Logic
        try:
            self.generation_variation = self._new_generation_variation(novel_type, theme)
            self._setup_logger(novel_type, theme, chapters)
            self.start_time = time.time()
            client = genai.Client(api_key=api_key)
            tools = []
            constraints_text = build_constraints(novel_type, theme, self.channel_var.get()) + "\n" + (self.generation_variation or "")
            config = types.GenerateContentConfig(
                system_instruction=[
                    types.Part.from_text(text=build_system_instruction()),
                    types.Part.from_text(text=constraints_text),
                ],
                tools=tools,
                temperature=0.7,
                max_output_tokens=4000,
                top_p=0.95,
            )
            
            models = [DEFAULT_GEMINI_MODEL]
            if model_name and model_name != DEFAULT_GEMINI_MODEL:
                models.append(model_name)
            if "gemini-2.5-pro" not in models:
                models.append("gemini-2.5-pro")
            if "gemini-2.0-flash" not in models:
                models.append("gemini-2.0-flash")
            
            # --- 第一步：生成优化后的提示词 ---
            self.root.after(0, self._append_text, "正在根据类型与主题，智能优化大纲生成指令...\n")
            if self.logger:
                self.logger.info("开始生成优化提示词")
            
            optimized_instruction = self._optimize_prompt(client, models, novel_type, theme, config)
            self.last_optimized_instruction = (optimized_instruction or "").strip()
            self.last_constraints_text = (constraints_text or "").strip()
            
            if self.logger:
                self.logger.info(f"优化后的提示词:\n{optimized_instruction}")

            self.root.after(
                0,
                self._append_text,
                "\n\n### 专业提示词（本次用于生成大纲）\n"
                + optimized_instruction.strip()
                + "\n\n"
                + (self.generation_variation or ""),
            )
            
            self.root.after(0, self._append_text, "指令优化完成，开始生成正文...\n")
            
            # 使用优化后的指令更新配置
            config = types.GenerateContentConfig(
                system_instruction=[
                    types.Part.from_text(text=optimized_instruction),
                    types.Part.from_text(text=constraints_text),
                ],
                tools=tools,
                temperature=0.7,
                max_output_tokens=4000,
                top_p=0.95,
            )
            sections = self._build_sections(novel_type, theme, chapters, volumes, provider=provider)
            self.total_sections = len(sections)
            self.completed_sections = 0
            self.root.after(0, self._update_progress)
            
            accumulated = ""
            for i, sec in enumerate(sections, start=1):
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成。\n")
                    break
                sec_title = sec[0]
                sec_prompt = sec[1]
                sec_schema = sec[2] if len(sec) > 2 else None
                
                self.root.after(0, self._append_text, f"\n\n### {i}. {sec_title}\n")
                if self.logger:
                    self.logger.info(f"开始生成: {sec_title}")
                
                # 动态构建 prompt parts
                prompt_parts = [types.Part.from_text(text=sec_prompt)]
                
                # 核心逻辑：将已生成的所有大纲内容作为上下文注入到 prompt 中
                # 这确保了大纲的前后逻辑一致性（如人物关系、设定细节等）
                if accumulated:
                    # 限制上下文长度，防止超出模型窗口（Gemini-Pro 上下文很长，这里相对安全，但仍做适当截断以防万一）
                    # 保留最近的 20000 字符通常足够覆盖大纲的关键信息
                    context_text = accumulated[-25000:] 
                    context_injection = (
                        f"\n\n【当前已生成的大纲内容（上下文参考）】\n"
                        f"{context_text}\n"
                        f"----------------\n"
                        f"重要指令：请基于以上已生成的内容继续创作，确保《{sec_title}》部分与前文的人物设定、世界观规则及剧情走向保持高度一致，严禁出现逻辑冲突。\n"
                    )
                    prompt_parts.insert(0, types.Part.from_text(text=context_injection)) # 将上下文放在 prompt 最前面

                # 如果是章节大纲（非第一批），额外注入剧情梗概作为更聚焦的上下文
                if sec_title.startswith("章节大纲") and self.all_chapter_summaries:
                    # 获取最近的剧情回顾
                    context_summary = "\n".join(self.all_chapter_summaries)[-5000:]
                    context_injection_summary = (
                        f"\n\n【前序剧情梗概速览】\n"
                        f"{context_summary}\n"
                        f"----------------\n"
                        f"重要指令：请承接上述剧情发展，确保新生成的章节（{sec_title}）与前文逻辑连贯，且必须引入新的冲突或转折，严禁简单重复之前的事件模式。\n"
                    )
                    prompt_parts.append(types.Part.from_text(text=context_injection_summary))

                contents = [
                    types.Content(
                        role="user",
                        parts=prompt_parts,
                    )
                ]
                
                config_local = config
                if sec_schema:
                    # 针对 JSON 结构化输出的配置
                    config_local = types.GenerateContentConfig(
                        system_instruction=config.system_instruction,
                        tools=config.tools,
                        temperature=0.5, # 结构化输出建议降低温度
                        max_output_tokens=config.max_output_tokens,
                        top_p=config.top_p,
                        response_mime_type="application/json",
                        response_schema=sec_schema,
                    )
                
                text_out = self._generate_with_fallback(client, models, contents, config_local)
                
                if sec_schema:
                    # 尝试解析 JSON
                    json_data = self._parse_json(text_out)
                    
                    if not json_data:
                        if self.logger:
                            self.logger.warning("JSON 解析失败，尝试纠正为有效 JSON")
                        fixed_json_text = self._correct_section_json(client, models, sec_title, text_out, sec_prompt, config_local, sec_schema)
                        json_data = self._parse_json(fixed_json_text)

                    if sec_title.startswith("章节大纲") and not json_data:
                        rng = self._parse_chapter_range_from_title(sec_title)
                        if rng:
                            a, b = rng
                            if self.logger:
                                self.logger.warning(f"章节范围 {a}-{b} 结构化失败，重新请求补全")
                            regen_prompt = (
                                f"任务：生成章节大纲，范围：第{a}章-第{b}章。\n"
                                f"要求：\n"
                                f"1. 只输出 JSON 数组，每项包含 chapter(整数)、title(章节标题)、summary(中文2-3句)。\n"
                                f"2. title 不要带“第X章”。\n"
                                f"3. summary 必须严格使用如下格式（爽点允许为“暂无”，其余不得留空）：**内容**：... **【悬疑点】**：... **【爽点】**：...\n"
                                f"4. 必须承接上下文，避免逻辑冲突。\n"
                            )
                            ctx_existing = self._parse_chapters_from_outline_text(accumulated)
                            range_context = self._build_chapter_range_context(accumulated, ctx_existing, a, b)
                            regen_data = self._generate_json_via_provider(provider, api_key, DEFAULT_GEMINI_MODEL, novel_type, theme, range_context, regen_prompt, sec_schema)
                            json_data = regen_data
                            if not json_data:
                                by_ch = dict(ctx_existing) if isinstance(ctx_existing, dict) else {}
                                for n in range(a, b + 1):
                                    if n not in by_ch:
                                        t, s = self._synthesize_missing_chapter(by_ch, n)
                                        by_ch[n] = {"chapter": n, "title": t, "summary": s}
                                json_data = [by_ch[k] for k in sorted(by_ch.keys()) if a <= k <= b]
                    
                    if sec_title.startswith("章节大纲") and json_data:
                        rng = self._parse_chapter_range_from_title(sec_title)
                        if rng:
                            a, b = rng
                            missing_chaps = self._missing_chapters_in_items(json_data, a, b)
                            attempt = 0
                            while missing_chaps and attempt < 4:
                                attempt += 1
                                miss_str = ", ".join(str(x) for x in missing_chaps[:20])
                                fill_prompt = (
                                    f"任务：补全章节大纲缺失部分。\n"
                                    f"范围：第{a}章-第{b}章。\n"
                                    f"只补全这些缺失章号：{miss_str}。\n"
                                    f"要求：只输出 JSON 数组；每项包含 chapter(整数)、title、summary；summary 必须包含：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”）\n"
                                )
                                context_text = accumulated[-25000:] if accumulated else ""
                                ctx = (context_text + "\n" + "\n".join(self.all_chapter_summaries[-80:])).strip()
                                fill_data = self._generate_json_via_provider(provider, api_key, DEFAULT_GEMINI_MODEL, novel_type, theme, ctx, fill_prompt, sec_schema)
                                fill_items = self._ensure_list(fill_data) if fill_data is not None else []
                                base_items = self._ensure_list(json_data)
                                by_ch = {}
                                for it in base_items + fill_items:
                                    if isinstance(it, dict) and "chapter" in it:
                                        try:
                                            cn = int(it.get("chapter"))
                                        except Exception:
                                            continue
                                        if a <= cn <= b:
                                            by_ch[cn] = {
                                                "chapter": cn,
                                                "title": (it.get("title") or "").strip() or "未命名",
                                                "summary": (it.get("summary") or "").strip() or "无内容",
                                            }
                                json_data = [by_ch[k] for k in sorted(by_ch.keys())]
                                missing_chaps = self._missing_chapters_in_items(json_data, a, b)
                            if missing_chaps:
                                by_ch = {int(it.get("chapter")): it for it in self._ensure_list(json_data) if isinstance(it, dict) and "chapter" in it}
                                for n in missing_chaps:
                                    t, s = self._synthesize_missing_chapter(by_ch, n)
                                    by_ch[n] = {"chapter": n, "title": t, "summary": s}
                                json_data = [by_ch[k] for k in sorted(by_ch.keys())]

                    # 格式化并收集数据
                    formatted = ""
                    if json_data:
                        formatted = self._format_from_data(sec_title, json_data)
                        # 收集章节数据用于后续导出
                        if sec_title.startswith("章节大纲"):
                            items = self._ensure_list(json_data)
                            self.chapters_data.extend(items)

                    text_out_final = formatted or self._sanitize_text(text_out or "")
                    if not text_out_final and json_data:
                        try:
                            text_out_final = json.dumps(json_data, ensure_ascii=False, indent=2)
                        except Exception:
                            text_out_final = str(json_data)
                    
                    # 收集章节梗概用于上下文
                    if sec_title.startswith("章节大纲") and json_data:
                        items = self._ensure_list(json_data)
                        for item in items:
                            if isinstance(item, dict):
                                s = item.get("summary", "")
                                if s:
                                    self.all_chapter_summaries.append(f"第{item.get('chapter')}章：{s}")

                else:
                    # 非 JSON 模式（本例中全为 JSON，保留此逻辑以备扩展）
                    if text_out and (self._violates_genre(novel_type, text_out) or self._contains_meta(text_out) or self._is_empty_section(sec_title, text_out)):
                        if self.logger:
                            self.logger.warning("检测到偏离或空输出，尝试纠正")
                        fix = self._correct_section(client, models, sec_title, text_out, novel_type, theme, config)
                        if fix:
                            text_out = fix
                    text_out_final = self._sanitize_text(text_out or "")

                if text_out_final:
                    self.root.after(0, self._append_text, text_out_final)
                    accumulated += "\n\n### " + str(i) + ". " + sec_title + "\n" + text_out_final
                    self.completed_sections += 1
                    self.root.after(0, self._update_progress)
                    self.root.after(0, self._update_eta, 0)
                    if self.logger:
                        self.logger.info(f"完成: {sec_title}")
            
            if not self._cancel_event.is_set():
                accumulated = self._post_fill_missing_after_generation(
                    provider,
                    api_key,
                    model_name,
                    novel_type,
                    theme,
                    chapters,
                    volumes,
                    accumulated,
                )
                self.root.after(0, self._auto_save, novel_type, theme)
                if self.logger:
                    self.logger.info("全部生成完成")
                
        except Exception as e:
            err_msg = str(e)
            print(err_msg) # 控制台打印
            self.root.after(0, messagebox.showerror, "生成失败", err_msg)
            if self.logger:
                self.logger.error(f"生成失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _slug(self, text: str) -> str:
        s = (text or "").strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[\\/:*?\"<>|]+", "_", s)
        s = s.strip(" .\t\r\n")
        if not s:
            s = "未命名"
        upper = s.upper()
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }
        if upper in reserved:
            s = f"_{s}"
        return s[:120]

    def _extract_outline_title(self, content: str) -> str:
        if not content:
            return ""
        lines = (content or "").splitlines()
        label_re = re.compile(r"^\s*(?:\d+\s*[\)\.、]\s*)?(?:作品名|书名|小说名|作品名称)\s*[:：]?\s*(.*)\s*$", re.IGNORECASE)
        for idx, line in enumerate(lines[:200]):
            m = label_re.match(line)
            if not m:
                continue
            tail = (m.group(1) or "").strip()
            if not tail:
                for j in range(idx + 1, min(idx + 8, len(lines))):
                    if lines[j].strip():
                        tail = lines[j].strip()
                        break
            if tail:
                tail = tail.strip()
                tail = re.sub(r"^[《“\"'‘]+", "", tail)
                tail = re.sub(r"[》”\"'’]+$", "", tail)
                tail = tail.strip()
                if tail:
                    return tail

        m2 = re.search(r"《([^》\n]{1,80})》", content)
        if m2:
            t = (m2.group(1) or "").strip()
            if t:
                return t

        m3 = re.search(r'(?i)"title"\s*:\s*"([^"\n]{1,120})"', content)
        if m3:
            t = (m3.group(1) or "").strip()
            if t:
                return t
        return ""

    def _parse_retry_delay(self, msg: str) -> int:
        m = re.search(r"retryDelay['\"]?:\s*'?([0-9]+)s", msg)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        m2 = re.search(r"Please retry in ([0-9]+(?:\.[0-9]+)?)", msg)
        if m2:
            try:
                return int(float(m2.group(1)))
            except Exception:
                pass
        return 30

    def _is_rate_limit(self, msg: str) -> bool:
        s = msg.lower()
        return ("resource_exhausted" in s) or ("code: 429" in s) or ("quota" in s)

    def _is_free_tier_block(self, msg: str) -> bool:
        s = msg.lower()
        return ("generate_content_free_tier" in s or "free tier" in s or "free_tier" in s) and ("limit: 0" in s or "limit 0" in s)

    def _gemini_generate_with_timeout(self, client, model: str, contents, config, timeout_secs: int = 180):
        q = queue.Queue(maxsize=1)

        def worker():
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                q.put(("ok", resp))
            except Exception as e:
                q.put(("err", e))

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        try:
            kind, payload = q.get(timeout=max(1, int(timeout_secs)))
        except queue.Empty:
            raise TimeoutError(f"Gemini request timeout after {timeout_secs}s")
        if kind == "err":
            raise payload
        return payload

    def _extract_gemini_text(self, resp) -> str:
        if resp is None:
            return ""
        text = getattr(resp, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        parts = getattr(resp, "parts", None)
        if parts:
            try:
                joined = "".join([p.text for p in parts if hasattr(p, "text") and p.text])
                if joined.strip():
                    return joined
            except Exception:
                pass
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
                except Exception:
                    continue
        return ""

    def _generate_with_fallback(self, client, models, contents, config, max_request_retries=2, max_empty_retries=8) -> str:
        total_empty_retries = 0
        for idx, m in enumerate(models):
            if self._cancel_event.is_set():
                return ""
            request_retries = 0
            consecutive_empty = 0
            if idx > 0:
                self.root.after(0, self._append_text, f"\n[系统] 切换模型：{m}\n")
                if self.logger:
                    self.logger.info(f"切换模型: {m}")
            
            while True:
                if self._cancel_event.is_set():
                    return ""
                try:
                    resp = self._gemini_generate_with_timeout(client, model=m, contents=contents, config=config, timeout_secs=180)
                    text = self._extract_gemini_text(resp)
                    
                    if not text:
                        raise ValueError("Empty response received")
                    
                    return text or ""
                    
                except Exception as e:
                    msg = str(e)
                    
                    # 处理免费层配额耗尽
                    if self._is_free_tier_block(msg):
                        if self.logger:
                            self.logger.warning(f"免费层限制，跳过模型 {m}")
                        break

                    if "Empty response received" in msg:
                        total_empty_retries += 1
                        consecutive_empty += 1
                        if self.logger:
                            self.logger.warning(f"空响应: {msg}。正在重试 ({total_empty_retries}/{max_empty_retries}) | 模型 {m}")
                        if total_empty_retries >= max_empty_retries:
                            if self.logger:
                                self.logger.error(f"空响应达到上限，放弃本次请求 | 模型 {m}")
                            return ""
                        if consecutive_empty >= 2 and idx < (len(models) - 1):
                            if self.logger:
                                self.logger.warning(f"空响应连续出现，提前切换到下一个模型 | 当前模型 {m}")
                            break
                        wait_time = min(20, 2 * (2 ** min(consecutive_empty - 1, 4)))
                        self.root.after(0, self._append_text, f"\n[系统] 模型返回空内容，{wait_time}s后重试...\n")
                        time.sleep(wait_time)
                        continue
                    else:
                        consecutive_empty = 0
                    
                    # 处理速率限制 (429)
                    if self._is_rate_limit(msg) and request_retries < self.max_retries:
                        delay = self._parse_retry_delay(msg)
                        self.root.after(0, self._append_text, f"\n[系统] 达到配额限制，{delay}s后重试...\n")
                        self.root.after(0, self._update_eta, delay)
                        if self.logger:
                            self.logger.warning(f"限流，等待 {delay}s 后重试，模型 {m}")
                        time.sleep(delay)
                        request_retries += 1
                        continue
                        
                    # 处理其他网络错误或未知错误（增加通用重试）
                    if request_retries < max_request_retries:
                        wait_time = min(30, 4 * (2 ** request_retries))
                        self.root.after(0, self._append_text, f"\n[系统] 请求遇到问题（{msg[:50]}...），{wait_time}s后重试...\n")
                        if self.logger:
                            self.logger.warning(f"请求异常: {msg}。正在重试 ({request_retries + 1}/{max_request_retries})")
                        time.sleep(wait_time)
                        request_retries += 1
                        continue
                    else:
                        if self.logger:
                            self.logger.error(f"模型 {m} 调用最终失败: {msg}")
                        break
        return ""

    def _build_sections(self, novel_type: str, theme: str, chapters: int, volumes: int, provider: str = ""):
        base = f"类型：{novel_type}\n主题/设定：{theme}\n严格遵循类型与主题，不得偏离或引入不相关元素。"
        variation = (getattr(self, "generation_variation", "") or "").strip()
        if variation:
            base = base + "\n" + variation
        volumes = max(1, min(int(volumes or 1), int(chapters or 1)))
        
        sec1_schema = {
            "type": "OBJECT",
            "required": ["title", "genre"],
            "properties": {
                "title": {"type": "STRING"},
                "genre": {"type": "STRING"},
            },
        }
        sec2_schema = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["role", "name", "identity", "desire", "weakness", "growth"],
                "properties": {
                    "role": {"type": "STRING"},
                    "name": {"type": "STRING"},
                    "identity": {"type": "STRING"},
                    "desire": {"type": "STRING"},
                    "weakness": {"type": "STRING"},
                    "growth": {"type": "STRING"},
                },
            },
        }
        sec3_schema = {
            "type": "OBJECT",
            "required": ["era", "region", "power_structure", "resources", "rules", "scenes"],
            "properties": {
                "era": {"type": "STRING"},
                "region": {"type": "STRING"},
                "power_structure": {"type": "STRING"},
                "resources": {"type": "STRING"},
                "rules": {"type": "STRING"},
                "scenes": {"type": "STRING"},
            },
        }
        sec4_schema = {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        }
        sec5_schema = {
            "type": "OBJECT",
            "required": ["act1", "act2", "act3"],
            "properties": {
                "act1": {"type": "ARRAY", "items": {"type": "STRING"}},
                "act2": {"type": "ARRAY", "items": {"type": "STRING"}},
                "act3": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        }
        sec6_schema = {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["name", "identity", "personality", "desire", "secret", "weakness", "growth", "relation_to_protagonist"],
                "properties": {
                    "name": {"type": "STRING"},
                    "identity": {"type": "STRING"},
                    "personality": {"type": "STRING"},
                    "desire": {"type": "STRING"},
                    "secret": {"type": "STRING"},
                    "weakness": {"type": "STRING"},
                    "growth": {"type": "STRING"},
                    "relation_to_protagonist": {"type": "STRING"},
                },
            },
        }
        
        # --- 核心修改：分卷生成逻辑 ---
        chapter_sections = []
        
        # 计算每卷的章节范围
        avg_chapters = chapters // volumes
        remainder = chapters % volumes
        
        current_start = 1
        
        # 定义阶段性指导原则（根据整体进度）
        def get_stage_instruction(ratio):
            if ratio < 0.2:
                return "【阶段：开局与铺垫】重点：抛出核心悬念，建立主角动机，确立初期反派。节奏要快，切入点要小。"
            elif ratio < 0.4:
                return "【阶段：发展与扩张】重点：地图/势力范围扩大，主角遭遇第一次重大挫折或强敌，爽点在于“以弱胜强”或“智谋破局”。避免单纯的打脸重复。"
            elif ratio < 0.6:
                return "【阶段：转折与危机】重点：剧情出现重大反转，原有套路失效，主角陷入绝境。引入新的力量体系或更高层面的博弈。"
            elif ratio < 0.8:
                return "【阶段：高潮前奏】重点：线索收束，多方势力混战，主角完成关键蜕变（实力或心境）。"
            else:
                return "【阶段：终局与收束】重点：最终对决，揭开所有伏笔，完成主题升华。确保结局震撼且逻辑自洽。"

        for v_idx in range(1, volumes + 1):
            # 计算当前卷的章节数（处理余数）
            count = avg_chapters + (1 if v_idx <= remainder else 0)
            if count <= 0: continue
            
            v_start = current_start
            v_end = current_start + count - 1
            current_start += count
            
            # 1. 生成分卷规划 (Volume Blueprint)
            vol_title_key = f"第{v_idx}卷：分卷规划 ({v_start}-{v_end}章)"
            vol_ratio = (v_start + v_end) / 2 / chapters
            vol_stage = get_stage_instruction(vol_ratio)
            
            vol_prompt = (
                f"{base}\n"
                f"正在规划：第{v_idx}卷（共{volumes}卷），章节范围：{v_start}-{v_end}章。\n"
                f"{vol_stage}\n"
                f"任务：请为本卷设计详细的剧情蓝图。\n"
                f"要求：\n"
                f"1. 卷名：极具吸引力，概括本卷核心。\n"
                f"2. 核心冲突：本卷要解决的主要矛盾是什么？\n"
                f"3. 关键事件：列出3-5个推动剧情的大事件。\n"
                f"4. 伏笔与悬念：本卷埋下的重要伏笔，以及留给下一卷的钩子。\n"
                f"请只输出 JSON，包含 volume_title, core_conflict, key_events(数组), hooks。"
            )
            
            vol_schema = {
                "type": "OBJECT",
                "required": ["volume_title", "core_conflict", "key_events", "hooks"],
                "properties": {
                    "volume_title": {"type": "STRING"},
                    "core_conflict": {"type": "STRING"},
                    "key_events": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "hooks": {"type": "STRING"},
                },
            }
            chapter_sections.append((vol_title_key, vol_prompt, vol_schema))
            
            # 2. 生成分卷内的章节细纲 (Chapter Outlines)
            # 如果一卷章节太多（>15），再进行切分，否则一次性生成
            # Gemini 2.0 Flash/Pro 上下文很长，一次生成 20-30 章问题不大，但为了稳定，还是限制在 15 章左右一组
            
            c_ptr = v_start
            batch_size = 8 if provider == "Doubao" else 15
            
            while c_ptr <= v_end:
                batch_end = min(c_ptr + batch_size - 1, v_end)
                
                chap_title_key = f"章节大纲 第{c_ptr}-{batch_end}章 (属于第{v_idx}卷)"
                
                chap_prompt = (
                    f"{base}\n"
                    f"当前任务：生成第{v_idx}卷的章节细纲，范围：第{c_ptr}章 - 第{batch_end}章。\n"
                    f"请严格基于刚刚生成的【第{v_idx}卷规划】（见上下文）进行创作。\n"
                    f"要求：\n"
                    f"1. 请只输出 JSON 数组，每个元素包含 chapter(整数)、title(章节标题) 与 summary。\n"
                    f"2. 章节标题不要带“第X章”。\n"
                    f"3. 确保剧情紧凑，紧扣本卷核心冲突。\n"
                    f"4. summary 必须严格使用如下格式（纯文本，不要 JSON 之外的包裹）：\n"
                    f"   **内容**：中文2-4句，写清本章发生什么。\n"
                    f"   **【悬疑点】**：一句。\n"
                    f"   **【爽点】**：一句（允许为“暂无”，用于开局悲剧铺垫）。\n"
                )
                
                chap_schema = {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "required": ["chapter", "title", "summary"],
                        "properties": {
                            "chapter": {"type": "INTEGER"},
                            "title": {"type": "STRING"},
                            "summary": {"type": "STRING"},
                        },
                    },
                }
                
                chapter_sections.append((chap_title_key, chap_prompt, chap_schema))
                c_ptr = batch_end + 1

        sec8_schema = {
            "type": "OBJECT",
            "required": ["short_term", "mid_term", "long_term"],
            "properties": {
                "short_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                "mid_term": {"type": "ARRAY", "items": {"type": "STRING"}},
                "long_term": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        }
        sec9_schema = {
            "type": "OBJECT",
            "required": ["side_plots", "future_arcs"],
            "properties": {
                "side_plots": {"type": "ARRAY", "items": {"type": "STRING"}},
                "future_arcs": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
        }

        sec1 = ("作品名与类型", base + "\n请只输出 JSON，其中 title 与 genre 两项。", sec1_schema)
        sec2 = ("核心人设", base + "\n请只输出 JSON 数组，含主角、对手、导师、盟友四类角色的人设。", sec2_schema)
        sec3 = ("世界观与设定", base + "\n请只输出 JSON，包含 era、region、power_structure、resources、rules、scenes。", sec3_schema)
        sec4 = ("爽点清单", base + "\n请只输出 JSON 数组，列出不少于12条爽点，每条一句。", sec4_schema)
        sec5 = ("三幕结构梗概", base + "\n请只输出 JSON，包含 act1、act2、act3 三个数组，每幕不少于5项。", sec5_schema)
        # sec6 已移除，原“主要角色档案”
        sec8 = ("读者钩子与悬念设计", base + "\n请只输出 JSON，包含 short_term、mid_term、long_term 三个数组。", sec8_schema)
        sec9 = ("可扩展支线与后续走向", base + "\n请只输出 JSON，包含 side_plots 与 future_arcs 两个数组。", sec9_schema)
        
        return [sec1, sec2, sec3, sec4, sec5] + chapter_sections + [sec8, sec9]

    def _build_sections_text(self, novel_type: str, theme: str, chapters: int, volumes: int, provider: str = ""):
        base = f"类型：{novel_type}\n主题/设定：{theme}\n严格遵循类型与主题，不得偏离或引入不相关元素。"
        variation = (getattr(self, "generation_variation", "") or "").strip()
        if variation:
            base = base + "\n" + variation
        volumes = max(1, min(int(volumes or 1), int(chapters or 1)))

        sec1 = (
            "作品名与类型",
            base
            + "\n请输出纯文本，格式严格如下（不要 JSON）。两行都必须有内容，不得留空：\n作品名：...\n类型：...\n",
        )
        sec2 = (
            "核心人设",
            base
            + "\n请输出纯文本（不要 JSON），必须包含主角、对手、导师、盟友四类角色。每个字段都必须填写，不得留空。每个角色使用如下标签并分段：\n角色：...\n姓名：...\n身份：...\n欲望：...\n弱点：...\n成长线：...\n",
        )
        sec3 = (
            "世界观与设定",
            base
            + "\n请输出纯文本（不要 JSON），每个字段都必须填写，不得留空。使用如下标签：\n时代：...\n地域：...\n权力结构：...\n关键资源：...\n规则与禁忌：...\n典型场景：...\n",
        )
        sec4 = (
            "爽点清单",
            base + "\n请输出纯文本（不要 JSON），不少于12条，每条以“- ”开头；不要写总结句：\n- ...\n",
        )
        sec5 = (
            "三幕结构梗概",
            base
            + "\n请输出纯文本（不要 JSON），使用如下格式：\nACT1：\n- ...\nACT2：\n- ...\nACT3：\n- ...\n每幕不少于5条。\n",
        )

        chapter_sections = []
        avg_chapters = chapters // volumes
        remainder = chapters % volumes
        current_start = 1

        def get_stage_instruction(ratio):
            if ratio < 0.2:
                return "【阶段：开局与铺垫】重点：抛出核心悬念，建立主角动机，确立初期反派。节奏要快，切入点要小。"
            elif ratio < 0.4:
                return "【阶段：发展与扩张】重点：地图/势力范围扩大，主角遭遇第一次重大挫折或强敌，爽点在于“以弱胜强”或“智谋破局”。避免单纯的打脸重复。"
            elif ratio < 0.6:
                return "【阶段：转折与危机】重点：剧情出现重大反转，原有套路失效，主角陷入绝境。引入新的力量体系或更高层面的博弈。"
            elif ratio < 0.8:
                return "【阶段：高潮前奏】重点：线索收束，多方势力混战，主角完成关键蜕变（实力或心境）。"
            else:
                return "【阶段：终局与收束】重点：最终对决，揭开所有伏笔，完成主题升华。确保结局震撼且逻辑自洽。"

        for v_idx in range(1, volumes + 1):
            count = avg_chapters + (1 if v_idx <= remainder else 0)
            if count <= 0:
                continue
            v_start = current_start
            v_end = current_start + count - 1
            current_start += count

            vol_ratio = (v_start + v_end) / 2 / chapters
            vol_stage = get_stage_instruction(vol_ratio)
            vol_title_key = f"第{v_idx}卷：分卷规划 ({v_start}-{v_end}章)"
            vol_prompt = (
                f"{base}\n"
                f"正在规划：第{v_idx}卷（共{volumes}卷），章节范围：{v_start}-{v_end}章。\n"
                f"{vol_stage}\n"
                f"任务：请为本卷设计详细的剧情蓝图。\n"
                f"要求：\n"
                f"1. 卷名：极具吸引力，概括本卷核心。\n"
                f"2. 核心冲突：本卷要解决的主要矛盾是什么？\n"
                f"3. 关键事件：列出至少5个推动剧情的大事件（每条以“- ”开头），不要少于5条。\n"
                f"4. 伏笔与钩子：本卷埋下的重要伏笔，以及留给下一卷的钩子。\n"
                f"输出纯文本（不要 JSON），建议格式：\n卷名：...\n核心冲突：...\n关键事件：\n- ...\n伏笔与钩子：...\n"
            )
            chapter_sections.append((vol_title_key, vol_prompt))

            c_ptr = v_start
            batch_size = 8 if provider == "Doubao" else 15
            while c_ptr <= v_end:
                batch_end = min(c_ptr + batch_size - 1, v_end)
                chap_title_key = f"章节大纲 第{c_ptr}-{batch_end}章 (属于第{v_idx}卷)"
                chap_prompt = (
                    f"{base}\n"
                    f"当前任务：生成第{v_idx}卷的章节细纲，范围：第{c_ptr}章 - 第{batch_end}章。\n"
                    f"请严格基于刚刚生成的【第{v_idx}卷规划】（见上下文）进行创作。\n"
                    f"要求：\n"
                    f"1. 必须逐章输出第{c_ptr}章到第{batch_end}章，不能漏章。\n"
                    f"2. 每章输出一个章节块，格式严格如下（不要省略任何字段）：\n"
                    f"   ### 第N章：标题\n"
                    f"   **内容**：...\n"
                    f"   **【悬疑点】**：...\n"
                    f"   **【爽点】**：...\n"
                    f"3. 标题不要带“第N章”字样（格式中的“第N章”由你输出的前缀承担）。\n"
                    f"4. 剧情紧凑，紧扣本卷核心冲突，且要有升级与反转。\n"
                    f"5. 开局悲剧铺垫章节，爽点允许输出“暂无”。\n"
                    f"输出纯文本（不要 JSON）。"
                )
                chapter_sections.append((chap_title_key, chap_prompt))
                c_ptr = batch_end + 1

        sec8 = (
            "读者钩子与悬念设计",
            base
            + "\n请输出纯文本（不要 JSON），使用如下格式：\nshort_term：\n- ...\nmid_term：\n- ...\nlong_term：\n- ...\n每个不少于4条。\n",
        )
        sec9 = (
            "可扩展支线与后续走向",
            base
            + "\n请输出纯文本（不要 JSON），使用如下格式：\n支线：\n- ...\n后续走向：\n- ...\n",
        )

        return [sec1, sec2, sec3, sec4, sec5] + chapter_sections + [sec8, sec9]

    def _ensure_list(self, data):
        """
        辅助函数：确保数据是列表。
        如果模型返回的是 {"items": [...]} 或 {"chapters": [...]} 这种字典结构，自动提取内部列表。
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "chapter" in data and ("title" in data or "summary" in data):
                return [data]
            # 尝试查找常见的包装键名
            for key in ["items", "list", "data", "chapters", "roles", "content", "result"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            # 如果找不到列表，但本身是字典，可能无法直接转为列表，返回空列表以触发重试
            return []
        return []

    def _parse_chapter_range_from_title(self, sec_title: str):
        m = re.search(r"章节大纲\s*第\s*(\d+)\s*-\s*(\d+)\s*章", sec_title or "")
        if not m:
            return None
        try:
            a = int(m.group(1))
            b = int(m.group(2))
        except Exception:
            return None
        if a <= 0 or b <= 0 or b < a:
            return None
        return a, b

    def _missing_chapters_in_items(self, items, a: int, b: int):
        have = set()
        for it in self._ensure_list(items):
            if isinstance(it, dict) and "chapter" in it:
                try:
                    have.add(int(it.get("chapter")))
                except Exception:
                    continue
        return [n for n in range(a, b + 1) if n not in have]

    def _format_from_data(self, title: str, data) -> str:
        if not data:
            return ""

        # 根据标题进行格式化，增加类型安全检查
        try:
            # --- 作品名与类型 ---
            if title == "作品名与类型":
                if isinstance(data, dict):
                    t = data.get("title", "未命名")
                    g = data.get("genre", "未分类")
                    return f"作品名：{t}\n类型：{g}"
                return str(data)

            # --- 核心人设 ---
            if title == "核心人设":
                items = self._ensure_list(data)
                out = []
                for item in items:
                    if isinstance(item, dict):
                        out.append(
                            f"角色：{item.get('role','')}\n"
                            f"姓名：{item.get('name','')}\n"
                            f"身份：{item.get('identity','')}\n"
                            f"欲望：{item.get('desire','')}\n"
                            f"弱点：{item.get('weakness','')}\n"
                            f"成长线：{item.get('growth','')}"
                        )
                return "\n\n".join(out)

            # --- 世界观与设定 ---
            if title == "世界观与设定":
                if isinstance(data, dict):
                    return (
                        f"时代：{data.get('era','')}\n"
                        f"地域：{data.get('region','')}\n"
                        f"权力结构：{data.get('power_structure','')}\n"
                        f"关键资源：{data.get('resources','')}\n"
                        f"规则与禁忌：{data.get('rules','')}\n"
                        f"典型场景：{data.get('scenes','')}"
                    )
                return str(data)

            # --- 爽点清单 ---
            if title == "爽点清单":
                items = self._ensure_list(data)
                return "\n".join([f"- {str(p)}" for p in items])

            # --- 三幕结构梗概 ---
            if title == "三幕结构梗概":
                if isinstance(data, dict):
                    lines = []
                    for k in ["act1", "act2", "act3"]:
                        arr = data.get(k, [])
                        if isinstance(arr, list):
                            lines.append(f"{k.upper()}：")
                            lines.extend([f"- {s}" for s in arr])
                    return "\n".join(lines)
                return str(data)

            # --- 主要角色档案 ---
            if title == "主要角色档案":
                items = self._ensure_list(data)
                out = []
                for r in items:
                    if isinstance(r, dict):
                        out.append(
                            f"姓名：{r.get('name','')}\n"
                            f"身份：{r.get('identity','')}\n"
                            f"性格：{r.get('personality','')}\n"
                            f"欲望：{r.get('desire','')}\n"
                            f"秘密：{r.get('secret','')}\n"
                            f"弱点：{r.get('weakness','')}\n"
                            f"成长线：{r.get('growth','')}\n"
                            f"与主角关系：{r.get('relation_to_protagonist','')}"
                        )
                return "\n\n".join(out)

            # --- 章节大纲 ---
            if title.startswith("章节大纲"):
                lines = []
                items = self._ensure_list(data)
                normalized = []
                for c in items:
                    if isinstance(c, dict) and "chapter" in c:
                        try:
                            cn = int(c.get("chapter"))
                        except Exception:
                            continue
                        normalized.append((cn, c))
                if normalized:
                    normalized.sort(key=lambda x: x[0])
                    items = [x[1] for x in normalized] + [c for c in items if isinstance(c, str)]
                
                for c in items:
                    if isinstance(c, dict):
                        chap = c.get('chapter', '?')
                        t = c.get('title', '')
                        summ = c.get('summary', '无内容')
                        if t:
                            # 去除可能存在的重复“第X章”前缀
                            t = re.sub(r'^第\d+章\s*', '', t).strip()
                        header = f"### 第{chap}章：{t}".strip()
                        body = (summ or "").strip() or "无内容"
                        lines.append(f"{header}\n{body}".strip())
                    elif isinstance(c, str):
                        lines.append(self._sanitize_text(c))
                
                if not lines and isinstance(data, dict):
                    return str(data)
                    
                return "\n\n".join([x for x in lines if x]).strip()

            if ("分卷规划" in title) or (title.startswith("第") and "卷" in title and ("规划" in title or "蓝图" in title)):
                if isinstance(data, dict):
                    vt = (data.get("volume_title") or "").strip()
                    cc = (data.get("core_conflict") or "").strip()
                    hooks = (data.get("hooks") or "").strip()
                    ke = data.get("key_events") or []
                    lines = []
                    if vt:
                        lines.append(f"卷名：{vt}")
                    if cc:
                        lines.append(f"核心冲突：{cc}")
                    if isinstance(ke, list) and ke:
                        lines.append("关键事件：")
                        lines.extend([f"- {str(x)}" for x in ke])
                    if hooks:
                        lines.append(f"伏笔与钩子：{hooks}")
                    return "\n".join(lines).strip()
                return str(data)

            # --- 读者钩子与悬念设计 ---
            if title == "读者钩子与悬念设计":
                if isinstance(data, dict):
                    lines = []
                    for k in ["short_term", "mid_term", "long_term"]:
                        lines.append(f"{k}：")
                        val = data.get(k, [])
                        if isinstance(val, list):
                            lines.extend([f"- {s}" for s in val])
                    return "\n".join(lines)
                return str(data)

            # --- 可扩展支线与后续走向 ---
            if title == "可扩展支线与后续走向":
                if isinstance(data, dict):
                    lines = ["支线："] 
                    sp = data.get("side_plots", [])
                    if isinstance(sp, list):
                        lines += [f"- {s}" for s in sp]
                    
                    lines += ["\n后续走向："]
                    fa = data.get("future_arcs", [])
                    if isinstance(fa, list):
                         lines += [f"- {s}" for s in fa]
                    return "\n".join(lines)
                return str(data)

        except Exception as e:
            if self.logger:
                self.logger.error(f"格式化错误 [{title}]: {str(e)} | 数据类型: {type(data)}")
            return ""
        return ""

    def _correct_section_json(self, client, models, title, bad_json_text, sec_prompt, config_local, schema):
        prompt = (
            f"请严格输出有效 JSON，严格匹配下述 schema。不得输出说明文字。\n"
            f"任务：{sec_prompt}\n"
            f"如果上一次输出不是有效 JSON：\n{bad_json_text}\n"
            f"请修正为有效 JSON。"
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        fixed = self._generate_with_fallback(client, models, contents, config_local)
        return fixed

    def _extract_json(self, text: str):
        if not isinstance(text, str):
            return text
        s = text.strip()
        fence = re.search(r"```json([\s\S]*?)```", s, re.IGNORECASE)
        if fence:
            s = fence.group(1).strip()
        start_obj = s.find('{')
        start_arr = s.find('[')
        candidates = []
        for start_char, start_idx, end_char in [('{' , start_obj, '}'), ('[', start_arr, ']')]:
            if start_idx != -1:
                depth = 0
                for i in range(start_idx, len(s)):
                    c = s[i]
                    if c == start_char:
                        depth += 1
                    elif c == end_char:
                        depth -= 1
                        if depth == 0:
                            candidates.append(s[start_idx:i+1])
                            break
        if candidates:
            return max(candidates, key=len)
        return s

    def _parse_json(self, text: str):
        s = self._extract_json(text)
        try:
            return json.loads(s)
        except Exception:
            s2 = s.replace("'", '"')
            s2 = re.sub(r",\s*(\}|\])", r"\1", s2)
            try:
                return json.loads(s2)
            except Exception:
                return None

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

    def _violates_genre(self, novel_type: str, text: str) -> bool:
        ban = self._get_forbidden_terms(novel_type)
        t = text.lower()
        for term in ban:
            if term in t:
                return True
        return False

    def _contains_meta(self, text: str) -> bool:
        t = text.strip()
        patterns = ["收到", "感谢", "作为资深", "我将", "我会", "策划案", "以下是", "将为您", "为了确保", "基于您"]
        tl = t.lower()
        for p in patterns:
            if p in t or p in tl:
                return True
        return False

    def _is_empty_section(self, title: str, text: str) -> bool:
        if len(text.strip()) < 20:
            return True
        return False

    def _get_forbidden_terms(self, novel_type: str):
        t = (novel_type or "").strip()
        allow_fantasy = any(k in t for k in ["仙侠", "玄幻", "奇幻"])
        allow_scifi = any(k in t for k in ["科幻"])
        allow_apocalypse = any(k in t for k in ["末世"])
        allow_supernatural = any(k in t for k in ["灵异", "悬疑灵异", "恐怖"])

        realistic_ban = [
            "修真", "仙侠", "灵气", "法术", "飞升", "渡劫", "妖兽",
            "赛博", "星际", "外星", "末日", "机甲",
            "cultivation", "cyber", "cyber-cultivation",
        ]
        scifi_ban = ["修真", "仙侠", "灵气", "法术", "飞升", "渡劫", "妖兽", "cultivation"]
        fantasy_ban = ["赛博", "星际", "外星", "机甲", "cyber"]

        if allow_scifi or allow_apocalypse:
            return [s.lower() for s in scifi_ban]
        if allow_fantasy or allow_supernatural:
            return [s.lower() for s in fantasy_ban]
        return [s.lower() for s in realistic_ban]

    def _correct_section(self, client, models, title, bad_text, novel_type, theme, config):
        forbid = ",".join(self._get_forbidden_terms(novel_type))
        prompt = (
            f"类型：{novel_type}\n主题/设定：{theme}\n"
            f"上一段输出存在问题（偏离类型/空输出/包含不合规元素或元叙述）：\n{bad_text}\n"
            f"请在保持结构与字数相近的情况下，完全重写成符合类型与主题的中文内容。\n"
            f"禁止出现感谢、收到、自我介绍等元叙述；避免出现：{forbid}。\n"
            f"只输出《{title}》这一部分的纯内容，避免额外说明。"
        )
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        fixed = self._generate_with_fallback(client, models, contents, config)
        return fixed

    def _update_progress(self):
        self.progress_var.set(f"进度 {self.completed_sections}/{self.total_sections}")

    def _update_eta(self, extra_wait: int = 0):
        if not self.start_time or self.total_sections == 0:
            return
        elapsed = time.time() - self.start_time
        done = max(self.completed_sections, 1)
        avg = elapsed / done
        remaining = max(self.total_sections - self.completed_sections, 0)
        eta_secs = int(avg * remaining + extra_wait)
        finish_ts = time.time() + eta_secs
        finish_str = time.strftime("%H:%M:%S", time.localtime(finish_ts))
        mins, secs = divmod(eta_secs, 60)
        self.status_var.set(f"剩余约 {mins}分{secs}秒，预计完成 {finish_str}")

    def _setup_logger(self, novel_type: str, theme: str, chapters: int):
        try:
            if getattr(sys, "frozen", False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))

            log_dir = os.path.join(base_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_type = self._slug(novel_type) or "outline"
            fname = f"{safe_type}_{ts}.log"
            path = os.path.join(log_dir, fname)
            
            # 创建 Logger
            logger = logging.getLogger("outline")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            
            # 清除旧的 handlers，防止重复写入
            if logger.hasHandlers():
                for h in list(logger.handlers):
                    try:
                        h.flush()
                    except Exception:
                        pass
                    try:
                        h.close()
                    except Exception:
                        pass
                logger.handlers.clear()
            
            # 设置 FileHandler
            handler = logging.FileHandler(path, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            handler.setFormatter(formatter)
            
            logger.addHandler(handler)
            self.logger = logger
            self.log_path = path
            
            # 立即写入一条测试日志
            logger.info(f"=== 启动生成任务 ===")
            logger.info(f"类型: {novel_type}")
            logger.info(f"章节数: {chapters}")
            logger.info(f"主题: {theme}")
            logger.info(f"日志文件路径: {path}")

            try:
                handler.flush()
            except Exception:
                pass
            
        except Exception as e:
            print(f"Logger setup failed: {e}")
            self.logger = None
            self.log_path = None

    def _load_api_key(self, provider="Gemini") -> str:
        if provider == "Gemini":
            key_field = "api_key"
            env_var = "GEMINI_API_KEY"
            fallback_field = None
            fallback_env = None
        elif provider == "Claude":
            key_field = "claude_api_key"
            env_var = "CLAUDE_API_KEY"
            fallback_field = None
            fallback_env = "ANTHROPIC_API_KEY"
        elif provider == "Doubao":
            key_field = "doubao_api_key"
            env_var = "DOUBAO_API_KEY"
            fallback_field = None
            fallback_env = None
        else:
            return ""
        
        try:
            cfg_path = self._find_config_path()
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    key = (cfg.get(key_field) or "").strip()
                    if (not key) and fallback_field:
                        key = (cfg.get(fallback_field) or "").strip()
                    if key:
                        return key
        except Exception:
            pass
        k = (os.environ.get(env_var, "") or "").strip()
        if k:
            return k
        if fallback_env:
            return (os.environ.get(fallback_env, "") or "").strip()
        return ""

    def _load_doubao_base_url(self) -> str:
        try:
            cfg_path = self._find_config_path()
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    u = (cfg.get("doubao_base_url") or "").strip()
                    if u:
                        return u
        except Exception:
            pass
        u = (os.environ.get("DOUBAO_BASE_URL", "") or "").strip()
        if u:
            return u
        return DEFAULT_DOUBAO_BASE_URL

    def _load_claude_base_url(self) -> str:
        try:
            cfg_path = self._find_config_path()
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    u = (cfg.get("claude_base_url") or "").strip()
                    if u:
                        return u
        except Exception:
            pass
        u = (os.environ.get("ANTHROPIC_BASE_URL", "") or os.environ.get("CLAUDE_BASE_URL", "") or "").strip()
        if u:
            return u
        return DEFAULT_CLAUDE_BASE_URL

    def _load_doubao_model(self) -> str:
        try:
            cfg_path = self._find_config_path()
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    m = (cfg.get("doubao_model") or "").strip()
                    if m:
                        return m
        except Exception:
            pass
        return (os.environ.get("DOUBAO_MODEL", "") or "").strip()

    def _auto_save(self, novel_type: str, theme: str):
        content = self.output.get("1.0", tk.END).strip()
        if not content:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        novel_title = self._extract_outline_title(content) or (novel_type or "").strip() or "未命名"
        filename = f"{self._slug(novel_title)}_{ts}_大纲.txt"
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        path = os.path.join(base_dir, filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.last_outline_path = path
            messagebox.showinfo("自动保存", f"文件已保存至：\n{path}")
        except Exception as e:
            messagebox.showerror("自动保存失败", str(e))

    def on_save(self):
        content = self.output.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("无内容", "当前没有可保存的内容")
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        novel_title = self._extract_outline_title(content) or (self.type_var.get() or "").strip() or "未命名"
        initial = f"{self._slug(novel_title)}_{ts}_大纲.txt"
        path = filedialog.asksaveasfilename(
            title="保存小说大纲",
            defaultextension=".txt",
            initialfile=initial,
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.last_outline_path = path
            messagebox.showinfo("已保存", f"保存路径：{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def on_export_zip(self):
        output_text = self.output.get("1.0", tk.END).strip()
        content = output_text
        if ("正在生成 第" in output_text) or (">>> 正在生成" in output_text) or ("所有章节正文生成完毕" in output_text):
            content = (self.full_outline_context or "").strip() or output_text
        if not content and not self.chapters_data:
            messagebox.showwarning("无内容", "当前没有可导出的内容")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        initial = f"{self._slug(self.type_var.get())}_{ts}_大纲包.zip"
        path = filedialog.asksaveasfilename(
            title="导出ZIP包",
            defaultextension=".zip",
            initialfile=initial,
            filetypes=[("ZIP Archive", "*.zip"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            # 自动备份
            try:
                self._auto_save(self.type_var.get(), self.theme_var.get())
            except:
                pass

            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 1. 写入完整大纲
                zf.writestr("完整大纲.txt", content)
                
                # 2. 写入章节细分
                if self.chapters_data:
                    # 创建章节目录结构
                    for item in self.chapters_data:
                        if not isinstance(item, dict):
                            continue
                        
                        chap_num = item.get('chapter')
                        chap_title = item.get('title', '')
                        summary = item.get('summary', '')
                        if isinstance(chap_title, list):
                            chap_title = "\n".join(str(x) for x in chap_title)
                        chap_title = str(chap_title or "")
                        if isinstance(summary, list):
                            summary = "\n".join(str(x) for x in summary)
                        summary = str(summary or "").strip()
                        
                        if chap_num is not None:
                            try:
                                chap_num = int(chap_num)
                                # 格式化文件名: 001_章节标题.txt
                                # 去除标题中可能存在的重复“第X章”前缀
                                if chap_title:
                                    chap_title = re.sub(r'^第\d+章\s*', '', chap_title).strip()
                                    
                                # 如果没有标题，使用摘要前15字
                                name_part = chap_title if chap_title else summary[:15]
                                clean_name = self._slug(name_part)
                                filename = f"章节/{chap_num:03d}_{clean_name}.txt"
                                
                                file_content_lines = [f"第{chap_num}章 {chap_title}"]
                                file_content_lines.append(f"\n梗概：\n{summary}")
                                
                                # 检查是否有生成的正文
                                if hasattr(self, 'generated_chapters_content') and chap_num in self.generated_chapters_content:
                                    file_content_lines.append("\n\n" + "="*20 + " 正文 " + "="*20 + "\n")
                                    file_content_lines.append(self.generated_chapters_content[chap_num])
                                else:
                                    file_content_lines.append("\n(此处可后续扩展正文)")
                                
                                zf.writestr(filename, "\n".join(file_content_lines))
                            except Exception:
                                pass
                                
            messagebox.showinfo("已导出", f"ZIP包已保存：\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def on_generate_novel(self):
        if not self._require_login_and_token():
            return
        if not self.chapters_data:
            messagebox.showwarning("无大纲", "请先生成或解析小说大纲！")
            return
        
        provider = "Gemini"
        model = self.model_var.get()
        api_key = self._load_api_key("Gemini")
        
        if not api_key:
            messagebox.showerror("错误", "未配置 API Key，请在 config.json 或环境变量 GEMINI_API_KEY 中设置")
            return
            
        self.generate_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.export_zip_btn.config(state=tk.DISABLED)
        self.generate_novel_btn.config(state=tk.DISABLED)
        if hasattr(self, "generate_novel_zip_btn"):
            self.generate_novel_zip_btn.config(state=tk.DISABLED)
        self.parse_btn.config(state=tk.DISABLED)
        self._cancel_event.clear()
        self.stop_btn.config(state=tk.NORMAL)
        
        self.status_var.set(f"准备使用 {provider} 生成正文...")
        self.generated_chapters_content = {} 
        
        threading.Thread(target=self._run_novel_generation, args=(provider, api_key, model), daemon=True).start()

    def on_generate_novel_and_export(self):
        if not self._require_login_and_token():
            return
        self._auto_export_zip_after_novel = True
        self.on_generate_novel()

    def _run_novel_generation(self, provider, api_key, model_name):
        auto_export_zip = bool(getattr(self, "_auto_export_zip_after_novel", False))
        try:
            if self.logger:
                self.logger.info(f"开始生成小说正文 ({provider} - {model_name})")
            
            # Gemini Client Init (Only if needed)
            client = None
            if provider == "Gemini":
                client = genai.Client(api_key=api_key)
                models = [model_name, "gemini-2.5-pro"] if "gemini" in model_name.lower() else [model_name]
            
            # 过滤出有效的章节数据
            valid_chapters = []
            for c in self.chapters_data:
                if isinstance(c, dict) and c.get('chapter') is not None:
                    valid_chapters.append(c)
            
            total_chapters = len(valid_chapters)
            self.root.after(0, lambda: self.progress_var.set(f"正文进度 0/{total_chapters}"))
            
            # 构建基础上下文
            novel_type = self.type_var.get()
            theme = self.theme_var.get()
            # 用户要求发送完整大纲，Gemini模型支持长上下文，取消截断
            context_base = (
                f"小说类型：{novel_type}\n"
                f"主题：{theme}\n"
                f"完整大纲参考：\n{self.full_outline_context}" 
            )
            
            last_chapter_text = "" # 用于存储上一章正文，保持连贯性

            for i, chap in enumerate(valid_chapters, 1):
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成正文。\n")
                    break
                chap_num = int(chap.get('chapter'))
                chap_title = chap.get('title', '')
                chap_summary = chap.get('summary', '')
                
                if chap_title:
                    chap_title = re.sub(r'^第\d+章\s*', '', chap_title).strip()
                
                self.root.after(0, self._append_text, f"\n\n>>> 正在生成 第{chap_num}章 {chap_title} ...\n")
                self.root.after(0, lambda: self.status_var.set(f"正在生成 第{chap_num}章"))
                if self.logger:
                    self.logger.info(f"生成章节: 第{chap_num}章 {chap_title}")

                # 构建上一章的回顾，增强连贯性
                prev_context_prompt = ""
                if last_chapter_text:
                    # 截取上一章最后2000字作为上下文
                    prev_text_segment = last_chapter_text[-2000:]
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
                
                if provider in ("Doubao", "Claude"):
                    system_inst = build_system_instruction() + "\n" + build_constraints(novel_type, theme, self.channel_var.get())
                    if provider == "Claude":
                        content_out = self._call_claude(api_key, model_name, system_inst, prompt, temperature=0.8, max_tokens=8192)
                    else:
                        base_url = self._load_doubao_base_url()
                        content_out = self._call_compat_chat(api_key, model_name, system_inst, prompt, temperature=0.8, base_url=base_url)
                else:
                    # Gemini 生成
                    config = types.GenerateContentConfig(
                        temperature=0.8, 
                        max_output_tokens=8000,
                        top_p=0.95,
                    )
                    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
                    content_out = self._generate_with_fallback(client, models, contents, config)
                
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成正文。\n")
                    break

                content_out = self._sanitize_text(content_out)
                
                self.generated_chapters_content[chap_num] = content_out
                last_chapter_text = content_out # 更新上一章内容
                
                # 实时显示部分内容或提示完成
                preview = content_out[:200] + "..." if len(content_out) > 200 else content_out
                self.root.after(0, self._append_text, f"{preview}\n[第{chap_num}章 完成]\n")
                self.root.after(0, lambda: self.progress_var.set(f"正文进度 {i}/{total_chapters}"))
                
                # 简单的防频控休眠
                time.sleep(2)

            if not self._cancel_event.is_set():
                self.root.after(0, self._append_text, "\n\n====== 所有章节正文生成完毕 ======\n")
                if self.logger:
                    self.logger.info("所有章节正文生成完毕")
                if auto_export_zip:
                    def do_export_zip():
                        try:
                            self._auto_export_zip_after_novel = False
                            self.status_var.set("正文生成完毕，准备导出ZIP...")
                            self.on_export_zip()
                        finally:
                            self._auto_export_zip_after_novel = False
                    self.root.after(0, do_export_zip)
                else:
                    self.root.after(0, lambda: messagebox.showinfo("完成", "小说正文生成完毕，请点击“导出ZIP包”获取完整小说文件。"))

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "生成正文失败", err_msg)
            if self.logger:
                self.logger.error(f"生成正文失败: {err_msg}")
        finally:
            self._auto_export_zip_after_novel = False
            self._reset_ui_state()

    def _run_compat_generation(self, provider, api_key, model_name, novel_type, theme, chapters, volumes):
        try:
            self.generation_variation = self._new_generation_variation(novel_type, theme)
            self._setup_logger(novel_type, theme, chapters)
            self.start_time = time.time()
            
            constraints_text = build_constraints(novel_type, theme, self.channel_var.get()) + "\n" + (self.generation_variation or "")
            system_prompt = build_system_instruction() + "\n" + constraints_text
            base_url = self._load_doubao_base_url()
            
            # --- 1. 优化提示词 ---
            self.root.after(0, self._append_text, f"正在使用 {provider} ({model_name}) 优化指令...\n")
            if self.logger: self.logger.info("开始备用模型提示词优化")
            
            optimize_prompt = (
                "你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n"
                f"小说类型：{novel_type}\n"
                f"核心主题：{theme}\n\n"
                "要求：\n"
                "1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n"
                "2. 细化对人设、世界观、冲突节奏的具体要求。\n"
                "3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n"
                "4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n"
                "5. 针对长篇结构，设计“螺旋式上升”的剧情结构，避免重复。\n"
                "6. 章节标题生成时，请只输出标题文字，不要包含“第X章”字样。\n"
                "7. 【章节强制格式】每一章的 summary 必须严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”，其余不得留空）。\n"
                "8. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。"
            )
            
            optimized_instruction = self._call_compat_chat(api_key, model_name, system_prompt, optimize_prompt, temperature=0.7, base_url=base_url)
            self.last_optimized_instruction = (optimized_instruction or "").strip() if isinstance(optimized_instruction, str) else str(optimized_instruction)
            self.last_constraints_text = (constraints_text or "").strip()
            if not optimized_instruction:
                optimized_instruction = system_prompt
            else:
                system_prompt = optimized_instruction.strip() + "\n" + constraints_text
            
            if self.logger: self.logger.info(f"优化后指令: {system_prompt[:100]}...")
            self.root.after(
                0,
                self._append_text,
                "\n\n### 专业提示词（本次用于生成大纲）\n"
                + (optimized_instruction.strip() if isinstance(optimized_instruction, str) else str(optimized_instruction))
                + "\n\n"
                + (self.generation_variation or ""),
            )
            self.root.after(0, self._append_text, "指令优化完成，开始生成正文...\n")
            
            # --- 2. 生成各章节 ---
            sections = self._build_sections_text(novel_type, theme, chapters, volumes, provider=provider)
            self.total_sections = len(sections)
            self.completed_sections = 0
            self.root.after(0, self._update_progress)
            
            accumulated = ""
            
            for i, sec in enumerate(sections, start=1):
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成。\n")
                    break
                self._wait_if_paused()
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成。\n")
                    break
                sec_title = sec[0]
                sec_prompt = sec[1]
                sec_schema = sec[2] if len(sec) > 2 else None
                
                self.root.after(0, self._append_text, f"\n\n### {i}. {sec_title}\n")
                if self.logger: self.logger.info(f"开始生成: {sec_title}")
                
                # 上下文注入
                current_prompt = sec_prompt
                if accumulated:
                    context_text = accumulated[-20000:]
                    current_prompt = (
                        f"【前文内容参考】\n{context_text}\n"
                        f"----------------\n"
                        f"基于前文继续创作：\n{current_prompt}"
                    )
                    
                if sec_title.startswith("章节大纲") and self.all_chapter_summaries:
                    context_summary = "\n".join(self.all_chapter_summaries)[-4000:]
                    current_prompt += (
                        f"\n\n【前序章节梗概】\n{context_summary}\n"
                        f"----------------\n"
                        f"承接剧情发展，确保连贯且有新意。\n"
                    )

                if sec_schema:
                    text_out = self._call_compat_chat(api_key, model_name, system_prompt, current_prompt, temperature=0.5, base_url=base_url)
                else:
                    text_out = ""
                    last_sanitized = ""
                    attempt_prompt = current_prompt
                    for attempt in range(3):
                        self._wait_if_paused()
                        if self._cancel_event.is_set():
                            break
                        temp = 0.7 if attempt == 0 else 0.55
                        out = self._call_compat_chat(api_key, model_name, system_prompt, attempt_prompt, temperature=temp, base_url=base_url)
                        sanitized = self._sanitize_text(out or "")
                        last_sanitized = sanitized
                        ok = True
                        if sec_title.startswith("章节大纲"):
                            ok = False
                            rng = self._parse_chapter_range_from_title(sec_title)
                            parsed = self._parse_chapters_from_outline_text(sanitized)
                            if rng and isinstance(parsed, dict):
                                a, b = rng
                                expected = b - a + 1
                                got = [k for k in parsed.keys() if a <= int(k) <= b]
                                if len(got) >= expected:
                                    ok = True
                            elif isinstance(parsed, dict) and len(parsed) >= 3:
                                ok = True
                        else:
                            if self._is_empty_section(sec_title, sanitized):
                                ok = False
                        if ok and sanitized:
                            text_out = sanitized
                            break
                        attempt_prompt = attempt_prompt + "\n\n上一次输出不完整或过短，请严格按要求完整输出，不要省略任何条目，也不要解释。"
                    if (not text_out) and last_sanitized:
                        text_out = last_sanitized
                
                # 处理输出
                if sec_schema:
                    json_data = self._parse_json(text_out)
                    if not json_data:
                        if self.logger: self.logger.warning("JSON 解析失败，尝试纠错")
                        fix_prompt = f"上一次输出的 JSON 格式有误，请修正为合法的 JSON：\n{text_out}"
                        text_out_fixed = self._call_compat_chat(api_key, model_name, system_prompt, fix_prompt, temperature=0.1, base_url=base_url)
                        json_data = self._parse_json(text_out_fixed)
                    
                    if sec_title.startswith("章节大纲") and not json_data:
                        rng = self._parse_chapter_range_from_title(sec_title)
                        if rng:
                            a, b = rng
                            if self.logger:
                                self.logger.warning(f"章节范围 {a}-{b} 结构化失败，重新请求补全")
                            regen_prompt = (
                                f"任务：生成章节大纲，范围：第{a}章-第{b}章。\n"
                                f"要求：\n"
                                f"1. 只输出 JSON 数组，每项包含 chapter(整数)、title(章节标题)、summary(中文2-3句)。\n"
                                f"2. title 不要带“第X章”。\n"
                                f"3. summary 必须严格使用如下格式（爽点允许为“暂无”，其余不得留空）：**内容**：... **【悬疑点】**：... **【爽点】**：...\n"
                                f"4. 必须承接上下文，避免逻辑冲突。\n"
                            )
                            ctx_existing = self._parse_chapters_from_outline_text(accumulated)
                            range_context = self._build_chapter_range_context(accumulated, ctx_existing, a, b)
                            regen_prompt = f"【上下文参考】\n{range_context}\n----------------\n{regen_prompt}"
                            regen_text = self._call_compat_chat(api_key, model_name, system_prompt, regen_prompt, temperature=0.5, base_url=base_url)
                            json_data = self._parse_json(regen_text)
                            if not json_data:
                                by_ch = dict(ctx_existing) if isinstance(ctx_existing, dict) else {}
                                for n in range(a, b + 1):
                                    if n not in by_ch:
                                        t, s = self._synthesize_missing_chapter(by_ch, n)
                                        by_ch[n] = {"chapter": n, "title": t, "summary": s}
                                json_data = [by_ch[k] for k in sorted(by_ch.keys()) if a <= k <= b]
                    
                    formatted = ""
                    if json_data:
                        if sec_title.startswith("章节大纲"):
                            rng = self._parse_chapter_range_from_title(sec_title)
                            if rng:
                                a, b = rng
                                missing_chaps = self._missing_chapters_in_items(json_data, a, b)
                                attempt = 0
                                while missing_chaps and attempt < 5:
                                    attempt += 1
                                    miss_str = ", ".join(str(x) for x in missing_chaps[:20])
                                    fill_prompt = (
                                        f"任务：补全章节大纲缺失部分。\n"
                                        f"范围：第{a}章-第{b}章。\n"
                                        f"只补全这些缺失章号：{miss_str}。\n"
                                        f"要求：只输出 JSON 数组；每项包含 chapter(整数)、title、summary；summary 必须包含：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”）\n"
                                    )
                                    if accumulated:
                                        ctx = accumulated[-20000:]
                                        fill_prompt = f"【前文内容参考】\n{ctx}\n----------------\n{fill_prompt}"
                                    fill_text = self._call_compat_chat(api_key, model_name, system_prompt, fill_prompt, temperature=0.4, base_url=base_url)
                                    fill_data = self._parse_json(fill_text)
                                    base_items = self._ensure_list(json_data)
                                    fill_items = self._ensure_list(fill_data) if fill_data is not None else []
                                    by_ch = {}
                                    for it in base_items + fill_items:
                                        if isinstance(it, dict) and "chapter" in it:
                                            try:
                                                cn = int(it.get("chapter"))
                                            except Exception:
                                                continue
                                            if a <= cn <= b:
                                                by_ch[cn] = {
                                                    "chapter": cn,
                                                    "title": (it.get("title") or "").strip() or "未命名",
                                                    "summary": (it.get("summary") or "").strip() or "无内容",
                                                }
                                    json_data = [by_ch[k] for k in sorted(by_ch.keys())]
                                    missing_chaps = self._missing_chapters_in_items(json_data, a, b)
                                if missing_chaps:
                                    by_ch = {int(it.get("chapter")): it for it in self._ensure_list(json_data) if isinstance(it, dict) and "chapter" in it}
                                    for n in missing_chaps:
                                        t, s = self._synthesize_missing_chapter(by_ch, n)
                                        by_ch[n] = {"chapter": n, "title": t, "summary": s}
                                    json_data = [by_ch[k] for k in sorted(by_ch.keys())]
                        formatted = self._format_from_data(sec_title, json_data)
                        if not formatted:
                            try:
                                formatted = json.dumps(json_data, ensure_ascii=False, indent=2)
                            except Exception:
                                formatted = str(json_data)
                        if sec_title.startswith("章节大纲"):
                            items = self._ensure_list(json_data)
                            self.chapters_data.extend(items)
                            for item in items:
                                if isinstance(item, dict):
                                    s = item.get("summary", "")
                                    if s: self.all_chapter_summaries.append(f"第{item.get('chapter')}章：{s}")
                    
                    text_out_final = formatted or text_out
                else:
                    text_out_final = text_out

                if text_out_final:
                    self.root.after(0, self._append_text, text_out_final)
                    accumulated += "\n\n### " + str(i) + ". " + sec_title + "\n" + text_out_final
                    self.completed_sections += 1
                    self.root.after(0, self._update_progress)
                    self.root.after(0, self._update_eta, 0)
            
            if not self._cancel_event.is_set():
                accumulated = self._post_fill_missing_after_generation(
                    provider,
                    api_key,
                    model_name,
                    novel_type,
                    theme,
                    chapters,
                    volumes,
                    accumulated,
                )

            if not self._cancel_event.is_set():
                self.root.after(0, self._auto_save, novel_type, theme)
                if self.logger:
                    self.logger.info("备用模型生成完成")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "生成失败", err_msg)
            if self.logger: self.logger.error(f"生成失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _run_claude_generation(self, provider, api_key, model_name, novel_type, theme, chapters, volumes):
        try:
            self.generation_variation = self._new_generation_variation(novel_type, theme)
            self._setup_logger(novel_type, theme, chapters)
            self.start_time = time.time()

            constraints_text = build_constraints(novel_type, theme, self.channel_var.get()) + "\n" + (self.generation_variation or "")
            system_prompt = build_system_instruction() + "\n" + constraints_text

            self.root.after(0, self._append_text, f"正在使用 {provider} ({model_name}) 优化指令...\n")
            optimize_prompt = (
                "你是资深网文主编，请根据以下基础信息，扩充并优化出一份专业的小说大纲生成提示词（System Instruction）。\n"
                f"小说类型：{novel_type}\n"
                f"核心主题：{theme}\n\n"
                "要求：\n"
                "1. 分析该类型的核心爽点、受众心理和市场热门趋势。\n"
                "2. 细化对人设、世界观、冲突节奏的具体要求。\n"
                "3. 强调输出风格（如节奏快、反转多、情绪拉扯强）。\n"
                "4. 输出一段完整的、指令性强的 System Instruction，用于指导AI生成大纲。\n"
                "5. 针对长篇结构，设计“螺旋式上升”的剧情结构，避免重复。\n"
                "6. 章节标题生成时，请只输出标题文字，不要包含“第X章”字样。\n"
                "7. 【章节强制格式】每一章的 summary 必须严格包含三行：**内容**：... **【悬疑点】**：... **【爽点】**：...（爽点允许为“暂无”，其余不得留空）。\n"
                "8. 不要包含任何解释性文字，直接输出优化后的 Instruction 内容。"
            )

            optimized_instruction = ""
            try:
                optimized_instruction = self._call_claude(api_key, model_name, system_prompt, optimize_prompt, temperature=0.7, max_tokens=2048)
            except Exception:
                optimized_instruction = ""
            self.last_optimized_instruction = (optimized_instruction or "").strip()
            self.last_constraints_text = (constraints_text or "").strip()
            if not optimized_instruction:
                optimized_instruction = build_system_instruction()
            system_prompt = optimized_instruction.strip() + "\n" + constraints_text

            self.root.after(
                0,
                self._append_text,
                "\n\n### 专业提示词（本次用于生成大纲）\n"
                + optimized_instruction.strip()
                + "\n\n"
                + (self.generation_variation or ""),
            )
            self.root.after(0, self._append_text, "指令优化完成，开始生成正文...\n")

            sections = self._build_sections_text(novel_type, theme, chapters, volumes, provider=provider)
            self.total_sections = len(sections)
            self.completed_sections = 0
            self.root.after(0, self._update_progress)

            accumulated = ""
            for i, sec in enumerate(sections, start=1):
                if self._cancel_event.is_set():
                    self.root.after(0, self._append_text, "\n\n[系统] 已停止生成。\n")
                    break
                sec_title = sec[0]
                sec_prompt = sec[1]

                self.root.after(0, self._append_text, f"\n\n### {i}. {sec_title}\n")
                if self.logger:
                    self.logger.info(f"开始生成: {sec_title}")

                current_prompt = sec_prompt
                if accumulated:
                    context_text = accumulated[-20000:]
                    current_prompt = (
                        f"【前文内容参考】\n{context_text}\n"
                        f"----------------\n"
                        f"基于前文继续创作：\n{current_prompt}"
                    )

                if sec_title.startswith("章节大纲") and self.all_chapter_summaries:
                    context_summary = "\n".join(self.all_chapter_summaries)[-4000:]
                    current_prompt += (
                        f"\n\n【前序章节梗概】\n{context_summary}\n"
                        f"----------------\n"
                        f"承接剧情发展，确保连贯且有新意。\n"
                    )

                self._wait_if_paused()
                if self._cancel_event.is_set():
                    break
                text_out = self._call_claude(api_key, model_name, system_prompt, current_prompt, temperature=0.7, max_tokens=4096)
                text_out_final = self._sanitize_text(text_out or "")

                if text_out_final:
                    self.root.after(0, self._append_text, text_out_final)
                    accumulated += "\n\n### " + str(i) + ". " + sec_title + "\n" + text_out_final
                    self.completed_sections += 1
                    self.root.after(0, self._update_progress)
                    self.root.after(0, self._update_eta, 0)

            if not self._cancel_event.is_set():
                accumulated = self._post_fill_missing_after_generation(
                    provider, api_key, model_name, novel_type, theme, chapters, volumes, accumulated
                )
                self.root.after(0, self._auto_save, novel_type, theme)
                if self.logger:
                    self.logger.info("Claude 生成完成")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "生成失败", err_msg)
            if self.logger:
                self.logger.error(f"生成失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _call_compat_chat(self, api_key, model, system, user_msg, temperature=0.7, base_url=None):
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("未配置兼容接口 Base URL")
        if base_url.lower().endswith("/chat/completions"):
            url = base_url
        else:
            url = f"{base_url}/chat/completions"
        base_url_l = base_url.lower()
        is_ark = ("volces.com" in base_url_l) or ("ark" in base_url_l)
        timeout_secs = 300 if is_ark else 120
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg}
            ],
            "temperature": temperature,
            "max_tokens": 4000,
            "stream": False
        }
        
        retries = 5 if is_ark else 3
        for i in range(retries):
            if self._cancel_event.is_set():
                return ""
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=timeout_secs)
                if resp.status_code >= 400:
                    body = (resp.text or "").strip()
                    if resp.status_code == 404 and ("volces.com" in url.lower() or "volc" in url.lower() or "ark" in url.lower()):
                        raise requests.HTTPError(f"{resp.status_code} Client Error: {body or 'Not Found'}; 豆包 Ark 通常需要使用 Endpoint ID（ep-...）作为 model", response=resp)
                    raise requests.HTTPError(f"{resp.status_code} Client Error: {body or resp.reason}", response=resp)
                res_json = resp.json()
                return res_json['choices'][0]['message']['content']
            except requests.exceptions.ReadTimeout as e:
                if i < retries - 1:
                    try:
                        mt = int(data.get("max_tokens") or 4000)
                        data["max_tokens"] = max(1200, int(mt * 0.7))
                    except Exception:
                        pass
                    time.sleep(min(30, 3 * (i + 1)))
                    continue
                if self.logger:
                    self.logger.error(f"兼容接口 API Error: {e}")
                raise e
            except Exception as e:
                if i < retries - 1:
                    time.sleep(2 * (i+1))
                    continue
                if self.logger: self.logger.error(f"兼容接口 API Error: {e}")
                raise e
        return ""

    def _call_claude(self, api_key, model, system, user_msg, temperature=0.7, base_url=None, max_tokens: int = 4096):
        url = (base_url or self._load_claude_base_url() or DEFAULT_CLAUDE_BASE_URL).strip()
        timeout_secs = 180
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        data = {
            "model": (model or DEFAULT_CLAUDE_MODEL),
            "max_tokens": int(max(256, min(8192, max_tokens))),
            "temperature": float(temperature),
            "system": system or "",
            "messages": [{"role": "user", "content": user_msg or ""}],
        }

        for i in range(3):
            if self._cancel_event.is_set():
                return ""
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=timeout_secs)
                if resp.status_code >= 400:
                    body = (resp.text or "").strip()
                    raise requests.HTTPError(f"{resp.status_code} Client Error: {body or resp.reason}", response=resp)
                res_json = resp.json() or {}
                parts = res_json.get("content") or []
                if isinstance(parts, list):
                    text_parts = []
                    for p in parts:
                        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
                            text_parts.append(p["text"])
                    out = "".join(text_parts).strip()
                    if out:
                        return out
                if isinstance(res_json.get("text"), str) and res_json.get("text").strip():
                    return res_json.get("text").strip()
                return ""
            except requests.exceptions.ReadTimeout:
                if i < 2:
                    time.sleep(min(20, 2 * (i + 1)))
                    continue
                raise
            except Exception:
                if i < 2:
                    time.sleep(2 * (i + 1))
                    continue
                raise

    def on_parse_outline(self):
        text = self.output.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "文本框为空，请先粘贴大纲内容")
            return
        self._sync_chapters_from_text(text, show_message=True)

    def _sync_chapters_from_text(self, text: str, show_message: bool = False):
        t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not t:
            self.chapters_data = []
            self.all_chapter_summaries = []
            self.full_outline_context = ""
            return

        self.full_outline_context = t
        chapters = self._parse_chapters_from_outline_text(t)
        if isinstance(chapters, dict) and chapters:
            items = [chapters[k] for k in sorted(chapters.keys())]
        else:
            items = []
            matches = list(re.finditer(r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)", t))
            for m in matches:
                try:
                    c_num = int(m.group(2))
                except Exception:
                    continue
                title_only = (m.group(3) or "").strip()
                full_title_part = (m.group(1) or "").strip()
                title_clean = re.sub(r"^第\s*\d+\s*章\s*", "", full_title_part).strip()
                if title_only:
                    title_clean = title_only
                summary = (m.group(4) or "").strip() or "无内容"
                items.append({"chapter": c_num, "title": title_clean, "summary": summary})

        items = [it for it in items if isinstance(it, dict) and it.get("chapter") is not None]
        items.sort(key=lambda x: int(x.get("chapter")))
        self.chapters_data = items
        self.all_chapter_summaries = [
            f"第{it.get('chapter')}章：{(it.get('summary') or '').strip()[:50]}..."
            for it in items
        ]

        if items:
            try:
                max_ch = max(int(it.get("chapter")) for it in items if it.get("chapter") is not None)
                if max_ch:
                    self.chapters_var.set(max_ch)
                    if int(self.expand_to_var.get() or 0) < max_ch:
                        self.expand_to_var.set(max_ch)
            except Exception:
                pass

            if hasattr(self, "generate_novel_btn"):
                self.generate_novel_btn.config(state=tk.NORMAL)
            if hasattr(self, "generate_novel_zip_btn"):
                self.generate_novel_zip_btn.config(state=tk.NORMAL)
            if hasattr(self, "export_zip_btn"):
                self.export_zip_btn.config(state=tk.NORMAL)
            if hasattr(self, "save_btn"):
                self.save_btn.config(state=tk.NORMAL)
            if hasattr(self, "polish_btn"):
                self.polish_btn.config(state=tk.NORMAL)
            if hasattr(self, "regen_btn"):
                self.regen_btn.config(state=tk.NORMAL)
            if hasattr(self, "apply_feedback_btn"):
                self.apply_feedback_btn.config(state=tk.NORMAL)
            if hasattr(self, "check_suggest_btn"):
                self.check_suggest_btn.config(state=tk.NORMAL)
            if show_message:
                messagebox.showinfo("解析成功", f"成功解析出 {len(items)} 个章节。")
        else:
            if show_message:
                messagebox.showwarning("解析失败", "未找到符合格式（如“第1章...”或“### 第1章...”）的章节信息，请检查大纲格式。")

    def _parse_target_chapters_from_feedback(self, feedback: str, max_chapter: int):
        fb = (feedback or "").strip()
        if not fb:
            return []
        max_ch = int(max_chapter or 0)
        if max_ch <= 0:
            max_ch = 1000

        found = set()

        for m in re.finditer(r"(?:第\s*)?(\d+)\s*(?:章)?\s*(?:[-~—－到至]\s*)(?:第\s*)?(\d+)\s*章", fb):
            try:
                a = int(m.group(1))
                b = int(m.group(2))
            except Exception:
                continue
            if a > b:
                a, b = b, a
            a = max(1, a)
            b = min(max_ch, b)
            for x in range(a, b + 1):
                found.add(x)

        for m in re.finditer(r"第\s*(\d+)\s*章", fb):
            try:
                x = int(m.group(1))
            except Exception:
                continue
            if 1 <= x <= max_ch:
                found.add(x)

        if not found:
            for m in re.finditer(r"(?<!\d)(\d{1,4})\s*章", fb):
                try:
                    x = int(m.group(1))
                except Exception:
                    continue
                if 1 <= x <= max_ch:
                    found.add(x)

        return sorted(found)

    def _generate_json_for_outline_edit(self, provider, api_key, model_name, novel_type, theme, contents_text, user_prompt, schema):
        system_text = (
            build_system_instruction()
            + "\n"
            + build_constraints(novel_type, theme, self.channel_var.get())
            + "\n你正在根据修改意见对既有大纲做定向修订。必须承接原大纲设定与线索链，只改动被要求修改的章节，不要重写整本。严格输出 JSON。"
        )

        if provider in ("Doubao", "Claude"):
            base_url = self._load_doubao_base_url() if provider == "Doubao" else ""
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                prompt = (
                    f"【上下文参考】\n{ctx}\n"
                    f"----------------\n"
                    f"{user_prompt}\n\n"
                    f"请务必严格输出合法的 JSON，不要包含 Markdown 代码块标记。"
                )
                try:
                    if provider == "Claude":
                        text_out = self._call_claude(api_key, model_name, system_text, prompt, temperature=0.35, max_tokens=4096)
                    else:
                        text_out = self._call_compat_chat(api_key, model_name, system_text, prompt, temperature=0.35, base_url=base_url)
                except Exception:
                    text_out = ""
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fix_prompt = f"上一次输出的 JSON 格式有误，请修正为合法的 JSON，且严格匹配 schema：\n{json.dumps(schema, ensure_ascii=False)}\n\n原输出：\n{text_out}"
                    try:
                        if provider == "Claude":
                            fixed = self._call_claude(api_key, model_name, system_text, fix_prompt, temperature=0.1, max_tokens=4096)
                        else:
                            fixed = self._call_compat_chat(api_key, model_name, system_text, fix_prompt, temperature=0.1, base_url=base_url)
                    except Exception:
                        fixed = ""
                    json_data = self._parse_json(fixed)
                    if json_data is not None:
                        return json_data
            return None

        client = genai.Client(api_key=api_key)
        base_models = [model_name]
        if "gemini" in model_name.lower() and model_name != "gemini-2.5-pro":
            base_models.append("gemini-2.5-pro")
        if "gemini" in model_name.lower() and model_name != "gemini-2.0-flash":
            base_models.append("gemini-2.0-flash")

        for max_tokens in [2500, 1800, 1200]:
            config = types.GenerateContentConfig(
                system_instruction=[types.Part.from_text(text=system_text)],
                temperature=0.45,
                max_output_tokens=max_tokens,
                top_p=0.95,
            )
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=user_prompt),
                            types.Part.from_text(text=f"\n\n【上下文参考】\n{ctx}\n"),
                        ],
                    )
                ]
                config_local = types.GenerateContentConfig(
                    system_instruction=config.system_instruction,
                    temperature=config.temperature,
                    max_output_tokens=config.max_output_tokens,
                    top_p=config.top_p,
                    response_mime_type="application/json",
                    response_schema=schema,
                )
                text_out = self._generate_with_fallback(client, base_models, contents, config_local, max_request_retries=4, max_empty_retries=10)
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fixed_json_text = self._correct_section_json(client, base_models, "修订", text_out, user_prompt, config_local, schema)
                    json_data = self._parse_json(fixed_json_text)
                    if json_data is not None:
                        return json_data

        return None

    def _generate_json_for_outline_audit(self, provider, api_key, model_name, novel_type, theme, contents_text, user_prompt, schema):
        system_text = (
            "你是资深网文主编与结构编辑，擅长大纲体检与可执行修改建议。"
            "你的任务是审阅用户提供的小说大纲，指出结构/逻辑/爽点节奏/伏笔钩子/人物动机的关键问题，并给出可以直接执行的修改意见。"
            "\n"
            + build_constraints(novel_type, theme, self.channel_var.get())
            + "\n必须承接原大纲设定与命名；除非建议明确要求，否则不要推翻重写。严格输出 JSON。"
        )

        if provider in ("Doubao", "Claude"):
            base_url = self._load_doubao_base_url() if provider == "Doubao" else ""
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                prompt = (
                    f"【大纲内容】\n{ctx}\n"
                    f"----------------\n"
                    f"{user_prompt}\n\n"
                    f"请务必严格输出合法的 JSON，不要包含 Markdown 代码块标记。"
                )
                try:
                    if provider == "Claude":
                        text_out = self._call_claude(api_key, model_name, system_text, prompt, temperature=0.35, max_tokens=4096)
                    else:
                        text_out = self._call_compat_chat(api_key, model_name, system_text, prompt, temperature=0.35, base_url=base_url)
                except Exception:
                    text_out = ""
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fix_prompt = f"上一次输出的 JSON 格式有误，请修正为合法的 JSON，且严格匹配 schema：\n{json.dumps(schema, ensure_ascii=False)}\n\n原输出：\n{text_out}"
                    try:
                        if provider == "Claude":
                            fixed = self._call_claude(api_key, model_name, system_text, fix_prompt, temperature=0.1, max_tokens=4096)
                        else:
                            fixed = self._call_compat_chat(api_key, model_name, system_text, fix_prompt, temperature=0.1, base_url=base_url)
                    except Exception:
                        fixed = ""
                    json_data = self._parse_json(fixed)
                    if json_data is not None:
                        return json_data
            return None

        client = genai.Client(api_key=api_key)
        base_models = [model_name]
        if "gemini" in model_name.lower() and model_name != "gemini-2.5-pro":
            base_models.append("gemini-2.5-pro")
        if "gemini" in model_name.lower() and model_name != "gemini-2.0-flash":
            base_models.append("gemini-2.0-flash")

        for max_tokens in [2500, 1800, 1200]:
            config = types.GenerateContentConfig(
                system_instruction=[types.Part.from_text(text=system_text)],
                temperature=0.45,
                max_output_tokens=max_tokens,
                top_p=0.95,
            )
            for ctx_limit in [20000, 12000, 6000, 2000, 0]:
                ctx = contents_text[-ctx_limit:] if ctx_limit and isinstance(contents_text, str) else ""
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=user_prompt),
                            types.Part.from_text(text=f"\n\n【大纲内容】\n{ctx}\n"),
                        ],
                    )
                ]
                config_local = types.GenerateContentConfig(
                    system_instruction=config.system_instruction,
                    temperature=config.temperature,
                    max_output_tokens=config.max_output_tokens,
                    top_p=config.top_p,
                    response_mime_type="application/json",
                    response_schema=schema,
                )
                text_out = self._generate_with_fallback(client, base_models, contents, config_local, max_request_retries=4, max_empty_retries=10)
                json_data = self._parse_json(text_out)
                if json_data is not None:
                    return json_data
                if text_out:
                    fixed_json_text = self._correct_section_json(client, base_models, "体检", text_out, user_prompt, config_local, schema)
                    json_data = self._parse_json(fixed_json_text)
                    if json_data is not None:
                        return json_data

        return None

    def _apply_updated_chapters_to_outline_text(self, outline_text: str, chapters: dict):
        base = (outline_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not isinstance(chapters, dict) or not chapters:
            return base.strip()

        ordered_nums = sorted([int(k) for k in chapters.keys() if str(k).isdigit()])
        if not ordered_nums:
            return base.strip()

        ordered_items = [chapters[n] for n in ordered_nums if n in chapters]
        new_block = self._format_from_data(f"章节大纲 第1-{ordered_nums[-1]}章", ordered_items)
        if not new_block:
            return base.strip()

        matches = list(re.finditer(r"(?:^|\n)\s*###\s*第\s*(\d+)\s*章[\s\S]*?(?=(?:\n\s*###\s*第\s*\d+\s*章)|\Z)", base))
        if matches:
            start = matches[0].start()
            end = matches[-1].end()
            return (base[:start].rstrip() + "\n\n" + new_block.strip() + "\n" + base[end:].lstrip()).strip()

        matches2 = list(re.finditer(r"(?:^|\n)\s*第\s*\d+\s*章[\s\S]*?(?=(?:\n\s*第\s*\d+\s*章)|\Z)", base))
        if matches2:
            start = matches2[0].start()
            end = matches2[-1].end()
            return (base[:start].rstrip() + "\n\n" + new_block.strip() + "\n" + base[end:].lstrip()).strip()

        return (base.strip() + "\n\n" + new_block.strip()).strip()

    def _run_apply_feedback_to_chapters(self, provider, api_key, model_name, novel_type, theme, base_outline: str, feedback: str):
        try:
            existing = self._parse_chapters_from_outline_text(base_outline) or {}
            if not isinstance(existing, dict) or not existing:
                existing = {int(it.get("chapter")): it for it in (self.chapters_data or []) if isinstance(it, dict) and it.get("chapter") is not None}

            max_ch = 0
            try:
                max_ch = max(int(k) for k in existing.keys())
            except Exception:
                max_ch = 0

            targets = self._parse_target_chapters_from_feedback(feedback, max_ch)
            if not targets:
                brief = []
                for it in (self.chapters_data or []):
                    if not isinstance(it, dict) or it.get("chapter") is None:
                        continue
                    cn = it.get("chapter")
                    tt = (it.get("title") or "").strip()
                    ss = (it.get("summary") or "").strip().replace("\n", " ")
                    brief.append(f"第{cn}章 {tt}：{ss[:60]}")
                brief_text = "\n".join(brief[:400])
                schema = {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "required": ["chapter"],
                        "properties": {"chapter": {"type": "STRING"}},
                    },
                }
                prompt = (
                    "任务：根据【修改意见】，判断需要改动的章节编号列表（只输出 JSON 数组）。\n"
                    "要求：\n"
                    "1. 只选择确实需要改动的章节；不要超过 30 个。\n"
                    "2. 输出格式为：[ {\"chapter\":\"12\"}, ... ]。\n\n"
                    f"【修改意见】\n{feedback}\n\n"
                    f"【章节列表（标题+摘要片段）】\n{brief_text}\n"
                )
                picked = self._generate_json_for_outline_edit(provider, api_key, model_name, novel_type, theme, brief_text, prompt, schema)
                cand = []
                if isinstance(picked, list):
                    for x in picked:
                        if isinstance(x, dict) and x.get("chapter"):
                            try:
                                cand.append(int(str(x.get("chapter")).strip()))
                            except Exception:
                                continue
                cand = [c for c in cand if 1 <= c <= (max_ch or 1000)]
                targets = sorted(list(dict.fromkeys(cand)))[:30]

            if not targets:
                self.root.after(0, messagebox.showwarning, "提示", "未识别到需要修改的章节编号，请在修改意见中写明“第X章”或“X-Y章”。")
                return

            total = len(targets)
            done = 0
            self.total_sections = total
            self.completed_sections = 0
            self.root.after(0, lambda: self.progress_var.set(f"进度 {done}/{total}"))

            schema = {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "required": ["chapter", "title", "summary"],
                    "properties": {
                        "chapter": {"type": "STRING"},
                        "title": {"type": "STRING"},
                        "summary": {"type": "STRING"},
                    },
                },
            }

            batch_size = 8 if provider == "Doubao" else 12
            for i in range(0, len(targets), batch_size):
                if self._cancel_event.is_set():
                    break
                cur = targets[i:i + batch_size]
                if not cur:
                    break
                a = min(cur)
                b = max(cur)
                ctx = self._build_chapter_range_context(base_outline, existing, a, b)
                items = []
                for cn in cur:
                    it = existing.get(cn, {"chapter": cn, "title": "", "summary": ""})
                    items.append(
                        {
                            "chapter": cn,
                            "title": (it.get("title") or "").strip(),
                            "summary": (it.get("summary") or "").strip(),
                        }
                    )

                user_prompt = (
                    "任务：根据【修改意见】，定向修改【待改章节】的章节标题与梗概（可只改梗概）。\n"
                    "要求：\n"
                    "1. 必须承接上下文与原设定，不得推翻重写整本。\n"
                    "2. 只输出被修改后的章节（不要输出未要求修改的章节）。\n"
                    "3. 每个章节输出字段：chapter/title/summary。\n"
                    "4. summary 建议包含“内容/悬疑点/爽点”结构，但不强制。\n"
                    "5. 严禁输出任何解释性文字，必须输出 JSON。\n\n"
                    f"【修改意见】\n{feedback}\n\n"
                    f"【待改章节（原始）】\n{json.dumps(items, ensure_ascii=False)}\n"
                )

                patched = self._generate_json_for_outline_edit(provider, api_key, model_name, novel_type, theme, ctx, user_prompt, schema)
                if isinstance(patched, list):
                    for it in patched:
                        if not isinstance(it, dict):
                            continue
                        chap_raw = it.get("chapter")
                        if chap_raw is None:
                            continue
                        try:
                            cn = int(str(chap_raw).strip())
                        except Exception:
                            continue
                        if cn not in cur:
                            continue
                        title = (it.get("title") or "").strip()
                        summary = (it.get("summary") or "").strip()
                        if not summary:
                            continue
                        existing[cn] = {"chapter": cn, "title": title, "summary": summary}

                done = min(total, done + len(cur))
                self.root.after(0, lambda d=done, t=total: self.progress_var.set(f"进度 {d}/{t}"))
                self.root.after(0, self._append_text, f"[系统] 已修改章节：{a}-{b}\n")

            new_text = self._apply_updated_chapters_to_outline_text(base_outline, existing)
            self.full_outline_context = new_text.strip()
            ordered_nums = sorted([int(k) for k in existing.keys() if str(k).isdigit()])
            ordered_items = [existing[n] for n in ordered_nums if n in existing]
            self.chapters_data = ordered_items
            self.all_chapter_summaries = [
                f"第{it.get('chapter')}章：{(it.get('summary') or '').strip()[:50]}..."
                for it in ordered_items
                if isinstance(it, dict)
            ]

            self.root.after(0, lambda: self.output.delete("1.0", tk.END))
            self.root.after(0, self._append_text, self.full_outline_context + "\n")
            self.root.after(0, messagebox.showinfo, "完成", "已按修改意见修改对应章节，可直接保存/导出。")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "修改失败", err_msg)
            if self.logger:
                self.logger.error(f"按修改意见修改章节失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _run_check_outline_suggestions(self, provider, api_key, model_name, novel_type, theme, outline_text: str):
        try:
            text = (outline_text or "").strip()
            if not text:
                self.root.after(0, messagebox.showwarning, "提示", "大纲为空，无法检查")
                return

            chapters = self._parse_chapters_from_outline_text(text) or {}
            max_ch = 0
            try:
                max_ch = max(int(k) for k in chapters.keys())
            except Exception:
                max_ch = 0

            schema = {
                "type": "OBJECT",
                "required": ["feedback", "report"],
                "properties": {
                    "feedback": {"type": "STRING"},
                    "report": {"type": "STRING"},
                },
            }

            prompt = (
                "任务：对这份小说大纲做“体检”，并输出两份内容：\n"
                "A) report：详细体检报告（按模块分段，指出问题与原因）。\n"
                "B) feedback：可以直接粘贴到“修改意见”输入框的可执行修改清单。\n\n"
                "feedback 输出要求：\n"
                "1. 每条必须明确指向范围（例如“第12章”“第12-15章”“第60章结尾”等）。\n"
                "2. 每条只写“要改什么 + 改到什么效果”，不要写分析过程。\n"
                "3. 总条数 8-20 条，优先挑影响最大的。\n"
                "4. 若需要新增章节或拆分合并，也要写清楚新增到哪几章。\n\n"
                f"补充信息：大纲章节最大编号约为 {max_ch or '未知'}。\n"
            )

            data = self._generate_json_for_outline_audit(provider, api_key, model_name, novel_type, theme, text, prompt, schema)
            if not isinstance(data, dict):
                self.root.after(0, messagebox.showerror, "检查失败", "模型未返回可解析的结构化结果")
                return

            def to_text(v):
                if v is None:
                    return ""
                if isinstance(v, str):
                    return v
                if isinstance(v, list):
                    parts = []
                    for x in v:
                        if x is None:
                            continue
                        if isinstance(x, str):
                            s = x
                        elif isinstance(x, dict):
                            try:
                                s = json.dumps(x, ensure_ascii=False)
                            except Exception:
                                s = str(x)
                        else:
                            s = str(x)
                        if s:
                            parts.append(s)
                    return "\n".join(parts)
                if isinstance(v, dict):
                    try:
                        return json.dumps(v, ensure_ascii=False)
                    except Exception:
                        return str(v)
                return str(v)

            feedback = to_text(data.get("feedback")).strip()
            report = to_text(data.get("report")).strip()
            if not feedback and not report:
                self.root.after(0, messagebox.showerror, "检查失败", "模型返回了空内容")
                return

            def fill_feedback():
                try:
                    self.feedback_text.delete("1.0", tk.END)
                    if feedback:
                        self.feedback_text.insert(tk.END, feedback + "\n")
                except Exception:
                    pass

            self.root.after(0, fill_feedback)

            out = []
            if report:
                out.append("### 大纲体检报告\n" + report.strip())
            if feedback:
                out.append("\n### 自动生成的修改意见（已填入输入框）\n" + feedback.strip())
            final = "\n\n".join([x for x in out if x]).strip()
            if final:
                self.root.after(0, self._append_text, final + "\n")
            self.root.after(0, messagebox.showinfo, "完成", "大纲检查完成，修改意见已自动填充")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "检查失败", err_msg)
            if self.logger:
                self.logger.error(f"大纲检查失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def on_polish(self):
        if not self._require_login_and_token():
            return
        content = self.output.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("无内容", "当前没有可润色的内容")
            return
            
        # 强制使用 Gemini 进行润色
        api_key = self._load_api_key("Gemini")
        if not api_key:
            messagebox.showerror("错误", "未配置 Gemini API Key，无法使用 Gemini 进行润色")
            return
            
        self.status_var.set("正在使用 Gemini 3 Pro 润色大纲...")
        self.generate_btn.config(state=tk.DISABLED)
        if hasattr(self, "regen_btn"):
            self.regen_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        self.export_zip_btn.config(state=tk.DISABLED)
        self.generate_novel_btn.config(state=tk.DISABLED)
        if hasattr(self, "generate_novel_zip_btn"):
            self.generate_novel_zip_btn.config(state=tk.DISABLED)
        self.parse_btn.config(state=tk.DISABLED)
        self.polish_btn.config(state=tk.DISABLED)
        self._cancel_event.clear()
        self.stop_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=self._run_polish, args=(api_key, content), daemon=True).start()

    def _run_polish(self, api_key, content):
        try:
            if self.logger:
                self.logger.info("开始大纲润色 (Gemini)")
                
            client = genai.Client(api_key=api_key)
            model = "gemini-3-pro-preview" # 指定使用 Gemini 3 Pro Preview
            
            prompt = (
                "你是资深网文主编。请对以下小说大纲进行深度润色与优化。\n"
                "任务要求：\n"
                "1. 【保留结构】必须严格保留原有的结构层次（如“作品名”、“核心人设”、“章节大纲”等），特别是“章节大纲”部分的“第X章”格式不能乱，以便后续程序解析。\n"
                "2. 【提升文笔】优化语言表达，使其更具感染力、画面感和网文爽感。\n"
                "3. 【强化逻辑】检查并修复剧情逻辑漏洞，增强冲突的合理性和张力。\n"
                "4. 【丰富细节】对简略的设定或梗概进行适当扩充，增加看点。\n"
                "5. 直接输出润色后的大纲内容，不要包含任何解释性前言或后语。\n\n"
                "【待润色大纲】：\n"
                f"{content}"
            )
            
            config = types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8000,
                top_p=0.95,
            )
            
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
            
            # 使用带重试的调用
            polished_text = self._generate_with_fallback(client, [model, "gemini-2.5-pro"], contents, config)
            polished_text = self._sanitize_text(polished_text)
            
            if polished_text:
                # 更新 UI
                self.root.after(0, lambda: self.output.delete("1.0", tk.END))
                self.root.after(0, self._append_text, polished_text)
                
                # 自动重新解析以更新内部数据结构
                self.root.after(100, self.on_parse_outline) 
                
                if self.logger:
                    self.logger.info("大纲润色完成")
            else:
                self.root.after(0, messagebox.showwarning, "润色失败", "模型返回了空内容")

        except Exception as e:
            err_msg = str(e)
            print(err_msg)
            self.root.after(0, messagebox.showerror, "润色失败", err_msg)
            if self.logger:
                self.logger.error(f"润色失败: {err_msg}")
        finally:
            self._reset_ui_state()

    def _reset_ui_state(self):
        self._pause_event.clear()
        self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.regen_btn.config(state=tk.NORMAL))
        if hasattr(self, "pause_btn"):
            self.root.after(0, lambda: self.pause_btn.config(state=tk.DISABLED, text="暂停"))
        self.root.after(0, lambda: self.status_var.set("就绪"))
        self.root.after(0, self._update_account_ui)

def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("800x520")
    root.resizable(False, False)

    try:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#F5F5F5")
        style.configure("TLabel", background="#F5F5F5", foreground="#000000")
        style.configure("TButton", foreground="#000000")
        style.configure("TEntry", foreground="#000000")
    except Exception:
        pass

    loading_text = tk.StringVar(value="正在加载登录界面…")
    try:
        loading = tk.Label(root, textvariable=loading_text, font=("Microsoft YaHei UI", 11))
        loading.pack(expand=True)
    except Exception:
        pass

    def _boot():
        try:
            show_auth_screen(root)
            try:
                root.update_idletasks()
            except Exception:
                pass

            def _ensure():
                try:
                    root.update_idletasks()
                    root.update()
                    if not root.winfo_children():
                        show_auth_screen(root)
                except Exception:
                    pass

            root.after(200, _ensure)
        except Exception as e:
            try:
                _clear_root(root)
            except Exception:
                pass
            try:
                messagebox.showerror("启动失败", str(e), parent=root)
            except Exception:
                try:
                    tk.Label(root, text=str(e), fg="red", wraplength=720, justify=tk.LEFT).pack(
                        padx=20, pady=20, fill=tk.BOTH, expand=True
                    )
                except Exception:
                    pass

    root.after(0, _boot)
    root.mainloop()

if __name__ == "__main__":
    main()
