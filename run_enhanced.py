#!/usr/bin/env python
"""
启动增强版Web应用的脚本
避免相对导入问题
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入增强版应用
from web_app.enhanced_app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 启动增强版 Web 应用")
    print("=" * 60)
    print("✅ 包含所有桌面端功能：")
    print("   - AI 智能生成完整大纲")
    print("   - 40+ 小说类型库")
    print("   - 多AI模型支持")
    print("   - 文本润色功能")
    print("   - ZIP导出功能")
    print("=" * 60)
    print("📍 访问地址: http://localhost:5000")
    print("=" * 60)

    app.run(debug=True, port=5000, host='0.0.0.0')
