from .extensions import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(191), unique=True)
    phone = db.Column(db.String(32), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.SmallInteger, nullable=False, default=1)
    token_balance = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)
    novels = db.relationship('Novel', backref='author', lazy=True)

    @property
    def balance(self):
        return float(self.token_balance or 0)

    @balance.setter
    def balance(self, value):
        self.token_balance = int(float(value or 0))

class Novel(db.Model):
    __tablename__ = 'novels'

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    user_id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(150), default="Untitled")
    type = db.Column(db.String(50))
    theme = db.Column(db.String(500))
    outline = db.Column(db.Text) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chapters = db.relationship('Chapter', backref='novel', lazy=True)

class Chapter(db.Model):
    __tablename__ = 'chapters'

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    novel_id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), db.ForeignKey('novels.id'), nullable=False)
    chapter_num = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(150))
    summary = db.Column(db.Text)
    content = db.Column(db.Text) 
    word_count = db.Column(db.Integer, default=0)
    cost = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending') # pending, generating, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

