
import os

file_path = r"c:\Users\Administrator\Downloads\xiaoshuo\北海沉锚\北海沉锚-小说大纲.md"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replacements
content = content.replace("何强一", "秦渊")
content = content.replace("何萧", "秦渊")
content = content.replace("女主", "男主")
content = content.replace("她", "他") # Global gender swap to Male

# Fix specific context if needed
# content = content.replace("华哲言", "华哲言") # Name stays

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated novel outline.")
