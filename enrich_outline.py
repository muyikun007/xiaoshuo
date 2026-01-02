import os
import re
import json
import time
import sys
from google import genai
from google.genai import types

# Configuration
FILE_PATH = r"c:\Users\Administrator\Downloads\xiaoshuo\官场逆袭_20251229_105229_大纲.txt"
MODEL_NAME = "gemini-3-pro-preview"
BATCH_SIZE = 20

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

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def get_chapters_matches(text):
    # Regex to capture:
    # Group 1: Full Title Line (e.g. 第1章 标题)
    # Group 2: Chapter Number
    # Group 3: Title Only
    # Group 4: Content
    # Lookahead: Stop at next "第X章" OR "第X卷" OR End of String
    
    pattern = re.compile(
        r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|(?:\n\s*第\s*[一二三四五六七八九十0-9]+\s*卷)|$)"
    )
    return list(pattern.finditer(text))

def enrich_batch(client, front_matter_context, batch_items):
    # batch_items is list of dict: {num, title, content}
    
    # Construct input for AI
    items_str = json.dumps(batch_items, ensure_ascii=False, indent=2)
    
    prompt = (
        "你是资深网文主编。请对以下小说章节大纲进行深度润色与丰富。\n"
        "【任务目标】\n"
        "1. 为每个章节增加【爽点】、【悬疑】或【钩子】设计，使剧情更具吸引力。\n"
        "2. 扩充细节，增强画面感和冲突张力。字数适当增加（每章梗概扩充到100-200字左右）。\n"
        "3. 保持原有核心剧情不变，只是丰富和优化。\n"
        "4. 必须输出 JSON 数组，格式严格如下：\n"
        "[\n"
        "  {\"chapter\": 1, \"title\": \"章节标题\", \"summary\": \"润色后的内容...\"},\n"
        "  ...\n"
        "]\n\n"
        "【小说背景与设定（参考）】\n"
        f"{front_matter_context[-3000:]}\n\n"
        "【待润色章节数据】\n"
        f"{items_str}\n\n"
        "请直接输出 JSON 结果："
    )
    
    schema = {
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
    
    config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=8000,
        top_p=0.95,
        response_mime_type="application/json",
        response_schema=schema
    )
    
    # Retry logic
    for attempt in range(3):
        try:
            # Fallback models if main fails? No, just stick to gemini-3-pro-preview or gemini-2.0-flash
            models_to_try = [MODEL_NAME, "gemini-2.5-pro"]
            
            last_err = None
            for m in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=m,
                        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
                        config=config
                    )
                    
                    if not response.text:
                        continue
                        
                    data = json.loads(response.text)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "items" in data: # Handle wrapped
                        return data["items"]
                except Exception as e:
                    last_err = e
                    # print(f"Model {m} failed: {e}")
                    continue
            
            if last_err: raise last_err
            
        except Exception as e:
            print(f"Batch generation failed (attempt {attempt+1}): {e}")
            time.sleep(5)
            
    return None

def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: API Key not found.")
        return

    print(f"Reading {FILE_PATH}...")
    text = read_file(FILE_PATH)
    
    matches = get_chapters_matches(text)
    if not matches:
        print("No chapters found.")
        return
        
    print(f"Found {len(matches)} chapters.")
    
    # Extract Front Matter (everything before first chapter)
    first_match_start = matches[0].start()
    front_matter = text[:first_match_start]
    
    client = genai.Client(api_key=api_key)
    
    # Prepare for reconstruction
    # We will build a list of segments: [ (type, content) ]
    # type: 'static' or 'chapter'
    
    segments = []
    last_pos = 0
    
    # Identify all static segments first
    chapter_indices = [] # store indices in segments list that are chapters
    
    for m in matches:
        start, end = m.span()
        # Text before this chapter
        if start > last_pos:
            segments.append({"type": "static", "content": text[last_pos:start]})
            
        # The chapter itself (placeholder for now)
        segments.append({
            "type": "chapter", 
            "original_content": m.group(0),
            "num": int(m.group(2)),
            "title": m.group(3).strip(),
            "summary": m.group(4).strip()
        })
        chapter_indices.append(len(segments) - 1)
        
        last_pos = end
        
    # Text after last chapter
    if last_pos < len(text):
        segments.append({"type": "static", "content": text[last_pos:]})
        
    # Process batches
    total_chapters = len(chapter_indices)
    
    for i in range(0, total_chapters, BATCH_SIZE):
        batch_indices = chapter_indices[i:i+BATCH_SIZE]
        batch_items = []
        for idx in batch_indices:
            seg = segments[idx]
            batch_items.append({
                "chapter": seg["num"],
                "title": seg["title"],
                "summary": seg["summary"]
            })
            
        print(f"Enriching batch {i//BATCH_SIZE + 1}/{(total_chapters + BATCH_SIZE - 1)//BATCH_SIZE} (Chapters {batch_items[0]['chapter']}-{batch_items[-1]['chapter']})...")
        
        enriched_data = enrich_batch(client, front_matter, batch_items)
        
        if enriched_data:
            # Map back to segments
            # Create a lookup dict for this batch
            enriched_map = {item['chapter']: item for item in enriched_data if 'chapter' in item}
            
            for idx in batch_indices:
                seg = segments[idx]
                c_num = seg["num"]
                if c_num in enriched_map:
                    item = enriched_map[c_num]
                    new_title = item.get("title", seg["title"]).strip()
                    new_summary = item.get("summary", seg["summary"]).strip()
                    
                    # Format: 第X章 Title：Summary
                    # Ensure Title doesn't have "第X章" prefix
                    new_title = re.sub(r"^第\d+章\s*", "", new_title).strip()
                    
                    new_content = f"第{c_num}章 {new_title}：{new_summary}"
                    segments[idx]["new_content"] = new_content
                else:
                    print(f"Warning: Chapter {c_num} missing in response, keeping original.")
                    segments[idx]["new_content"] = segments[idx]["original_content"]
        else:
            print("Batch failed, keeping original.")
            for idx in batch_indices:
                segments[idx]["new_content"] = segments[idx]["original_content"]
                
        time.sleep(2) # Rate limit friendly
        
    # Reconstruct Text
    print("Reconstructing file...")
    final_text = ""
    for seg in segments:
        if seg["type"] == "static":
            final_text += seg["content"]
        else:
            final_text += seg.get("new_content", seg["original_content"])
            
    # Backup
    backup_path = FILE_PATH.replace(".txt", f"_backup_{int(time.time())}.txt")
    write_file(backup_path, text)
    print(f"Backup saved to {backup_path}")
    
    # Save
    write_file(FILE_PATH, final_text)
    print(f"Successfully saved enriched outline to {FILE_PATH}")

if __name__ == "__main__":
    main()
