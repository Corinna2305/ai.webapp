# -*- coding: utf-8 -*-
"""
AI Multi-Modello Web App
Web application per generare immagini con diverse API AI
"""
import os
try:
    from dotenv import load_dotenv
except ImportError:
    # Fallback: app can still run using Render environment variables.
    def load_dotenv():
        return False

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from datetime import datetime
import bcrypt
import requests
import random
import re
import logging

# Carica variabili d'ambiente
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================
ALLOW_SHARED_KEYS = os.getenv("ALLOW_SHARED_KEYS", "True").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_webapp.db")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# SQLite requires check_same_thread=False; Postgres must not receive that option.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)
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
def is_valid_email(email: str) -> bool:
    """Valida il formato email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(p: str) -> str:
    """Hash password con bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(p.encode('utf-8'), salt).decode('utf-8')

def check_password(p: str, h: str) -> bool:
    """Verifica password vs hash"""
    try:
        return bcrypt.checkpw(p.encode('utf-8'), h.encode('utf-8'))
    except Exception as e:
        logger.error(f"Password check error: {e}")
        return False

def get_db():
    """Dependency per ottenere sessione DB"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_shared_key(db: Session, provider: str) -> str | None:
    """Recupera una chiave API condivisa"""
    if not ALLOW_SHARED_KEYS:
        return None
    try:
        users = db.query(User).filter(User.shared == 1).all()
        pool = []
        for u in users:
            key = getattr(u, f"{provider}_key", None)
            if key:
                pool.append(key)
        return random.choice(pool) if pool else None
    except Exception as e:
        logger.error(f"Error getting shared key: {e}")
        return None

# ⚠️ Placeholder immagini (sostituibile con API vere)
def generate_image_placeholder(prompt: str, provider: str) -> str:
    """Genera URL placeholder per immagine"""
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
    """Endpoint login/register"""
    try:
        # Validazione input
        if not is_valid_email(email):
            return "<h2>❌ Email non valida</h2><a href='/'>Riprova</a>"
        
        if len(password) < 4:
            return "<h2>❌ Password troppo corta (min 4 caratteri)</h2><a href='/'>Riprova</a>"
        
        db = SessionLocal()
        
        try:
            user = db.query(User).filter(User.email == email).first()

            if not user:
                # Nuovo utente: registrazione
                user = User(
                    email=email,
                    password=hash_password(password),
                    credits=10,
                    last_login=datetime.utcnow()
                )
                db.add(user)
                logger.info(f"New user registered: {email}")
            else:
                # Utente esistente: verifica password
                if not check_password(password, user.password):
                    logger.warning(f"Failed login attempt: {email}")
                    return "<h2>❌ Password errata</h2><a href='/'>Torna</a>"
                
                # Aggiorna last_login
                user.last_login = datetime.utcnow()
                logger.info(f"User login: {email}")
            
            db.commit()
            return f"<h2>✅ Login OK</h2><a href='/dashboard?email={email}'>Vai al dashboard</a>"
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Login error: {e}")
        return f"<h2>❌ Errore: {str(e)}</h2><a href='/'>Torna</a>"

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(email: str):
    """Pagina dashboard utente"""
    try:
        if not is_valid_email(email):
            return "<h2>❌ Email non valida</h2><a href='/'>Torna</a>"
        
        db = SessionLocal()
        
        try:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                return "<h2>❌ Utente non trovato</h2><a href='/'>Torna</a>"

            imgs = db.query(Image).filter(Image.email == email).all()
            images_html = "".join([f"<img src='{i.url}' width='128' alt='Generated'>" for i in imgs])

            return f"""
            <h2>Dashboard - {email}</h2>
            <p><strong>Crediti disponibili:</strong> {user.credits}</p>
            
            <h3>🔑 Chiavi API (opzionale)</h3>
            <form action="/save_keys" method="post">
                <input type="hidden" name="email" value="{email}">
                <label>OpenAI key: <input name="openai_key" type="password" placeholder="sk-..."></label><br>
                <label>Stability key: <input name="stability_key" type="password" placeholder="sk-..."></label><br>
                <label>Nano Banana key: <input name="nano_key" type="password" placeholder="key-..."></label><br>
                <label><input type="checkbox" name="shared" value="1"> Condividi token pubblicamente?</label><br>
                <button type="submit">Salva API key</button>
            </form>

            <h3>🎨 Genera immagine</h3>
            <form action="/generate" method="post">
                <input type="hidden" name="email" value="{email}">
                <label>Prompt: <input name="prompt" required maxlength="500" placeholder="Descrivi l'immagine..."></label><br>
                <label>Provider:
                    <select name="provider">
                        <option value="openai">OpenAI DALL-E</option>
                        <option value="stability">Stability AI</option>
                        <option value="nano">Nano Banana</option>
                    </select>
                </label>
                <button type="submit">Genera</button>
            </form>

            <h3>📸 Le tue immagini</h3>
            {images_html if images_html else '<p>Nessuna immagine ancora. Generane una!</p>'}
            
            <hr>
            <a href="/">Logout</a>
            """
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return f"<h2>❌ Errore: {str(e)}</h2><a href='/'>Torna</a>"

@app.post("/save_keys", response_class=HTMLResponse)
def save_keys(
    email: str = Form(...),
    openai_key: str = Form(None),
    stability_key: str = Form(None),
    nano_key: str = Form(None),
    shared: str = Form(None)
):
    """Salva le chiavi API dell'utente"""
    try:
        if not is_valid_email(email):
            return "<h2>❌ Email non valida</h2><a href='/'>Torna</a>"
        
        db = SessionLocal()
        
        try:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                return "<h2>❌ Utente non trovato</h2><a href='/'>Torna</a>"
            
            # Salva solo se fornita, altrimenti None
            user.openai_key = openai_key if openai_key else None
            user.stability_key = stability_key if stability_key else None
            user.nano_key = nano_key if nano_key else None
            user.shared = 1 if shared else 0
            
            db.commit()
            logger.info(f"API keys updated for user: {email}")
            
            return f"<h2>✅ API key salvate</h2><a href='/dashboard?email={email}'>Torna al dashboard</a>"
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Save keys error: {e}")
        return f"<h2>❌ Errore: {str(e)}</h2><a href='/dashboard?email={email}'>Torna</a>"

@app.post("/generate", response_class=HTMLResponse)
def generate(prompt: str = Form(...), provider: str = Form(...), email: str = Form(...)):
    """Genera una nuova immagine"""
    try:
        # Validazione input
        if not is_valid_email(email):
            return "<h2>❌ Email non valida</h2><a href='/'>Torna</a>"
        
        if not prompt or len(prompt.strip()) == 0:
            return "<h2>❌ Prompt vuoto</h2><a href='/dashboard?email={email}'>Torna</a>"
        
        if len(prompt) > 500:
            return "<h2>❌ Prompt troppo lungo (max 500 caratteri)</h2><a href='/dashboard?email={email}'>Torna</a>"
        
        provider = provider.lower()
        if provider not in ["openai", "stability", "nano"]:
            return "<h2>❌ Provider non valido</h2><a href='/dashboard?email={email}'>Torna</a>"
        
        db = SessionLocal()
        
        try:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                return "<h2>❌ Utente non trovato</h2><a href='/'>Torna</a>"

            # Controlla crediti
            if user.credits <= 0:
                return f"<h2>❌ Crediti finiti</h2><p>Contattic l'admin</p><a href='/dashboard?email={email}'>Torna</a>"

            # Recupera chiave API
            api_key = getattr(user, f"{provider}_key", None) or get_shared_key(db, provider)

            if not api_key:
                return f"<h2>⚠️ Nessuna API key disponibile per {provider}</h2><a href='/dashboard?email={email}'>Torna</a>"

            # Decrementa crediti
            user.credits -= 1
            
            # TODO: Implementare richiesta vera all'API
            # Per ora usiamo placeholder
            url = generate_image_placeholder(prompt, provider)

            # Salva record nel database
            img = Image(
                email=email,
                prompt=prompt,
                provider=provider,
                url=url,
                created_at=datetime.utcnow()
            )
            db.add(img)
            db.commit()
            
            logger.info(f"Image generated for user: {email}, provider: {provider}")
            
            return f"""
            <h2>✅ Immagine generata!</h2>
            <img src="{url}" width="256" alt="Generated image"><br>
            <p><strong>Crediti rimasti:</strong> {user.credits}</p>
            <a href="/dashboard?email={email}">Torna al dashboard</a>
            """
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Generate error: {e}")
        return f"<h2>❌ Errore nella generazione: {str(e)}</h2><a href='/dashboard?email={email}'>Torna</a>"

# =========================
# AVVIO SERVER
# =========================
if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on http://{HOST}:{PORT}")
    uvicorn.run(
        "appia:app",
        host=HOST,
        port=PORT,
        reload=True
    )