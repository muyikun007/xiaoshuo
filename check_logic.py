import os
import json
import time
from google import genai
from google.genai import types

# Configuration
FILE_PATH = r"c:\Users\Administrator\Downloads\xiaoshuo\《扫黑：权路锋刃》.txt"
MODEL_NAME = "gemini-3-pro-preview"

def load_api_key():
    # 1. Try Env Var
    key = os.environ.get("GEMINI_API_KEY")
    if key: return key
    
    # 2. Try config.json in current dir
    try:
        if os.path.exists("config.json"):
            with open("config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("api_key")
    except:
        pass
        
    # 3. Try config.json in script dir
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(script_dir, "config.json")
        if os.path.exists(cfg_path):
             with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("api_key")
    except:
        pass
    return None

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def check_logic(client, text):
    prompt = (
        "你是资深网文主编和逻辑分析师。请仔细阅读以下小说大纲，并进行深度逻辑审查。\n"
        "【审查重点】\n"
        "1. **因果逻辑**：剧情发展是否符合因果律？是否有强行降智或机械降神的情节？\n"
        "2. **人物动机**：角色的行为是否符合其既定人设（性格、欲望、弱点）？是否存在OOC（角色崩坏）现象？\n"
        "3. **势力平衡**：主角的晋升速度是否合理？反派的智商和手段是否在线？是否存在战力崩坏？\n"
        "4. **时间线与细节**：是否存在时间线冲突或关键细节遗漏？\n"
        "5. **爽点节奏**：爽点铺垫是否足够？是否有期待感落空的情况？\n\n"
        "【输出要求】\n"
        "请输出一份《大纲逻辑诊断报告》，包含以下部分：\n"
        "- **整体评价**：简要评价大纲的逻辑严密性。\n"
        "- **核心问题列表**：列出发现的具体逻辑漏洞（按严重程度排序），每条需指出章节号或情节段落，并说明问题所在。\n"
        "- **修改建议**：针对每个问题给出具体的修正方案。\n"
        "- **亮点分析**：简要提及逻辑闭环做得好的地方。\n\n"
        "【小说大纲内容】\n"
        f"{text}\n\n"
        "请开始你的诊断："
    )
    
    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=8000,
        top_p=0.95
    )
    
    try:
        print("Sending request to Gemini (this may take a minute)...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=config
        )
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: API Key not found.")
        return

    if not os.path.exists(FILE_PATH):
        print(f"Error: File not found: {FILE_PATH}")
        return

    print(f"Reading {FILE_PATH}...")
    text = read_file(FILE_PATH)
    print(f"File size: {len(text)} characters.")
    
    client = genai.Client(api_key=api_key)
    
    report = check_logic(client, text)
    print("\n" + "="*20 + " LOGIC CHECK REPORT " + "="*20 + "\n")
    print(report)
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
