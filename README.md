# 小说大纲生成器 (Xiaoshuo)

基于 Google Gemini AI 的中文网络小说大纲生成工具，支持桌面 GUI 应用和 Web 应用。

## 项目特点

- 🤖 **AI 驱动**: 使用 Google Gemini API 生成高质量小说大纲
- 🖥️ **多平台**: 支持桌面 GUI、Web 应用、FastAPI 服务
- 📝 **完整大纲**: 生成包含人物设定、世界观、章节大纲的完整小说框架
- 💰 **积分系统**: 内置 MySQL 用户积分管理系统
- 🎨 **现代界面**: 使用 ttkbootstrap 提供现代化 GUI 体验
- 📦 **单文件部署**: 可打包为独立可执行文件，无需 Python 环境

## 快速开始

### 方式 1: 使用可执行文件（推荐）

**下载并运行打包好的可执行文件**：

1. 下载 `小说大纲生成器.exe` (Windows) 或 `小说大纲生成器` (Linux/Mac)
2. 在同一目录创建 `config.json` 配置文件（参考 `config.example.json`）
3. 填写 Gemini API 密钥和数据库配置
4. 双击运行（Windows）或 `./小说大纲生成器` (Linux/Mac)

详细说明请查看: [用户配置指南.txt](用户配置指南.txt)

### 方式 2: 从源码运行

```bash
# 克隆仓库
git clone <repository-url>
cd xiaoshuo

# 安装依赖
pip install -r requirements.txt

# 创建配置文件
cp config.example.json config.json
# 编辑 config.json 填写 API 密钥

# 运行桌面应用
python app.py

# 或运行 Web 应用
cd web_app
python app.py
```

## 打包部署

### 打包成可执行文件

**一键打包**：

```bash
# Linux/Mac
./build.sh

# Windows
build.bat
```

**手动打包**：

```bash
pip install pyinstaller
pyinstaller outline_app_onefile.spec --clean
```

详细说明请查看:
- [PACKAGING_README.md](PACKAGING_README.md) - 快速打包指南
- [BUILD_GUIDE.md](BUILD_GUIDE.md) - 详细打包和部署文档

## 配置说明

### 最小配置

创建 `config.json` 文件：

```json
{
  "api_key": "YOUR_GEMINI_API_KEY",
  "gemini_api_key": "YOUR_GEMINI_API_KEY",

  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "xiaoshuo_user",
    "password": "your_password",
    "database": "xiaoshuo",
    "charset": "utf8mb4"
  }
}
```

### 获取 API 密钥

访问 [Google AI Studio](https://aistudio.google.com/app/apikey) 创建 Gemini API 密钥。

### 完整配置选项

参考 [config.example.json](config.example.json) 查看所有可用配置选项。

## 主要功能

### 桌面应用 (app.py)
- ✅ 用户登录/注册
- ✅ 积分管理系统
- ✅ 实时流式大纲生成
- ✅ 支持多种 AI 提供商（Gemini、Doubao、Claude）
- ✅ 大纲保存和导出
- ✅ MySQL 数据库集成

### Web 应用 - Flask 版 (web_app/)
- ✅ Web 界面用户管理
- ✅ 小说项目管理
- ✅ 章节内容生成
- ✅ 后台任务处理
- ✅ 响应式界面设计

### Web 应用 - FastAPI 版 (web/)
- ✅ 异步 API 服务
- ✅ SQLite 数据库
- ✅ 轻量级部署
- ✅ RESTful API

## 技术栈

- **后端**: Python 3.8+
- **GUI**: tkinter + ttkbootstrap
- **Web 框架**: Flask / FastAPI
- **数据库**: MySQL / SQLite
- **AI SDK**: google-genai
- **打包工具**: PyInstaller

## 项目结构

```
xiaoshuo/
├── app.py                      # 桌面 GUI 应用
├── config.example.json         # 配置文件示例
├── requirements.txt            # Python 依赖
│
├── build.sh / build.bat        # 打包脚本
├── outline_app_onefile.spec    # PyInstaller 配置
│
├── web/                        # FastAPI Web 应用
├── web_app/                    # Flask Web 应用
│
├── BUILD_GUIDE.md              # 详细打包指南
├── PACKAGING_README.md         # 快速打包参考
├── 用户配置指南.txt             # 用户配置说明
├── 使用说明.txt                 # 使用手册
└── CLAUDE.md                   # 完整项目文档
```

## 常见问题

### 配置相关

**Q: 如何获取 API 密钥？**
A: 访问 [Google AI Studio](https://aistudio.google.com/app/apikey) 免费获取 Gemini API 密钥。

**Q: 必须使用 MySQL 吗？**
A: 桌面应用需要 MySQL，Web 应用可以使用 SQLite。

**Q: 配置文件放在哪里？**
A: 放在可执行文件同一目录，或通过 `CONFIG_JSON_PATH` 环境变量指定路径。

### 打包相关

**Q: 打包后文件很大？**
A: 正常现象，单文件包含所有依赖库（20-30MB）。

**Q: Linux 打包能在 Windows 运行吗？**
A: 不能，需要在目标平台上打包。

**Q: Windows Defender 报毒？**
A: PyInstaller 打包程序常被误报，可以添加到排除列表。

### 运行相关

**Q: 提示"未配置 API Key"？**
A: 检查 `config.json` 是否在正确位置，且格式正确。

**Q: 数据库连接失败？**
A: 确保 MySQL 服务运行中，且配置文件中的凭据正确。

## 开发文档

- **CLAUDE.md**: 完整的项目架构、开发规范、AI 助手指南
- **BUILD_GUIDE.md**: 详细的打包和部署流程
- **WEB_FEATURES_README.md**: Web 应用功能说明

## 贡献指南

欢迎提交 Issue 和 Pull Request！

开发前请阅读 [CLAUDE.md](CLAUDE.md) 了解项目规范。

## 许可证

本项目仅供学习和个人使用。

## 技术支持

- 微信: dddjs003
- GitHub Issues: 欢迎提交问题和建议

---

**版本**: 1.0.2
**最后更新**: 2026-01-04
