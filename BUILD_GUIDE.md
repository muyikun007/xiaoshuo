# 小说大纲生成器 - 打包和部署指南

## 目录
- [准备工作](#准备工作)
- [配置文件准备](#配置文件准备)
- [打包流程](#打包流程)
- [部署说明](#部署说明)
- [常见问题](#常见问题)

---

## 准备工作

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 PyInstaller（如果尚未安装）
pip install pyinstaller
```

### 2. 检查必要文件

确保以下文件存在于项目根目录：

- ✅ `app.py` - 主应用程序
- ✅ `outline_app_onefile.spec` - PyInstaller 打包配置
- ✅ `config.example.json` - 示例配置文件
- ✅ `使用说明.txt` - 使用说明
- ✅ `file_version_info.txt` - 版本信息（Windows）
- ⚠️ `config.json` - 实际配置文件（可选，用于测试）

---

## 配置文件准备

### 创建配置文件

在打包之前，您有两个选择：

#### 选项 1: 仅打包示例配置（推荐）

打包时只包含 `config.example.json`，用户需要在首次使用时手动配置：

```bash
# 确保 config.example.json 存在
ls config.example.json
```

用户使用时需要：
1. 将可执行文件解压到某个目录
2. 在同一目录创建 `config.json`
3. 填写必要的 API 密钥

#### 选项 2: 打包完整配置（测试用）

如果您想打包一个预配置的版本用于测试：

```bash
# 复制示例配置
cp config.example.json config.json

# 编辑 config.json，填写实际的 API 密钥
nano config.json  # 或使用其他编辑器
```

**⚠️ 警告**: 不要将包含真实 API 密钥的可执行文件分发给其他人！

### 配置文件内容说明

`config.json` 最少需要包含：

```json
{
  "api_key": "YOUR_GEMINI_API_KEY_HERE",
  "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",

  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "xiaoshuo_user",
    "password": "your_password_here",
    "database": "xiaoshuo",
    "charset": "utf8mb4"
  }
}
```

---

## 打包流程

### 单文件可执行程序（推荐）

使用 `outline_app_onefile.spec` 打包成单个 `.exe` 文件：

```bash
# 在项目根目录执行
pyinstaller outline_app_onefile.spec --clean

# 打包完成后，可执行文件位于
# dist/小说大纲生成器.exe (Windows)
# dist/小说大纲生成器 (Linux/Mac)
```

### 打包说明

打包过程会：

1. ✅ 将 `app.py` 及所有依赖打包成单个可执行文件
2. ✅ 内嵌 `config.example.json` 作为配置模板
3. ✅ 内嵌 `使用说明.txt`
4. ✅ 内嵌微信支付二维码图片（如果存在）
5. ✅ 如果存在 `config.json`，也会一并打包
6. ✅ 包含版本信息（Windows）

### 打包时的文件查找优先级

打包后的程序会按以下顺序查找配置文件：

1. 环境变量 `CONFIG_JSON_PATH` 或 `OUTLINE_APP_CONFIG` 指定的路径
2. 可执行文件同目录的 `config.json` **(推荐用户配置位置)**
3. 当前工作目录的 `config.json`
4. 父目录的 `config.json`
5. 打包内嵌的 `config.json` 或 `config.example.json`（只读）

---

## 部署说明

### Windows 部署

#### 方式 1: 独立部署（推荐）

```
部署目录/
├── 小说大纲生成器.exe
├── config.json          <- 用户需要创建
└── README.txt           <- 可选，提供配置说明
```

步骤：
1. 将 `dist/小说大纲生成器.exe` 复制到目标位置
2. 在同一目录创建 `config.json` 文件
3. 填写必要的 API 密钥和数据库配置
4. 双击运行 `小说大纲生成器.exe`

#### 方式 2: 使用环境变量

如果不想在可执行文件旁创建配置文件，可以设置环境变量：

```cmd
# Windows CMD
set CONFIG_JSON_PATH=C:\path\to\your\config.json
小说大纲生成器.exe

# Windows PowerShell
$env:CONFIG_JSON_PATH = "C:\path\to\your\config.json"
.\小说大纲生成器.exe
```

### Linux/Mac 部署

```bash
# 赋予执行权限
chmod +x 小说大纲生成器

# 创建配置文件
cat > config.json << 'EOF'
{
  "api_key": "YOUR_API_KEY",
  "gemini_api_key": "YOUR_API_KEY",
  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "xiaoshuo_user",
    "password": "your_password",
    "database": "xiaoshuo",
    "charset": "utf8mb4"
  }
}
EOF

# 运行
./小说大纲生成器
```

---

## 首次使用配置

### 1. 创建配置文件

在可执行文件同目录创建 `config.json`：

```json
{
  "api_key": "你的 Gemini API 密钥",
  "gemini_api_key": "你的 Gemini API 密钥",

  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "xiaoshuo_user",
    "password": "数据库密码",
    "database": "xiaoshuo",
    "charset": "utf8mb4"
  },

  "auto_create_tables": true
}
```

### 2. 设置数据库

如果使用 MySQL（桌面应用必需）：

```bash
# 导入数据库架构
mysql -u root -p < mysql_token_only_schema.sql

# 或使用配置文件中的自动创建表功能
# "auto_create_tables": true
```

### 3. 运行应用

- **Windows**: 双击 `小说大纲生成器.exe`
- **Linux/Mac**: `./小说大纲生成器`

---

## 常见问题

### Q1: 打包时提示找不到模块

**问题**: `ModuleNotFoundError: No module named 'xxx'`

**解决方案**:
```bash
# 安装缺失的模块
pip install xxx

# 或重新安装所有依赖
pip install -r requirements.txt --force-reinstall
```

### Q2: 运行时提示找不到配置文件

**问题**: 应用启动时提示"未配置 API Key"

**解决方案**:
1. 确保 `config.json` 在可执行文件同目录
2. 检查 `config.json` 格式是否正确（使用 JSON 校验器）
3. 检查文件编码是否为 UTF-8

### Q3: 打包后文件过大

**问题**: 单个可执行文件超过 100MB

**解决方案**:
```bash
# 使用 UPX 压缩（已在 spec 文件中启用）
# 如果想进一步减小体积，可以排除不必要的库

# 编辑 outline_app_onefile.spec，在 excludes 中添加：
excludes=[
    'matplotlib',
    'numpy',
    'scipy',
    'pandas',
    # ... 其他不需要的大型库
],
```

### Q4: Windows Defender 误报病毒

**问题**: 打包的 exe 文件被 Windows Defender 标记为威胁

**解决方案**:
1. 这是 PyInstaller 打包程序的常见问题
2. 可以在打包后使用代码签名工具签名
3. 或提交到微软进行白名单申请
4. 临时解决：添加到 Windows Defender 排除列表

### Q5: 配置文件无法修改

**问题**: 打包后修改配置文件不生效

**解决方案**:
- 确保 `config.json` 在可执行文件**同目录**，而不是在打包内嵌的临时目录
- 打包内嵌的配置文件是只读的，用户配置必须在外部创建

### Q6: 数据库连接失败

**问题**: 提示 "MySQL 配置不完整" 或连接失败

**解决方案**:
1. 检查 MySQL 服务是否运行
2. 验证 `config.json` 中的数据库凭据
3. 确保数据库已创建：`CREATE DATABASE xiaoshuo CHARACTER SET utf8mb4;`
4. 检查防火墙是否阻止 MySQL 端口（默认 3306）

---

## 高级配置

### 自定义图标

如果想为可执行文件添加自定义图标：

1. 准备 `.ico` 文件（Windows）或 `.icns` 文件（Mac）
2. 修改 `outline_app_onefile.spec`:
   ```python
   icon='path/to/your/icon.ico',  # 替换 icon=None 这一行
   ```

### 多语言支持

配置文件中可以添加自定义小说类型和主题：

```json
{
  "novel_types": [
    "都市言情",
    "都市商战",
    "玄幻修真",
    "科幻未来"
  ],

  "theme_library": [
    "扫黑除恶",
    "商业帝国",
    "重生逆袭"
  ]
}
```

### 环境变量配置

除了配置文件，也可以使用环境变量：

```bash
# Linux/Mac
export GEMINI_API_KEY="your_api_key"
export MYSQL_HOST="localhost"
export MYSQL_USER="xiaoshuo_user"
export MYSQL_PASSWORD="password"
export MYSQL_DATABASE="xiaoshuo"

# Windows
set GEMINI_API_KEY=your_api_key
set MYSQL_HOST=localhost
```

---

## 版本管理

当前版本信息在 `file_version_info.txt` 中定义：

```
FileVersion: 1.0.2.0
ProductVersion: 1.0.2.0
```

更新版本时：
1. 修改 `file_version_info.txt`
2. 更新 `CLAUDE.md` 中的版本历史
3. 重新打包

---

## 技术支持

如遇到问题：
1. 查看应用日志（如果有）
2. 检查配置文件格式
3. 验证 API 密钥有效性
4. 测试数据库连接

联系方式：
- 微信: dddjs003
- GitHub Issues: [项目仓库]

---

**最后更新**: 2026-01-04
