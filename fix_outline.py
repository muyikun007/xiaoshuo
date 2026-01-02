import re
import os

FILE_PATH = r"c:\Users\Administrator\Downloads\xiaoshuo\《扫黑：权路锋刃》.txt"

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def parse_chapters(text):
    # Split by lines
    lines = text.splitlines()
    
    front_matter = []
    chapters = []
    
    current_chap = None
    
    # Regex for chapter header: 第123章 Title: Content...
    # Or just 第123章 Title
    chap_re = re.compile(r"^第\s*(\d+)\s*章\s*(.*)")
    
    # Regex for Volume header: 第X卷... (We want to preserve these but maybe regenerate them)
    # Actually, we can just treat Volume headers as part of the previous chapter's content 
    # OR better: separate them.
    # But swapping volumes means we need to move the volume headers too?
    # The user request specifically mentioned logic issues.
    # Let's extract chapters purely. Volume headers usually appear before a block of chapters.
    
    # Strategy:
    # 1. Capture front matter (everything before Ch 1).
    # 2. Capture each chapter.
    # 3. If a line looks like a Volume Header, store it as a special "marker" in the chapter list?
    #    No, Volume headers are distinct.
    
    # Let's use a list of segments.
    # Segment = {type: "front"|"chapter"|"volume_header", content: str, num: int (if chapter)}
    
    segments = []
    current_segment = {"type": "front", "content": []}
    
    for line in lines:
        match = chap_re.match(line)
        if match:
            # Save current segment
            segments.append(current_segment)
            
            # Start new chapter segment
            c_num = int(match.group(1))
            title_part = match.group(2)
            current_segment = {
                "type": "chapter",
                "num": c_num,
                "title_line": line, # We might reconstruct this
                "content": []
            }
        else:
            # Check for volume header
            if re.match(r"^第[一二三四五六七八九十]+卷", line):
                # Save current
                segments.append(current_segment)
                # Start volume segment
                current_segment = {
                    "type": "volume",
                    "content": [line]
                }
            else:
                current_segment["content"].append(line)
                
    segments.append(current_segment)
    
    # Clean up empty segments
    segments = [s for s in segments if s["content"] or s.get("title_line")]
    
    return segments

def fix_content(segments):
    # 1. Identify ranges
    # Vol 2: 61-120
    # Vol 3: 121-180
    
    seg_vol2 = []
    seg_vol3 = []
    seg_vol4 = [] # 181-240
    
    other_segments = []
    
    # We need to preserve the Volume Headers.
    # Typically:
    # [Vol 2 Header] -> [Ch 61] ... [Ch 120]
    # [Vol 3 Header] -> [Ch 121] ... [Ch 180]
    
    # Let's iterate and categorize
    new_segments = []
    
    # Find the indices for swapping
    # We want to swap the CONTENT of Vol 2 and Vol 3.
    # That includes the Volume Header (maybe? No, Vol 2 header should stay at pos 2, but content changes).
    # Actually, if we swap contents, the "Volume Title" in the header might not match the new content.
    # Vol 2 Title: "政道交锋" (Political Path)
    # Vol 3 Title: "深渊猎手" (Abyss Hunter)
    # If we swap chapters, we SHOULD swap the headers too, so the "Abyss Hunter" arc comes first.
    
    # So we act on blocks.
    # Block 2: Vol 2 Header + Ch 61-120
    # Block 3: Vol 3 Header + Ch 121-180
    
    block2 = []
    block3 = []
    
    # Helper to detect range
    def get_range(num):
        if 61 <= num <= 120: return 2
        if 121 <= num <= 180: return 3
        if 181 <= num <= 240: return 4
        return 0
        
    for seg in segments:
        if seg["type"] == "chapter":
            r = get_range(seg["num"])
            if r == 2: block2.append(seg)
            elif r == 3: block3.append(seg)
            else:
                if r == 4:
                    # Fix Lu Chen in Vol 4
                    fix_lu_chen(seg)
                other_segments.append(seg)
        elif seg["type"] == "volume":
            # Heuristic to assign volume header to block
            # Read the text to see which volume it is
            txt = "".join(seg["content"])
            if "第二卷" in txt or "第2卷" in txt:
                block2.insert(0, seg)
            elif "第三卷" in txt or "第3卷" in txt:
                block3.insert(0, seg)
            else:
                other_segments.append(seg)
        else:
            other_segments.append(seg)
            
    # Now Swap Block 2 and Block 3 in the main list?
    # No, we need to reconstruct the linear order.
    # The original order was: [Front] ... [Block 2] ... [Block 3] ... [Rest]
    # We want: [Front] ... [Block 3 (Renumbered)] ... [Block 2 (Renumbered)] ... [Rest]
    
    # But wait, `other_segments` now loses its position relative to blocks.
    # We need to rebuild the list in place.
    
    final_list = []
    
    # Re-iterate original list to find insertion points is hard because we split them.
    # Let's assume standard structure: Front -> Vol 1 -> Vol 2 -> Vol 3 -> Vol 4 -> Vol 5
    
    # Let's filter `segments` directly.
    
    # Extract blocks by index to preserve order of others
    indices_2 = []
    indices_3 = []
    
    for i, seg in enumerate(segments):
        if seg["type"] == "chapter":
            if 61 <= seg["num"] <= 120: indices_2.append(i)
            elif 121 <= seg["num"] <= 180: indices_3.append(i)
        elif seg["type"] == "volume":
            txt = "".join(seg["content"])
            if "第二卷" in txt: indices_2.append(i)
            elif "第三卷" in txt: indices_3.append(i)
            
    # Check if we found contiguous blocks
    if not indices_2 or not indices_3:
        print("Could not find Volume 2 or 3 chapters/headers clearly. Skipping swap.")
        return segments # Fail safe
        
    min_2, max_2 = min(indices_2), max(indices_2)
    min_3, max_3 = min(indices_3), max(indices_3)
    
    # Extract elements
    # Note: Volume headers might be mixed if logic above failed, but let's trust the logic.
    
    block_2_objs = [segments[i] for i in sorted(indices_2)]
    block_3_objs = [segments[i] for i in sorted(indices_3)]
    
    # Renumber Block 3 to be 61-120
    # Block 3 has 60 chapters?
    # Let's count chapters in block 3
    chaps_3 = [s for s in block_3_objs if s["type"] == "chapter"]
    for i, chap in enumerate(chaps_3):
        new_num = 61 + i
        chap["num"] = new_num
        # Update title line
        # Regex replace number
        chap["title_line"] = re.sub(r"第\s*\d+\s*章", f"第{new_num}章", chap["title_line"])
        
    # Renumber Block 2 to be 121-180
    chaps_2 = [s for s in block_2_objs if s["type"] == "chapter"]
    start_num_2 = 61 + len(chaps_3) # Should be 121 usually
    for i, chap in enumerate(chaps_2):
        new_num = start_num_2 + i
        chap["num"] = new_num
        chap["title_line"] = re.sub(r"第\s*\d+\s*章", f"第{new_num}章", chap["title_line"])
        
    # Fix Lu Chen in Vol 4 (which is in `segments` but not in these blocks)
    for seg in segments:
        if seg["type"] == "chapter" and 181 <= seg["num"] <= 240:
             fix_lu_chen(seg)
             
    # Global Anachronism Fix (apply to all content)
    for seg in segments:
        fix_anachronisms(seg)
        
    # Reconstruct list
    # We replace the range [min_2, max_2] with block_3_objs
    # And [min_3, max_3] with block_2_objs
    # But wait, if min_3 > max_2, the indices shift?
    # Actually, we can just build a new list.
    
    # Assumption: The segments list is ordered.
    # 0...min_2-1 : Keep
    # min_2...max_2 : Replace with Block 3
    # max_2+1...min_3-1 : Keep
    # min_3...max_3 : Replace with Block 2
    # max_3+1... : Keep
    
    # Update Volume Headers Numbers
    # Block 3 (now at pos 2) header should say "第二卷"
    for seg in block_3_objs:
        if seg["type"] == "volume":
             seg["content"] = [re.sub(r"第三卷", "第二卷", l) for l in seg["content"]]
             seg["content"] = [re.sub(r"第121-180章", "第61-120章", l) for l in seg["content"]]

    for seg in block_2_objs:
        if seg["type"] == "volume":
             seg["content"] = [re.sub(r"第二卷", "第三卷", l) for l in seg["content"]]
             seg["content"] = [re.sub(r"第61-120章", "第121-180章", l) for l in seg["content"]]

    out = []
    for i in range(len(segments)):
        if i == min_2:
            out.extend(block_3_objs)
        elif i == min_3:
            out.extend(block_2_objs)
        elif (min_2 < i <= max_2) or (min_3 < i <= max_3):
            continue
        else:
            out.append(segments[i])
            
    return out

def fix_lu_chen(seg):
    # Replace "陆沉" -> "王卫国"
    # Replace "陆市长" -> "王市长"
    # Be careful with context.
    
    def repl(text):
        t = text.replace("陆沉", "王卫国")
        t = t.replace("陆市长", "王市长")
        # Fix possible artifacts "王卫国(formerly Lu Chen)" if we did that, but we are doing straight replace
        return t
        
    seg["title_line"] = repl(seg["title_line"])
    seg["content"] = [repl(l) for l in seg["content"]]

def fix_anachronisms(seg):
    def repl(text):
        t = text.replace("元宇宙", "区块链")
        t = t.replace("Metaverse", "Blockchain")
        return t
    
    if seg.get("title_line"):
        seg["title_line"] = repl(seg["title_line"])
    seg["content"] = [repl(l) for l in seg["content"]]

def segments_to_text(segments):
    lines = []
    for seg in segments:
        if seg["type"] == "chapter":
            lines.append(seg["title_line"])
        lines.extend(seg["content"])
    return "\n".join(lines)

def main():
    print(f"Reading {FILE_PATH}...")
    text = read_file(FILE_PATH)
    
    print("Parsing chapters...")
    segments = parse_chapters(text)
    print(f"Total segments: {len(segments)}")
    
    print("Applying fixes (Swap Vol 2/3, Fix Lu Chen, Fix Anachronisms)...")
    new_segments = fix_content(segments)
    
    print("Reconstructing text...")
    new_text = segments_to_text(new_segments)
    
    backup = FILE_PATH.replace(".txt", "_before_fix.txt")
    write_file(backup, text)
    print(f"Backup saved to {backup}")
    
    write_file(FILE_PATH, new_text)
    print(f"Fixed outline saved to {FILE_PATH}")

if __name__ == "__main__":
    main()
