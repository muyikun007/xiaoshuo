import os
import re
import json
import threading
from datetime import datetime
from urllib.parse import quote_plus
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy.exc import IntegrityError

from .extensions import db, login_manager
from .models import User, Novel, Chapter
from .services import NovelGenerator

def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_root_config():
    cfg_path = os.path.join(_project_root(), "config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _build_mysql_uri(cfg):
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

def create_app():
    app = Flask(__name__)
    cfg = _load_root_config()
    mysql_cfg = cfg.get("mysql") if isinstance(cfg.get("mysql"), dict) else {}
    mysql_uri = _build_mysql_uri(mysql_cfg)

    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or cfg.get("secret_key") or "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or mysql_uri or f"sqlite:///{os.path.join(_project_root(), 'db.sqlite3')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect(url_for('login'))

    # --- Routes ---

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        # 如果用户已经登录，直接跳转到仪表盘
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if not username or not password:
                flash('请输入用户名和密码')
                return redirect(url_for('register'))
            
            # 检查用户名是否已存在
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('用户名已存在')
                return redirect(url_for('register'))
            
            # 使用更安全的哈希方法
            user = User(username=username, password_hash=generate_password_hash(password, method='pbkdf2:sha256:5000', salt_length=12))
            db.session.add(user)
            try:
                db.session.commit()
                login_user(user)
                return redirect(url_for('dashboard'))
            except IntegrityError:
                db.session.rollback()
                flash('用户名已存在')
                return redirect(url_for('register'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        # 如果用户已经登录，直接跳转到仪表盘
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
        logout_user()
        return redirect(url_for('index'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        try:
            novels = Novel.query.filter_by(user_id=current_user.id).order_by(Novel.created_at.desc()).all()
        except Exception:
            novels = []
        return render_template('dashboard.html', novels=novels)

    @app.route('/profile')
    @login_required
    def profile():
        return render_template('profile.html')

    @app.route('/create_novel', methods=['GET', 'POST'])
    @login_required
    def create_novel():
        if request.method == 'POST':
            title = request.form.get('title')
            n_type = request.form.get('type')
            theme = request.form.get('theme')
            outline_text = request.form.get('outline')
            
            novel = Novel(
                user_id=current_user.id,
                title=title,
                type=n_type,
                theme=theme,
                outline=outline_text
            )
            db.session.add(novel)
            db.session.commit()
            
            # Parse outline if provided
            if outline_text:
                _parse_and_save_chapters(novel, outline_text)
                
            return redirect(url_for('novel_detail', novel_id=novel.id))
        return render_template('create_novel.html')

    @app.route('/novel/<int:novel_id>')
    @login_required
    def novel_detail(novel_id):
        novel = Novel.query.get_or_404(novel_id)
        if novel.user_id != current_user.id:
            return "Unauthorized", 403
        chapters = Chapter.query.filter_by(novel_id=novel.id).order_by(Chapter.chapter_num).all()
        return render_template('novel_detail.html', novel=novel, chapters=chapters)

    GEN_START_TIMES = {}

    @app.route('/generate_chapter/<int:chapter_id>', methods=['POST'])
    @login_required
    def generate_chapter(chapter_id):
        chapter = Chapter.query.get_or_404(chapter_id)
        novel = chapter.novel
        if novel.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        if current_user.balance < 1.0: # Check minimum balance
             return jsonify({"error": "余额不足，请充值"}), 402

        # Load API Key from environment or config (Simple logic for demo)
        # In real app, maybe user provides key or system has one.
        # Assuming system has one in env
        api_key = os.environ.get("GEMINI_API_KEY")
        provider = "Gemini"
        
        # Try to load from ../config.json if not in env
        if not api_key:
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json'), 'r') as f:
                    cfg = json.load(f)
                    api_key = cfg.get('gemini_api_key') or cfg.get('api_key')
                    provider = "Gemini"
            except:
                pass
        
        if not api_key:
             return jsonify({"error": "系统未配置API Key"}), 500

        # Background generation (Simulation in thread)
        # In production, use Celery
        def run_gen():
            with app.app_context():
                # Get prev content
                prev_chap = Chapter.query.filter_by(novel_id=novel.id, chapter_num=chapter.chapter_num-1).first()
                prev_text = prev_chap.content if prev_chap else ""
                
                gen = NovelGenerator(api_key, provider=provider)
                def on_progress(text):
                    chapter.content = text
                    db.session.commit()
                content = gen.generate_chapter_streaming(
                    novel_info={'type': novel.type, 'theme': novel.theme, 'outline': novel.outline},
                    chapter_info={'num': chapter.chapter_num, 'title': chapter.title, 'summary': chapter.summary},
                    prev_content=prev_text,
                    on_progress=on_progress
                )
                
                word_count = len(content)
                cost = max(1, (int(word_count) + 2) // 3)
                
                # Update DB
                chapter.content = content
                chapter.word_count = word_count
                chapter.cost = cost
                chapter.status = 'completed'
                
                # Deduct balance
                user = User.query.get(novel.user_id)
                user.balance -= cost
                db.session.commit()

        chapter.status = 'generating'
        db.session.commit()
        GEN_START_TIMES[chapter.id] = datetime.utcnow()
        threading.Thread(target=run_gen).start()
        
        return jsonify({"status": "started", "message": "生成任务已提交"})

    @app.route('/chapter_status/<int:chapter_id>')
    @login_required
    def chapter_status(chapter_id):
        chapter = Chapter.query.get_or_404(chapter_id)
        eta = None
        if chapter.status == 'generating':
            started = GEN_START_TIMES.get(chapter_id)
            if started:
                elapsed = (datetime.utcnow() - started).total_seconds()
                expected = 75
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

    @app.route('/recharge', methods=['GET', 'POST'])
    @login_required
    def recharge():
        if request.method == 'POST':
            amount = int(float(request.form.get('amount')))
            current_user.balance += amount
            db.session.commit()
            flash(f'充值成功，当前Token：{current_user.token_balance}')
            return redirect(url_for('dashboard'))
        return render_template('recharge.html')

    def _parse_outline_text(text):
        items = []
        pattern_cn = re.finditer(r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)", text)
        for m in pattern_cn:
            full_title_part = m.group(1).strip()
            chap_num = int(m.group(2))
            title_only = (m.group(3) or "").strip()
            content_part = (m.group(4) or "").strip()
            title_clean = re.sub(r"^第\d+章\s*", "", full_title_part).strip()
            if title_only:
                title_clean = title_only
            items.append({"chapter": chap_num, "title": title_clean, "summary": content_part})
        if not items:
            pattern_ch = re.finditer(r"(?:Ch(?:apter)?\.?\s*)(\d+)\s*([^\n:：]*?)\s*[:：]\s*([\s\S]*?)(?=(?:\n\s*(?:Ch(?:apter)?\.?\s*\d+|第\s*\d+\s*章))|$)", text, re.IGNORECASE)
            for m in pattern_ch:
                chap_num = int(m.group(1))
                title_only = (m.group(2) or "").strip()
                content_part = (m.group(3) or "").strip()
                items.append({"chapter": chap_num, "title": title_only, "summary": content_part})
        items.sort(key=lambda x: x["chapter"])
        return items

    def _parse_and_save_chapters(novel, text):
        items = _parse_outline_text(text)
        for it in items:
            chap = Chapter(
                novel_id=novel.id,
                chapter_num=it["chapter"],
                title=it["title"],
                summary=it["summary"]
            )
            db.session.add(chap)
        db.session.commit()

    @app.post('/api/parse_outline')
    def api_parse_outline():
        data = request.get_json(silent=True) or {}
        text = data.get('outline', '')
        if not text:
            return jsonify({"error": "empty outline"}), 400
        items = _parse_outline_text(text)
        return jsonify({"chapters": items})

    @app.post('/parse_outline')
    def parse_outline():
        data = request.get_json(silent=True) or {}
        text = data.get('outline', '')
        if not text:
            return jsonify({"error": "empty outline"}), 400
        items = _parse_outline_text(text)
        return jsonify({"chapters": items})

    with app.app_context():
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        auto_create = os.environ.get("AUTO_CREATE_TABLES") or cfg.get("auto_create_tables")
        if (uri.startswith("sqlite:")) or (str(auto_create).lower() in ("1", "true", "yes", "y")):
            db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

