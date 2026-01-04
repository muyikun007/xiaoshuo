# 快速打包指南

## 一键打包

### Linux/Mac
```bash
./build.sh
```

### Windows
```cmd
build.bat
```

## 手动打包

### 1. 安装依赖
```bash
pip install -r requirements.txt
pip install pyinstaller
```

### 2. 执行打包
```bash
pyinstaller outline_app_onefile.spec --clean
```

### 3. 获取结果
打包完成后，可执行文件位于：
- **Linux/Mac**: `dist/小说大纲生成器`
- **Windows**: `dist/小说大纲生成器.exe`

## 打包内容

打包后的单文件可执行程序包含：

- ✅ 主应用程序 (`app.py`)
- ✅ 所有 Python 依赖库
- ✅ 示例配置文件 (`config.example.json`)
- ✅ 使用说明 (`使用说明.txt`)
- ✅ 用户配置指南 (`用户配置指南.txt`)
- ✅ 微信支付二维码（如果存在）

## 用户使用方法

### 方式 1: 外部配置文件（推荐）

```
部署目录/
├── 小说大纲生成器.exe
└── config.json          <- 用户创建
```

1. 将可执行文件复制到任意目录
2. 在**同一目录**创建 `config.json`
3. 填写 API 密钥和数据库配置
4. 运行可执行文件

**config.json 示例**:
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

### 方式 2: 环境变量

```bash
# Linux/Mac
export GEMINI_API_KEY="your_api_key"
export CONFIG_JSON_PATH="/path/to/config.json"
./小说大纲生成器

# Windows
set GEMINI_API_KEY=your_api_key
set CONFIG_JSON_PATH=C:\path\to\config.json
小说大纲生成器.exe
```

## 配置文件查找顺序

应用程序会按以下顺序查找配置文件：

1. `CONFIG_JSON_PATH` 或 `OUTLINE_APP_CONFIG` 环境变量指定的路径
2. 可执行文件同目录的 `config.json` **(推荐)**
3. 当前工作目录的 `config.json`
4. 父目录的 `config.json`
5. 打包内嵌的配置文件（只读，作为模板）

## 文件大小

- **预期大小**: 20-30 MB（单文件包含所有依赖）
- **实际大小**: 取决于包含的库数量

## 常见问题

### Q: 打包后文件很大？
A: 这是正常的，因为包含了所有 Python 运行时和依赖库。可以使用 UPX 压缩（已在 spec 文件中启用）。

### Q: 打包时提示缺少模块？
A: 运行 `pip install -r requirements.txt` 安装所有依赖。

### Q: Windows Defender 报毒？
A: PyInstaller 打包的程序常被误报，这是正常现象。可以添加到排除列表或使用代码签名。

### Q: Linux 上打包后无法在 Windows 运行？
A: 需要在目标平台上打包。Linux 打包的程序只能在 Linux 运行，Windows 同理。

### Q: 打包后运行提示找不到配置？
A: 确保 `config.json` 在可执行文件**同一目录**，且格式正确（使用 JSON 校验器检查）。

### Q: tkinter 相关警告？
A: 在无图形界面的 Linux 环境（如 Docker）中打包会有此警告。如需完整的 GUI 支持，请在有桌面环境的系统上打包。

## 平台特定说明

### Windows
- ✅ 完整的 GUI 支持
- ✅ 双击即可运行
- ✅ 可添加自定义图标
- ⚠️ 可能被杀毒软件误报

### Linux
- ⚠️ 需要安装 tkinter 图形库
- ✅ 命令行运行
- ✅ 可制作 .deb 或 .rpm 包

### macOS
- ⚠️ 需要代码签名（避免被 Gatekeeper 阻止）
- ✅ 可打包为 .app 应用包
- ✅ 支持 .icns 图标

## 进阶配置

### 自定义图标

编辑 `outline_app_onefile.spec`，修改：
```python
icon='path/to/icon.ico',  # Windows
# 或
icon='path/to/icon.icns',  # macOS
```

### 排除不需要的模块

减小文件大小：
```python
excludes=[
    'matplotlib',
    'numpy',
    'scipy',
    # ... 其他不需要的大型库
],
```

### 添加额外文件

在 `outline_app_onefile.spec` 中：
```python
datas=[
    ('your_file.txt', '.'),
    ('your_folder/', 'destination_folder/'),
],
```

## 相关文档

- **详细打包指南**: `BUILD_GUIDE.md`
- **用户使用说明**: `用户配置指南.txt`
- **项目说明**: `CLAUDE.md`
- **使用手册**: `使用说明.txt`

## 技术支持

微信: dddjs003

---

**最后更新**: 2026-01-04
