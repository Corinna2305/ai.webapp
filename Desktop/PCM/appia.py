# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""
import os
import fastapi
import uvicorn

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import bcrypt, requests, random

# =========================
# CONFIG
# =========================
ALLOW_SHARED_KEYS = True  # ⚠️ modalità LAB: permette usare token di altri utenti

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_webapp.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =========================
# MODELLI DB
# =========================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    credits = Column(Integer, default=10)
    last_login = Column(DateTime)
    openai_key = Column(String, nullable=True)
    stability_key = Column(String, nullable=True)
    nano_key = Column(String, nullable=True)
    shared = Column(Integer, default=0)  # 1 = condivido le mie key

class Image(Base):
    __tablename__ = "images"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    prompt = Column(Text)
    provider = Column(String)
    url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# =========================
# APP
# =========================
app = FastAPI(title="AI Multi-Modello PRO")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# =========================
# UTILS
# =========================
def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def check_password(p, h):
    return bcrypt.checkpw(p.encode(), h.encode())

def get_shared_key(db, provider):
    if not ALLOW_SHARED_KEYS:
        return None
    users = db.query(User).filter(User.shared == 1).all()
    pool = []
    for u in users:
        key = getattr(u, f"{provider}_key")
        if key:
            pool.append(key)
    return random.choice(pool) if pool else None

# ⚠️ Placeholder immagini (sostituibile con API vere)
def generate_image_placeholder(prompt, provider):
    safe_prompt = prompt.replace(" ", "+")[:40]
    return f"https://placehold.co/512x512?text={provider.upper()}+{safe_prompt}"

# =========================
# ROUTES
# =========================
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <h1>AI Multi-Modello PRO</h1>
    <form action="/login" method="post">
        Email: <input type="email" name="email" required><br>
        Password: <input type="password" name="password" required><br>
        <button>Login / Register</button>
    </form>
    """

@app.post("/login", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        user = User(
            email=email,
            password=hash_password(password),
            credits=10,
            last_login=datetime.utcnow()
        )
        db.add(user)
        db.commit()
    else:
        if not check_password(password, user.password):
            return "<h2>Password errata</h2><a href='/'>Torna</a>"

    return f"<h2>Login OK</h2><a href='/dashboard?email={email}'>Vai al dashboard</a>"

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(email: str):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return "<h2>Utente non trovato</h2><a href='/'>Torna</a>"

    imgs = db.query(Image).filter(Image.email == email).all()

    images_html = "".join([f"<img src='{i.url}' width='128'>" for i in imgs])

    return f"""
    <h2>Dashboard</h2>
    <p>Email: {email}</p>
    <p>Crediti: {user.credits}</p>

<h3>API Key (opzionale)</h3>
    <form action="/save_keys" method="post">
        <input type="hidden" name="email" value="{email}">
        OpenAI key: <input name="openai_key"><br>
        Stability key: <input name="stability_key"><br>
        Nano key: <input name="nano_key"><br>
        Condividi token pubblicamente? <input type="checkbox" name="shared" value="1"><br>
        <button>Salva API key</button>
    </form>

    <h3>Genera immagine</h3>
    <form action="/generate" method="post">
        <input type="hidden" name="email" value="{email}">
        Prompt: <input name="prompt" required><br>
        Provider:
        <select name="provider">
            <option value="openai">OpenAI</option>
            <option value="stability">Stability</option>
            <option value="nano">Nano Banana</option>
        </select>
        <button>Genera</button>
    </form>

    <h3>Le tue immagini</h3>
    {images_html}
    """

@app.post("/save_keys", response_class=HTMLResponse)
def save_keys(
    email: str = Form(...),
    openai_key: str = Form(None),
    stability_key: str = Form(None),
    nano_key: str = Form(None),
    shared: str = Form(None)
):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.openai_key = openai_key or None
    user.stability_key = stability_key or None
    user.nano_key = nano_key or None
    user.shared = 1 if shared else 0
    db.commit()
    return f"<h2>API key salvate</h2><a href='/dashboard?email={email}'>Torna al dashboard</a>"

@app.post("/generate", response_class=HTMLResponse)
def generate(prompt: str = Form(...), provider: str = Form(...), email: str = Form(...)):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()

    if user.credits <= 0:
        return f"<h2>Crediti finiti</h2><a href='/dashboard?email={email}'>Torna</a>"

    api_key = getattr(user, f"{provider}_key") or get_shared_key(db, provider)

    if not api_key:
        return f"<h2>Nessuna API key disponibile</h2><a href='/dashboard?email={email}'>Torna</a>"

    user.credits -= 1
    url = generate_image_placeholder(prompt, provider)

    img = Image(email=email, prompt=prompt, provider=provider, url=url)
    db.add(img)
    db.commit()
    

    return f"""
    <h2>Immagine generata!</h2>
    <img src="{url}" width="256"><br>
    <a href="/dashboard?email={email}">Torna al dashboard</a>
    """

# =========================
# AVVIO SERVER
# =========================

"""if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app",
            host="127.0.0.1", port=8000, reload=False)"""