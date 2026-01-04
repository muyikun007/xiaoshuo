@echo off
REM 小说大纲生成器 - Windows 打包脚本
REM 用途：自动化打包流程，生成单文件可执行程序

setlocal enabledelayedexpansion

echo ========================================
echo   小说大纲生成器 - 自动打包脚本
echo ========================================
echo.

REM 检查 Python 环境
echo [1/6] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo x Python 未安装或未添加到 PATH
    echo   请从 https://www.python.org/downloads/ 下载并安装 Python
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python 版本: %PYTHON_VERSION%
echo.

REM 检查并安装依赖
echo [2/6] 检查项目依赖...
if exist requirements.txt (
    echo 安装项目依赖...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo x 依赖安装失败
        pause
        exit /b 1
    )
    echo √ 项目依赖已安装
) else (
    echo - 警告: requirements.txt 未找到
)
echo.

REM 检查并安装 PyInstaller
echo [3/6] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller -q
    if errorlevel 1 (
        echo x PyInstaller 安装失败
        pause
        exit /b 1
    )
    echo √ PyInstaller 已安装
) else (
    echo √ PyInstaller 已安装
)
echo.

REM 清理旧的打包文件
echo [4/6] 清理旧的打包文件...
if exist build (
    rmdir /s /q build
    echo √ 清理 build 目录
)
if exist dist (
    rmdir /s /q dist
    echo √ 清理 dist 目录
)
echo.

REM 执行打包
echo [5/6] 开始打包...
echo 使用配置文件: outline_app_onefile.spec
pyinstaller outline_app_onefile.spec --clean

if errorlevel 1 (
    echo x 打包失败！
    pause
    exit /b 1
)
echo √ 打包成功！
echo.

REM 显示结果
echo [6/6] 打包结果：
if exist dist (
    echo ----------------------------------------
    dir /a dist
    echo ----------------------------------------
    echo.
    echo √ 可执行文件: dist\小说大纲生成器.exe
    echo.

    REM 显示警告
    if exist build\outline_app_onefile\warn-outline_app_onefile.txt (
        echo - 打包警告详见: build\outline_app_onefile\warn-outline_app_onefile.txt
    )
) else (
    echo x 未找到 dist 目录
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 下一步：
echo 1. 在 dist\ 目录旁创建 config.json 配置文件
echo 2. 参考 config.example.json 填写 API 密钥
echo 3. 双击运行: dist\小说大纲生成器.exe
echo.
echo 详细说明请查看: BUILD_GUIDE.md 和 用户配置指南.txt
echo.
pause
