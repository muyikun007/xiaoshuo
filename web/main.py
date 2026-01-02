import os
import re
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Depends, HTTPException, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel

from ai_service import AIService

# --- Configuration ---
DATABASE_URL = "sqlite:///./novel_web.db"
templates = Jinja2Templates(directory="templates")
ai_service = AIService()

# --- Database Setup ---
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    balance = Column(Integer, default=10000) # 初始赠送10000书币 (约10章)
    created_at = Column(DateTime, default=datetime.now)

class Novel(Base):
    __tablename__ = "novels"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="未命名")
    novel_type = Column(String)
    theme = Column(String)
    outline = Column(Text, default="") # 完整大纲文本
    created_at = Column(DateTime, default=datetime.now)
    
    chapters = relationship("Chapter", back_populates="novel")

class Chapter(Base):
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True, index=True)
    novel_id = Column(Integer, ForeignKey("novels.id"))
    chapter_num = Column(Integer)
    title = Column(String)
    summary = Column(Text)
    content = Column(Text, default="")
    status = Column(String, default="pending") # pending, generating, completed, error
    cost = Column(Integer, default=0) # 消耗书币

    novel = relationship("Novel", back_populates="chapters")

Base.metadata.create_all(bind=engine)

# --- FastAPI App ---
app = FastAPI(title="AI Novel Web")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Helper Functions ---
def parse_chapters_from_outline(outline_text: str):
    """从大纲文本中解析章节列表"""
    matches = list(re.finditer(r"(第\s*(\d+)\s*章\s*(.*?))\s*[:：\n]\s*([\s\S]*?)(?=(?:\n\s*第\s*\d+\s*章)|$)", outline_text))
    chapters = []
    for m in matches:
        try:
            c_num = int(m.group(2))
            title = m.group(3).strip()
            summary = m.group(4).strip()[:500] # 限制长度
            chapters.append({"num": c_num, "title": title, "summary": summary})
        except:
            continue
    return chapters

def generate_chapter_task(chapter_id: int, provider: str):
    """后台任务：异步生成章节内容"""
    db = SessionLocal()
    try:
        chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not chapter:
            return
        
        novel = chapter.novel
        
        # 获取上一章内容
        prev_chap = db.query(Chapter).filter(
            Chapter.novel_id == novel.id, 
            Chapter.chapter_num == chapter.chapter_num - 1
        ).first()
        prev_content = prev_chap.content if prev_chap else ""
        
        try:
            content = ai_service.generate_chapter(
                provider, 
                novel.novel_type, 
                novel.theme, 
                novel.outline, 
                chapter.chapter_num, 
                chapter.title, 
                chapter.summary,
                prev_content
            )
            chapter.content = content
            chapter.status = "completed"
        except Exception as e:
            chapter.status = "error"
            # 失败退款
            user = db.query(User).filter(User.id == novel.user_id).first()
            user.balance += chapter.cost
            chapter.content = f"生成失败: {str(e)}"
            
        db.commit()
    finally:
        db.close()

# --- Routes: Pages ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    # Mock simple user login (ID=1)
    user = db.query(User).filter(User.id == 1).first()
    if not user:
        user = User(username="demo_user", balance=5000)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    novels = db.query(Novel).filter(Novel.user_id == user.id).order_by(Novel.id.desc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "novels": novels})

@app.get("/novel/{novel_id}", response_class=HTMLResponse)
async def view_novel(request: Request, novel_id: int, db: Session = Depends(get_db)):
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return templates.TemplateResponse("novel.html", {"request": request, "novel": novel})

@app.get("/api/novel/{novel_id}/status")
async def check_novel_status(novel_id: int, db: Session = Depends(get_db)):
    """轮询接口：获取最新章节状态"""
    novel = db.query(Novel).filter(Novel.id == novel_id).first()
    if not novel:
         return JSONResponse({"status": "error"}, status_code=404)
         
    chapters_status = []
    for c in novel.chapters:
        chapters_status.append({
            "id": c.id,
            "status": c.status,
            "content": c.content if c.status == "completed" else ""
        })
    return JSONResponse({"chapters": chapters_status})

@app.get("/pay", response_class=HTMLResponse)
async def pay_page(request: Request, db: Session = Depends(get_db)):
    user = db.query(User).first()
    return templates.TemplateResponse("pay.html", {"request": request, "user": user})

# --- Routes: Actions ---
@app.post("/api/create_from_outline")
async def create_from_outline(
    type: str = Form(...), 
    theme: str = Form(...), 
    outline: str = Form(...),
    db: Session = Depends(get_db)
):
    """仅通过粘贴大纲创建"""
    user = db.query(User).first()
    
    # 解析大纲检查有效性
    parsed_chaps = parse_chapters_from_outline(outline)
    if not parsed_chaps:
        return JSONResponse({"status": "error", "msg": "无法解析大纲，请确保包含'第X章'格式"}, status_code=400)

    # 创建记录
    novel = Novel(
        user_id=user.id, 
        novel_type=type, 
        theme=theme, 
        title=f"{type}-{datetime.now().strftime('%H%M')}",
        outline=outline
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)
    
    # 存入章节
    for pc in parsed_chaps:
        db_chap = Chapter(
            novel_id=novel.id,
            chapter_num=pc['num'],
            title=pc['title'],
            summary=pc['summary']
        )
        db.add(db_chap)
    
    db.commit()
    return RedirectResponse(url=f"/novel/{novel.id}", status_code=303)

@app.post("/api/generate_chapter/{chapter_id}")
async def generate_chapter_api(
    chapter_id: int, 
    background_tasks: BackgroundTasks,
    provider: str = Form("Gemini"), 
    db: Session = Depends(get_db)
):
    """异步生成章节接口"""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not chapter:
        return JSONResponse({"status": "error", "msg": "Chapter not found"}, status_code=404)
    
    if chapter.status in ["generating", "completed"]:
        return JSONResponse({"status": "error", "msg": "Chapter is already processing or completed"}, status_code=400)

    novel = chapter.novel
    user = db.query(User).filter(User.id == novel.user_id).first()
    
    # 扣费逻辑
    COST = 1000
    if user.balance < COST:
        return JSONResponse({"status": "error", "msg": "余额不足，请充值"}, status_code=400)
        
    user.balance -= COST
    chapter.status = "generating"
    chapter.cost = COST
    db.commit()
    
    # 放入后台任务队列
    background_tasks.add_task(generate_chapter_task, chapter_id, provider)
    
    return JSONResponse({"status": "success", "msg": "任务已提交"})

@app.post("/api/topup")
async def topup(amount: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).first()
    coins = amount * 1000
    user.balance += coins
    db.commit()
    return RedirectResponse(url="/pay?success=1", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
