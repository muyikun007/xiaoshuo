# CLAUDE.md - AI Assistant Guide for Xiaoshuo (小说大纲生成器)

## Project Overview

**Xiaoshuo** is a Chinese novel outline generator application that leverages AI (primarily Google Gemini) to create structured novel outlines for web fiction authors. The project supports multiple deployment modes and includes both desktop (tkinter GUI) and web-based (Flask/FastAPI) interfaces.

### Core Functionality
- **Outline Generation**: Creates comprehensive novel outlines with chapters, plot points, character arcs, and world-building
- **Outline Modification**: Refines and adjusts generated outlines based on user feedback
- **Chapter Content Generation**: Expands chapter summaries into full chapter content
- **Logic Checking**: Analyzes outlines for plot consistency and narrative logic
- **Token/Credit System**: Manages user access through a token-based payment system

## Architecture

The project consists of three main components:

### 1. Desktop GUI Application (`app.py`)
- **Technology**: Python + tkinter/ttkbootstrap
- **Purpose**: Standalone Windows desktop application (packaged with PyInstaller)
- **Features**:
  - User authentication (phone + password)
  - MySQL-backed token system
  - Real-time streaming outline generation
  - Multi-AI provider support (Gemini, Doubao, Claude)
- **Deployment**: Compiled to `outline_app.exe` using PyInstaller specs

### 2. Web Application - Flask Version (`web_app/`)
- **Technology**: Flask + Flask-Login + SQLAlchemy
- **Purpose**: Full-featured web interface with user management
- **Database**: MySQL (with SQLite fallback)
- **Features**:
  - User registration/login system
  - Novel project management
  - Background chapter generation (threading)
  - Balance/token tracking
  - Chapter-by-chapter content generation

### 3. Web Application - FastAPI Version (`web/`)
- **Technology**: FastAPI + SQLAlchemy + Jinja2
- **Purpose**: Lightweight async web service
- **Database**: SQLite
- **Features**:
  - Simplified user system
  - Async background tasks
  - Novel outline parsing
  - Chapter generation queue

### 4. Utility Scripts
- `check_logic.py`: Analyzes outline for logical consistency
- `enrich_outline.py`: Batch enriches chapter summaries with AI
- `fix_outline.py`: Post-processes outlines (chapter swapping, renaming, fixes)
- `test_api.py`: API key validation and diagnostics
- `test_gemini3.py`: Gemini API testing
- `test_ui.py`: UI component testing

## Directory Structure

```
xiaoshuo/
├── app.py                          # Main desktop GUI application (marshaled/obfuscated)
├── requirements.txt                # Core Python dependencies
├── config.json                     # Configuration file (GITIGNORED - contains API keys)
│
├── web/                            # FastAPI web application
│   ├── main.py                     # FastAPI app with routes
│   ├── ai_service.py               # AI service abstraction
│   ├── templates/                  # Jinja2 templates
│   │   ├── index.html
│   │   ├── novel.html
│   │   └── pay.html
│   └── requirements.txt
│
├── web_app/                        # Flask web application
│   ├── app.py                      # Flask app with routes
│   ├── models.py                   # SQLAlchemy models (User, Novel, Chapter)
│   ├── services.py                 # NovelGenerator service
│   ├── extensions.py               # Flask extensions (db, login_manager)
│   ├── templates/                  # Jinja2 templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html
│   │   ├── create_novel.html
│   │   ├── novel_detail.html
│   │   ├── profile.html
│   │   └── recharge.html
│   └── requirements.txt
│
├── check_logic.py                  # Outline logic analysis utility
├── enrich_outline.py               # Batch chapter enrichment utility
├── fix_outline.py                  # Outline post-processing utility
├── test_api.py                     # API diagnostics tool
├── test_gemini3.py                 # Gemini API testing
├── test_ui.py                      # UI testing utilities
│
├── mysql_token_only_schema.sql     # MySQL database schema
├── outline_app.spec                # PyInstaller spec (directory mode)
├── outline_app_onefile.spec        # PyInstaller spec (single file mode)
├── file_version_info.txt           # Windows EXE version info
│
├── 使用说明.txt                     # User manual (Chinese)
├── README.md                       # Project README
│
└── [Novel Directories/Files]       # Sample/test novel outlines
    ├── 扫黑：权路锋刃/
    ├── 重生：巅峰人生/
    ├── 商战：深渊操盘手/
    └── *.txt                       # Generated outline files
```

## Tech Stack

### Core Dependencies
- **Python 3.8+**
- **google-genai**: Google Gemini AI SDK (v1.0.0+)
- **requests**: HTTP client for API calls
- **pymysql**: MySQL database connector
- **ttkbootstrap**: Modern tkinter UI framework

### Web Framework Dependencies
- **Flask**: Web framework (Flask version)
- **FastAPI**: Async web framework (FastAPI version)
- **SQLAlchemy**: ORM for database operations
- **Flask-Login**: User session management
- **Jinja2**: Template engine
- **uvicorn**: ASGI server (for FastAPI)

### Development Tools
- **PyInstaller**: Desktop app packaging
- **marshal**: Code obfuscation (app.py)

## Database Schema

### MySQL Tables (Token-Based System)

#### `users`
- User authentication and profile
- Token balance tracking
- Status management (active/disabled)

#### `token_products`
- Token purchase packages
- Pricing in cents (CNY)
- Product status (available/unavailable)

#### `payment_orders`
- Payment transaction records
- Support for WeChat/Alipay
- Order status tracking

#### `payment_notifications`
- Payment callback logs
- Signature verification records

#### `token_ledger`
- Token transaction log (credits/debits)
- Idempotent delivery tracking
- Business type categorization (recharge/consume/refund/manual)

#### `outline_jobs`
- Outline generation task queue
- Provider and model tracking
- Token cost calculation
- Error logging

### SQLite Schema (Simplified Web Apps)
- `users`: Basic auth + balance
- `novels`: Novel projects
- `chapters`: Chapter metadata and content

## Configuration

### `config.json` Structure
```json
{
  "api_key": "YOUR_GEMINI_API_KEY",
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "doubao_api_key": "YOUR_DOUBAO_API_KEY",
  "doubao_model": "ENDPOINT_ID",
  "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "claude_api_key": "YOUR_CLAUDE_API_KEY",
  "secret_key": "FLASK_SECRET_KEY",
  "mysql": {
    "host": "localhost",
    "port": 3306,
    "user": "username",
    "password": "password",
    "database": "xiaoshuo",
    "charset": "utf8mb4"
  },
  "auto_create_tables": true
}
```

**IMPORTANT**: `config.json` is in `.gitignore` and should NEVER be committed to version control.

### Environment Variables (Alternative)
- `GEMINI_API_KEY`: Google Gemini API key
- `DOUBAO_API_KEY`: Bytedance Doubao API key
- `DOUBAO_MODEL`: Doubao endpoint ID
- `DOUBAO_BASE_URL`: Doubao API base URL
- `CLAUDE_API_KEY`: Anthropic Claude API key
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- `FLASK_SECRET_KEY`: Flask session secret
- `DATABASE_URL`: Full database connection string
- `AUTO_CREATE_TABLES`: Auto-create DB tables on startup

## AI Provider Integration

### Google Gemini (Primary Provider)
- **Models Used**:
  - `gemini-3-pro-preview` (default for outline generation)
  - `gemini-2.5-pro` (fallback)
  - `gemini-2.0-flash` (testing)
- **Features**:
  - Streaming response support
  - JSON schema validation
  - System instruction support
  - Temperature and top-p tuning

### Bytedance Doubao (Alternative Provider)
- **Endpoint**: ARK API (Volcano Engine)
- **Integration**: OpenAI-compatible chat completions API
- **Configuration**: Requires endpoint ID in config

### Anthropic Claude (Alternative Provider)
- **Model**: `claude-3-5-sonnet-20241022`
- **Integration**: Messages API
- **Usage**: Secondary provider option

## Key Conventions & Patterns

### 1. Outline Format Requirements
Generated outlines MUST follow this structure:
```
作品名：[Title]

类型：[Genre]

核心人设：
- 主角：[Description]
- 对手：[Description]
- 导师：[Description]
- 盟友：[Description]

世界观与设定：
[World-building details]

爽点清单：
1. [Plot hook 1]
2. [Plot hook 2]
...

三幕结构梗概：
第一幕：[Act 1 summary]
第二幕：[Act 2 summary]
第三幕：[Act 3 summary]

### 第1章：[Chapter Title]
**内容**：[Chapter summary]
**【悬疑点】**：[Mystery/hook]
**【爽点】**：[Satisfaction point or "暂无"]

[Repeat for each chapter...]

可扩展支线与后续走向：
[Future plot possibilities]
```

### 2. Chapter Parsing Regex Pattern
```python
pattern = r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)"
```
- Group 1: Full title line
- Group 2: Chapter number
- Group 3: Chapter title (without "第X章" prefix)
- Group 4: Chapter content

### 3. API Key Loading Priority
1. Check `config.json` in current directory
2. Check environment variables
3. Check `config.json` in script directory
4. Fail with clear error message

### 4. Error Handling Patterns
- **Database Connections**: Always wrap in try-except with rollback
- **API Calls**: Implement retry logic with exponential backoff
- **User Balance**: Check before deduction, refund on failure
- **File Operations**: Create backups before modifications

### 5. Naming Conventions
- **Functions**: `snake_case` (e.g., `build_system_instruction`)
- **Classes**: `PascalCase` (e.g., `NovelGenerator`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_GEMINI_MODEL`)
- **Private Functions**: Prefix with `_` (e.g., `_gen_salt`)
- **Database Models**: Singular nouns (e.g., `User`, not `Users`)

### 6. Code Organization Principles
- **Separation of Concerns**: UI logic separate from business logic
- **Service Layer**: AI interactions abstracted to service classes
- **Configuration Management**: Centralized config loading
- **Database Abstraction**: Use ORM (SQLAlchemy) for all DB operations

## Development Workflows

### Setting Up Development Environment

```bash
# 1. Clone repository
git clone <repository-url>
cd xiaoshuo

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create configuration
cp config.example.json config.json  # If example exists
# Edit config.json with your API keys

# 5. Set up database (MySQL)
mysql -u root -p < mysql_token_only_schema.sql

# 6. Test API connectivity
python test_api.py
```

### Running the Applications

#### Desktop GUI Application
```bash
python app.py
```

#### Flask Web Application
```bash
cd web_app
python app.py
# Access at http://localhost:5000
```

#### FastAPI Web Application
```bash
cd web
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Access at http://localhost:8000
```

### Building Desktop Application

```bash
# One-folder distribution
pyinstaller outline_app.spec

# One-file distribution
pyinstaller outline_app_onefile.spec

# Output in dist/ folder
```

### Testing Utilities

```bash
# Test API connectivity
python test_api.py

# Test Gemini API specifically
python test_gemini3.py

# Check outline logic
python check_logic.py  # Edit FILE_PATH in script first

# Enrich outline chapters
python enrich_outline.py  # Edit FILE_PATH in script first

# Fix outline structure
python fix_outline.py  # Edit FILE_PATH in script first
```

## AI Assistant Guidelines

### When Modifying Code

1. **Preserve API Key Security**
   - Never hardcode API keys
   - Always use config file or environment variables
   - Never commit `config.json`

2. **Maintain Database Consistency**
   - Always use transactions for multi-step operations
   - Implement proper rollback on errors
   - Validate data before database writes

3. **Follow Existing Patterns**
   - Use existing API key loading functions
   - Maintain consistent error handling
   - Keep UI/business logic separation

4. **Test AI Integrations**
   - Test with actual API calls before committing
   - Handle rate limits and timeouts gracefully
   - Provide fallback models when primary fails

5. **Preserve User Experience**
   - Maintain streaming output for long operations
   - Show progress indicators for async tasks
   - Provide clear error messages in Chinese

### When Adding Features

1. **Configuration First**: Add new config options to `config.json` structure
2. **Service Layer**: Implement business logic in service classes
3. **Database Changes**: Update schema SQL file if adding tables/columns
4. **Error Handling**: Add try-except blocks with specific error messages
5. **Documentation**: Update this file with new patterns/conventions

### Common Pitfalls to Avoid

1. **Character Encoding**: Always use `encoding="utf-8"` for file operations
2. **Database Charset**: Use `utf8mb4` for MySQL to support all Chinese characters
3. **Path Separators**: Use `os.path.join()` instead of hardcoded `/` or `\`
4. **API Timeouts**: Set reasonable timeouts (30s+) for AI generation calls
5. **Token Calculation**: Account for both input and output tokens in cost estimates
6. **Streaming Interruptions**: Handle pause/resume for streaming responses
7. **Balance Race Conditions**: Lock user balance updates during deductions

### File-Specific Notes

#### `app.py`
- **WARNING**: This file uses `marshal` obfuscation and loads from `recovered_app_*.code`
- Direct modifications to `app.py` won't work - need to modify source and recompile
- Contains full GUI application with MySQL integration
- Uses ttkbootstrap for modern UI components

#### `web_app/services.py`
- Contains `NovelGenerator` class - primary AI service abstraction
- Implements streaming generation with callbacks
- Handles multiple AI providers (Gemini, Doubao, Claude)

#### `web_app/models.py`
- SQLAlchemy ORM models
- Flask-Login integration for `User` model
- Includes JSON fields for metadata storage

#### Utility Scripts
- All use hardcoded `FILE_PATH` - must be edited before running
- Create automatic backups before modifying files
- Use consistent chapter parsing regex across all scripts

## Security Considerations

1. **Password Hashing**: Uses `pbkdf2:sha256` with 260,000+ iterations
2. **SQL Injection**: Prevented by SQLAlchemy ORM
3. **API Key Storage**: Never in source code, only in gitignored config
4. **Session Security**: Flask secret key for session encryption
5. **Balance Validation**: Server-side checks before all operations
6. **Payment Verification**: Signature validation for payment callbacks

## File Naming Conventions

- **Outline Files**: `{title}_{timestamp}_大纲.txt`
- **Backup Files**: `{original}_backup_{unix_timestamp}.txt`
- **Before-Fix Files**: `{original}_before_fix.txt`
- **Novel Directories**: Named after novel titles in Chinese

## Common Tasks for AI Assistants

### Task: Add a new AI provider
1. Update `config.json` structure documentation
2. Add API key loading in utility function
3. Implement provider client in service layer
4. Add model selection in UI
5. Update `test_api.py` with new provider test
6. Document in this file

### Task: Modify outline format
1. Update `build_system_instruction()` function
2. Update chapter parsing regex if needed
3. Test with actual API calls
4. Update example format in this file
5. Regenerate sample outlines

### Task: Add database field
1. Update `mysql_token_only_schema.sql`
2. Update SQLAlchemy models
3. Create migration script (if using migrations)
4. Update relevant service methods
5. Update UI forms if user-facing

### Task: Fix encoding issues
1. Check file read/write uses `encoding="utf-8"`
2. Verify MySQL tables use `utf8mb4` charset
3. Check HTTP headers set correct charset
4. Test with actual Chinese characters

## Debugging Tips

### API Call Failures
1. Run `python test_api.py` to validate keys
2. Check `config.json` format (valid JSON)
3. Verify network connectivity to API endpoints
4. Check API quotas and rate limits

### Database Connection Issues
1. Verify MySQL service is running
2. Check credentials in `config.json`
3. Test connection string with manual `pymysql` connect
4. Check firewall rules for MySQL port

### Outline Parsing Issues
1. Print matched groups from regex
2. Check for non-standard chapter numbering
3. Verify UTF-8 encoding of input file
4. Test regex at regex101.com with sample text

### Balance/Token Issues
1. Check `token_ledger` table for transaction history
2. Verify idempotency key uniqueness
3. Look for failed transactions without refunds
4. Audit `balance_after` snapshots vs calculated sum

## Version History Notes

- Original app.py compiled and obfuscated (current state)
- Multiple novel outline samples included (Chinese web fiction)
- Payment QR codes included (WeChat Pay)
- Windows executable packaging configured

---

**Last Updated**: 2026-01-02
**Maintained By**: AI Assistant (Claude)
**For Questions**: Refer to `使用说明.txt` or contact via WeChat: dddjs003
