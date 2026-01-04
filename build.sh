#!/bin/bash
# 小说大纲生成器 - 打包脚本
# 用途：自动化打包流程，生成单文件可执行程序

set -e  # 遇到错误立即退出

echo "========================================"
echo "  小说大纲生成器 - 自动打包脚本"
echo "========================================"
echo ""

# 检查 Python 版本
echo "[1/6] 检查 Python 环境..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 版本: $python_version"
echo ""

# 检查并安装依赖
echo "[2/6] 检查项目依赖..."
if [ -f requirements.txt ]; then
    echo "安装项目依赖..."
    pip install -r requirements.txt -q
    echo "✓ 项目依赖已安装"
else
    echo "⚠ 警告: requirements.txt 未找到"
fi
echo ""

# 检查并安装 PyInstaller
echo "[3/6] 检查 PyInstaller..."
if ! pip show pyinstaller > /dev/null 2>&1; then
    echo "安装 PyInstaller..."
    pip install pyinstaller -q
    echo "✓ PyInstaller 已安装"
else
    pyinstaller_version=$(pip show pyinstaller | grep Version | awk '{print $2}')
    echo "✓ PyInstaller 已安装 (版本: $pyinstaller_version)"
fi
echo ""

# 清理旧的打包文件
echo "[4/6] 清理旧的打包文件..."
if [ -d "build" ]; then
    rm -rf build
    echo "✓ 清理 build 目录"
fi
if [ -d "dist" ]; then
    rm -rf dist
    echo "✓ 清理 dist 目录"
fi
echo ""

# 执行打包
echo "[5/6] 开始打包..."
echo "使用配置文件: outline_app_onefile.spec"
pyinstaller outline_app_onefile.spec --clean

if [ $? -eq 0 ]; then
    echo "✓ 打包成功！"
else
    echo "✗ 打包失败！"
    exit 1
fi
echo ""

# 显示结果
echo "[6/6] 打包结果："
if [ -d "dist" ]; then
    echo "----------------------------------------"
    ls -lh dist/
    echo "----------------------------------------"

    file_size=$(du -h dist/小说大纲生成器 2>/dev/null | awk '{print $1}' || echo "未知")
    echo ""
    echo "✓ 可执行文件: dist/小说大纲生成器"
    echo "✓ 文件大小: $file_size"
    echo ""

    # 显示警告文件
    if [ -f "build/outline_app_onefile/warn-outline_app_onefile.txt" ]; then
        warning_count=$(grep -c "^missing module" build/outline_app_onefile/warn-outline_app_onefile.txt 2>/dev/null || echo 0)
        echo "⚠ 打包警告: $warning_count 个缺失模块（大多数是可选的）"
        echo "  详细信息见: build/outline_app_onefile/warn-outline_app_onefile.txt"
    fi
else
    echo "✗ 未找到 dist 目录"
    exit 1
fi

echo ""
echo "========================================"
echo "  打包完成！"
echo "========================================"
echo ""
echo "下一步："
echo "1. 在 dist/ 目录旁创建 config.json 配置文件"
echo "2. 参考 config.example.json 填写 API 密钥"
echo "3. 运行: ./dist/小说大纲生成器"
echo ""
echo "详细说明请查看: BUILD_GUIDE.md 和 用户配置指南.txt"
echo ""
