"""
增强版 Flask 应用
包含桌面端的所有功能：大纲生成、多模型支持、文本润色、ZIP导出等
"""

import os
import re
import json
import threading
import zipfile
import io
import time
from datetime import datetime
from urllib.parse import quote_plus
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy.exc import IntegrityError

from .extensions import db, login_manager
from .models import User, Novel, Chapter
from .services import NovelGenerator
from .advanced_services import (
    AdvancedNovelGenerator,
    get_theme_suggestions,
    get_all_novel_types,
    load_config_from_file,
    THEME_SUGGESTIONS
)

# ==========================================================================
# 全局变量
# ==========================================================================

# 存储生成任务
GENERATION_TASKS = {}  # novel_id -> {status, progress, cancel_event, pause_event, thread}
GEN_START_TIMES = {}   # chapter_id -> start_time

# ==========================================================================
# 辅助函数
# ==========================================================================

def _project_root():
    """获取项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_root_config():
    """加载根目录的配置文件"""
    cfg_path = os.path.join(_project_root(), "config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _build_mysql_uri(cfg):
    """构建 MySQL 连接URI"""
    host = (cfg.get("host") or os.environ.get("MYSQL_HOST") or "").strip()
    if not host:
        return ""
    port = cfg.get("port") or os.environ.get("MYSQL_PORT") or 3306
    user = (cfg.get("user") or os.environ.get("MYSQL_USER") or "").strip()
    password = cfg.get("password") or os.environ.get("MYSQL_PASSWORD") or ""
    database = (cfg.get("database") or os.environ.get("MYSQL_DATABASE") or "").strip()
    charset = (cfg.get("charset") or "utf8mb4").strip()
    if not user or not database:
        return ""
    return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(str(password))}@{host}:{int(port)}/{quote_plus(database)}?charset={quote_plus(charset)}"

def _parse_outline_text(text):
    """从文本中解析章节信息"""
    items = []
    pattern_cn = re.finditer(
        r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)",
        text
    )
    for m in pattern_cn:
        full_title_part = m.group(1).strip()
        chap_num = int(m.group(2))
        title_only = (m.group(3) or "").strip()
        content_part = (m.group(4) or "").strip()
        title_clean = re.sub(r"^第\d+章\s*", "", full_title_part).strip()
        if title_only:
            title_clean = title_only
        items.append({
            "chapter": chap_num,
            "title": title_clean,
            "summary": content_part
        })

    if not items:
        pattern_ch = re.finditer(
            r"(?:Ch(?:apter)?\.?\s*)(\d+)\s*([^\n:：]*?)\s*[:：]\s*([\s\S]*?)(?=(?:\n\s*(?:Ch(?:apter)?\.?\s*\d+|第\s*\d+\s*章))|$)",
            text,
            re.IGNORECASE
        )
        for m in pattern_ch:
            chap_num = int(m.group(1))
            title_only = (m.group(2) or "").strip()
            content_part = (m.group(3) or "").strip()
            items.append({
                "chapter": chap_num,
                "title": title_only,
                "summary": content_part
            })

    items.sort(key=lambda x: x["chapter"])
    return items

def _parse_and_save_chapters(novel, text):
    """解析大纲文本并保存章节"""
    items = _parse_outline_text(text)
    for it in items:
        # 检查章节是否已存在
        existing = Chapter.query.filter_by(
            novel_id=novel.id,
            chapter_num=it["chapter"]
        ).first()

        if existing:
            # 更新现有章节
            existing.title = it["title"]
            existing.summary = it["summary"]
        else:
            # 创建新章节
            chap = Chapter(
                novel_id=novel.id,
                chapter_num=it["chapter"],
                title=it["title"],
                summary=it["summary"]
            )
            db.session.add(chap)

    db.session.commit()
    return items

# ==========================================================================
# Flask 应用创建
# ==========================================================================

def create_app():
    app = Flask(__name__)

    # 加载配置
    cfg = _load_root_config()
    mysql_cfg = cfg.get("mysql") if isinstance(cfg.get("mysql"), dict) else {}
    mysql_uri = _build_mysql_uri(mysql_cfg)

    app.config["SECRET_KEY"] = (
        os.environ.get("FLASK_SECRET_KEY") or
        cfg.get("secret_key") or
        "dev-secret-key-change-in-production"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        os.environ.get("DATABASE_URL") or
        mysql_uri or
        f"sqlite:///{os.path.join(_project_root(), 'db.sqlite3')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect(url_for('login'))

    # ======================================================================
    # 基础路由
    # ======================================================================

    @app.route('/')
    def index():
        """首页"""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """用户注册"""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            phone = request.form.get('phone', '')  # 可选

            if not username or not password:
                flash('请输入用户名和密码')
                return redirect(url_for('register'))

            # 检查用户名是否已存在
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('用户名已存在')
                return redirect(url_for('register'))

            # 创建用户（赠送初始 Token）
            user = User(
                username=username,
                phone=phone if phone else None,
                password_hash=generate_password_hash(
                    password,
                    method='pbkdf2:sha256:260000',
                    salt_length=16
                ),
                token_balance=300000  # 赠送 30万 Token
            )
            db.session.add(user)
            try:
                db.session.commit()
                login_user(user)
                flash('注册成功！已赠送 300,000 Token')
                return redirect(url_for('dashboard'))
            except IntegrityError:
                db.session.rollback()
                flash('用户名或手机号已存在')
                return redirect(url_for('register'))

        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """用户登录"""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()

            # 验证用户是否存在且密码正确
            if user and check_password_hash(user.password_hash, password) and user.status != 0:
                user.last_login_at = datetime.utcnow()
                db.session.commit()
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('用户名或密码错误')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        """用户登出"""
        logout_user()
        flash('已成功登出')
        return redirect(url_for('index'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        """用户仪表盘"""
        try:
            novels = Novel.query.filter_by(user_id=current_user.id).order_by(
                Novel.created_at.desc()
            ).all()
        except Exception:
            novels = []
        return render_template('dashboard.html', novels=novels)

    @app.route('/profile')
    @login_required
    def profile():
        """用户个人信息"""
        return render_template('profile.html')

    # ======================================================================
    # 小说创建与管理
    # ======================================================================

    @app.route('/create_novel', methods=['GET', 'POST'])
    @login_required
    def create_novel():
        """创建小说（手动输入大纲）"""
        if request.method == 'POST':
            title = request.form.get('title', 'Untitled')
            n_type = request.form.get('type', '')
            theme = request.form.get('theme', '')
            outline_text = request.form.get('outline', '')

            novel = Novel(
                user_id=current_user.id,
                title=title,
                type=n_type,
                theme=theme,
                outline=outline_text
            )
            db.session.add(novel)
            db.session.commit()

            # 解析大纲并保存章节
            if outline_text:
                _parse_and_save_chapters(novel, outline_text)

            flash('小说创建成功！')
            return redirect(url_for('novel_detail', novel_id=novel.id))

        # GET 请求 - 显示表单，传递类型和主题建议
        novel_types = get_all_novel_types()
        return render_template(
            'create_novel.html',
            novel_types=novel_types,
            theme_suggestions=THEME_SUGGESTIONS
        )

    @app.route('/generate_outline', methods=['GET', 'POST'])
    @login_required
    def generate_outline():
        """生成完整大纲（核心新功能）"""
        if request.method == 'POST':
            # 检查余额
            if current_user.balance < 1.0:
                flash('余额不足，请先充值！')
                return redirect(url_for('recharge'))

            # 获取参数
            title = request.form.get('title', '未命名')
            n_type = request.form.get('type', '')
            theme = request.form.get('theme', '')
            chapters = int(request.form.get('chapters', 100))
            channel = request.form.get('channel', '男频')
            provider = request.form.get('provider', 'Gemini')
            model_name = request.form.get('model', None)

            if not n_type or not theme:
                flash('请输入小说类型和主题')
                return redirect(url_for('generate_outline'))

            # 先创建小说记录
            novel = Novel(
                user_id=current_user.id,
                title=title,
                type=n_type,
                theme=theme,
                outline="生成中..."
            )
            db.session.add(novel)
            db.session.commit()

            # 扣除 1 次数卡（大纲生成消耗）
            current_user.balance -= 1
            db.session.commit()

            # 后台生成大纲
            def run_outline_generation():
                with app.app_context():
                    try:
                        # 加载配置
                        config = _load_root_config()
                        generator = AdvancedNovelGenerator(config=config)

                        # 进度回调
                        def progress_callback(message, percent):
                            task = GENERATION_TASKS.get(novel.id)
                            if task:
                                task['progress'] = percent
                                task['message'] = message

                        # 生成大纲
                        result = generator.generate_outline(
                            novel_type=n_type,
                            theme=theme,
                            chapters=chapters,
                            channel=channel,
                            provider=provider,
                            model_name=model_name,
                            progress_callback=progress_callback
                        )

                        if result['success']:
                            # 更新小说记录
                            novel.outline = result['outline_text']
                            db.session.commit()

                            # 保存章节
                            _parse_and_save_chapters(novel, result['outline_text'])

                            # 更新任务状态
                            task = GENERATION_TASKS.get(novel.id)
                            if task:
                                task['status'] = 'completed'
                                task['message'] = '大纲生成完成！'
                        else:
                            # 生成失败
                            novel.outline = f"生成失败：{result.get('error', '未知错误')}"
                            db.session.commit()

                            task = GENERATION_TASKS.get(novel.id)
                            if task:
                                task['status'] = 'failed'
                                task['message'] = result.get('error', '生成失败')

                    except Exception as e:
                        novel.outline = f"生成异常：{str(e)}"
                        db.session.commit()

                        task = GENERATION_TASKS.get(novel.id)
                        if task:
                            task['status'] = 'failed'
                            task['message'] = str(e)

            # 创建任务记录
            cancel_event = threading.Event()
            pause_event = threading.Event()
            thread = threading.Thread(target=run_outline_generation)

            GENERATION_TASKS[novel.id] = {
                'status': 'generating',
                'progress': 0,
                'message': '正在生成大纲...',
                'cancel_event': cancel_event,
                'pause_event': pause_event,
                'thread': thread
            }

            thread.start()

            # 重定向到进度页面
            flash('大纲生成任务已提交，请稍候...')
            return redirect(url_for('outline_progress', novel_id=novel.id))

        # GET 请求 - 显示表单
        novel_types = get_all_novel_types()
        return render_template(
            'generate_outline.html',
            novel_types=novel_types,
            theme_suggestions=THEME_SUGGESTIONS
        )

    @app.route('/outline_progress/<int:novel_id>')
    @login_required
    def outline_progress(novel_id):
        """大纲生成进度页面"""
        novel = Novel.query.get_or_404(novel_id)
        if novel.user_id != current_user.id:
            return "Unauthorized", 403

        return render_template('outline_progress.html', novel=novel)

    @app.route('/api/outline_status/<int:novel_id>')
    @login_required
    def api_outline_status(novel_id):
        """获取大纲生成状态（AJAX）"""
        novel = Novel.query.get_or_404(novel_id)
        if novel.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        task = GENERATION_TASKS.get(novel_id)
        if task:
            return jsonify({
                'status': task['status'],
                'progress': task['progress'],
                'message': task['message']
            })
        else:
            # 任务不存在，可能已完成或从未开始
            return jsonify({
                'status': 'completed',
                'progress': 100,
                'message': '已完成'
            })

    @app.route('/novel/<int:novel_id>')
    @login_required
    def novel_detail(novel_id):
        """小说详情页"""
        novel = Novel.query.get_or_404(novel_id)
        if novel.user_id != current_user.id:
            return "Unauthorized", 403

        chapters = Chapter.query.filter_by(novel_id=novel.id).order_by(
            Chapter.chapter_num
        ).all()

        return render_template(
            'novel_detail.html',
            novel=novel,
            chapters=chapters
        )

    # ======================================================================
    # 章节生成
    # ======================================================================

    @app.route('/generate_chapter/<int:chapter_id>', methods=['POST'])
    @login_required
    def generate_chapter(chapter_id):
        """生成单个章节"""
        chapter = Chapter.query.get_or_404(chapter_id)
        novel = chapter.novel

        if novel.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        if current_user.balance < 1.0:
            return jsonify({"error": "余额不足，请充值"}), 402

        # 加载 API Key
        config = _load_root_config()
        api_key = (
            config.get("gemini_api_key") or
            os.environ.get("GEMINI_API_KEY") or
            ""
        )

        if not api_key:
            return jsonify({"error": "系统未配置 API Key"}), 500

        # 后台生成章节
        def run_gen():
            with app.app_context():
                try:
                    # 获取上一章内容
                    prev_chap = Chapter.query.filter_by(
                        novel_id=novel.id,
                        chapter_num=chapter.chapter_num - 1
                    ).first()
                    prev_text = prev_chap.content if prev_chap else ""

                    # 使用高级生成器
                    generator = AdvancedNovelGenerator(config=config)

                    # 流式生成进度回调
                    def on_progress(text):
                        chapter.content = text
                        db.session.commit()

                    # 生成章节
                    content = generator.generate_chapter(
                        novel_info={
                            'type': novel.type,
                            'theme': novel.theme,
                            'outline': novel.outline
                        },
                        chapter_info={
                            'num': chapter.chapter_num,
                            'title': chapter.title,
                            'summary': chapter.summary
                        },
                        prev_content=prev_text,
                        provider='Gemini'
                    )

                    # 计算字数和成本
                    word_count = len(content)
                    cost = max(1, (int(word_count) + 2) // 3)

                    # 更新章节
                    chapter.content = content
                    chapter.word_count = word_count
                    chapter.cost = cost
                    chapter.status = 'completed'

                    # 扣除余额
                    user = User.query.get(novel.user_id)
                    user.balance -= cost
                    db.session.commit()

                except Exception as e:
                    chapter.status = 'failed'
                    chapter.content = f"生成失败：{str(e)}"
                    db.session.commit()

        # 标记状态并启动线程
        chapter.status = 'generating'
        db.session.commit()
        GEN_START_TIMES[chapter.id] = datetime.utcnow()
        threading.Thread(target=run_gen).start()

        return jsonify({"status": "started", "message": "生成任务已提交"})

    @app.route('/chapter_status/<int:chapter_id>')
    @login_required
    def chapter_status(chapter_id):
        """获取章节生成状态"""
        chapter = Chapter.query.get_or_404(chapter_id)
        eta = None

        if chapter.status == 'generating':
            started = GEN_START_TIMES.get(chapter_id)
            if started:
                elapsed = (datetime.utcnow() - started).total_seconds()
                expected = 75  # 预计75秒
                remain = max(0, int(expected - elapsed))
                eta = remain

        return jsonify({
            "status": chapter.status,
            "content": chapter.content if chapter.status == 'completed' else "",
            "content_preview": (chapter.content or "") if chapter.status != 'completed' else "",
            "cost": chapter.cost,
            "word_count": chapter.word_count,
            "eta_seconds": eta
        })

    # ======================================================================
    # 文本润色
    # ======================================================================

    @app.route('/polish_text', methods=['POST'])
    @login_required
    def polish_text():
        """文本润色功能"""
        data = request.get_json(silent=True) or {}
        text = data.get('text', '')
        polish_type = data.get('type', 'enhance')  # enhance/simplify/correct

        if not text:
            return jsonify({"error": "文本不能为空"}), 400

        if current_user.balance < 1.0:
            return jsonify({"error": "余额不足"}), 402

        try:
            config = _load_root_config()
            generator = AdvancedNovelGenerator(config=config)

            polished = generator.polish_text(
                text=text,
                polish_type=polish_type,
                provider='Gemini'
            )

            # 扣除费用
            cost = max(1, (len(text) + 2) // 3)
            current_user.balance -= cost
            db.session.commit()

            return jsonify({
                "success": True,
                "polished_text": polished,
                "cost": cost
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ======================================================================
    # ZIP 导出
    # ======================================================================

    @app.route('/export_novel/<int:novel_id>')
    @login_required
    def export_novel(novel_id):
        """导出小说为 ZIP 文件"""
        novel = Novel.query.get_or_404(novel_id)
        if novel.user_id != current_user.id:
            return "Unauthorized", 403

        chapters = Chapter.query.filter_by(novel_id=novel.id).order_by(
            Chapter.chapter_num
        ).all()

        # 创建内存中的 ZIP 文件
        mem_zip = io.BytesIO()

        with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 添加大纲文件
            if novel.outline:
                zf.writestr('大纲.txt', novel.outline)

            # 添加每个章节
            for ch in chapters:
                if ch.content:
                    filename = f"第{ch.chapter_num:03d}章 {ch.title}.txt"
                    zf.writestr(filename, ch.content)

            # 添加小说信息
            info = f"""小说信息
==================
标题：{novel.title}
类型：{novel.type}
主题：{novel.theme}
章节数：{len(chapters)}
创建时间：{novel.created_at}
"""
            zf.writestr('小说信息.txt', info)

        mem_zip.seek(0)

        # 生成文件名
        safe_title = re.sub(r'[\\/:*?"<>|]+', '_', novel.title or 'novel')
        filename = f"{safe_title}.zip"

        return send_file(
            mem_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )

    # ======================================================================
    # 充值管理
    # ======================================================================

    @app.route('/recharge', methods=['GET', 'POST'])
    @login_required
    def recharge():
        """Token 充值（模拟）"""
        if request.method == 'POST':
            try:
                amount = int(float(request.form.get('amount', 0)))
                if amount > 0:
                    current_user.balance += amount
                    db.session.commit()
                    flash(f'充值成功！当前 Token：{current_user.token_balance}')
                    return redirect(url_for('dashboard'))
            except:
                flash('充值金额无效')

        return render_template('recharge.html')

    # ======================================================================
    # API 路由
    # ======================================================================

    @app.post('/api/parse_outline')
    def api_parse_outline():
        """解析大纲文本（API）"""
        data = request.get_json(silent=True) or {}
        text = data.get('outline', '')
        if not text:
            return jsonify({"error": "empty outline"}), 400
        items = _parse_outline_text(text)
        return jsonify({"chapters": items})

    @app.post('/api/theme_suggestions')
    def api_theme_suggestions():
        """获取类型的主题建议（API）"""
        data = request.get_json(silent=True) or {}
        novel_type = data.get('type', '')
        suggestions = get_theme_suggestions(novel_type)
        return jsonify({"suggestions": suggestions})

    @app.get('/api/novel_types')
    def api_novel_types():
        """获取所有小说类型（API）"""
        types = get_all_novel_types()
        return jsonify({"types": types})

    # ======================================================================
    # 数据库初始化
    # ======================================================================

    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        auto_create = os.environ.get("AUTO_CREATE_TABLES") or cfg.get("auto_create_tables")
        if (uri.startswith("sqlite:")) or (str(auto_create).lower() in ("1", "true", "yes", "y")):
            db.create_all()

    return app


# ==========================================================================
# 应用实例
# ==========================================================================

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
