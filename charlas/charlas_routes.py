from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer, DateTime, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import re
import httpx

# ── DATABASE SETUP ──
DATABASE_URL = os.environ.get("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ConfiaPostulaciones(Base):
    __tablename__ = "confia_postulaciones"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    email = Column(String(200), nullable=False, index=True)
    telefono = Column(String(30), nullable=False)
    cargo = Column(String(80), nullable=False)
    empresa = Column(String(200), nullable=False)
    rubro = Column(String(100), nullable=False)
    tamano_equipo = Column(String(30), nullable=False)
    ciudad = Column(String(80), nullable=False)
    modalidad = Column(String(50), default="no_especificada")
    situacion = Column(Text, nullable=True)
    expectativa = Column(Text, nullable=True)
    fuente = Column(String(80), default="no_especificada")
    calificacion = Column(String(30), default="no_evaluado")
    estado = Column(String(30), default="pendiente")
    client_ip = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def enviar_email_resend(nombre: str, email: str, empresa: str):
    """Enviar email de confirmación via Resend"""
    resend_key = os.environ.get("RESEND_API_KEY", "re_c1tpEyD8_NKFusih9vKVQknRAQfmFcWCv")
    from_email = "contacto@miguelmontenegro.com"
    
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>body{{font-family:sans-serif;background:#f0faf4;margin:0;padding:20px}}.card{{max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:40px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}.header{{color:#2D6A4F;font-size:24px;font-weight:700;margin-bottom:20px}}p{{color:#555;line-height:1.6;margin:12px 0}}.footer{{border-top:1px solid #eee;margin-top:30px;padding-top:20px;font-size:12px;color:#999}}</style></head>
<body><div class="card">
<div class="header">¡Gracias por tu interés! ✅</div>
<p>Hola <strong>{nombre}</strong>,</p>
<p>Hemos recibido tu postulación para las charlas "Confía en Ti" desde <strong>{empresa}</strong>.</p>
<p>Nos pondremos en contacto contigo dentro de <strong>48-72 horas</strong> para confirmar la fecha, hora y modalidad de la sesión.</p>
<p style="margin:24px 0;padding:16px;background:#f8faf9;border-left:4px solid #2D6A4F;color:#2D6A4F;">
<strong>Lo que sigue:</strong><br>
• Validaremos disponibilidad<br>
• Te enviaremos propuesta con detalles<br>
• Coordinaremos sesión pre-charla (si aplica)<br>
• ¡A disfrutar de la charla!
</p>
<p>Si tienes dudas antes, puedes responder a este email.</p>
<p>Un abrazo,<br><strong>Miguel Montenegro</strong><br>Coach IAC · Psicólogo</p>
<div class="footer">
© 2024 Miguel Montenegro · Sistema de Charlas "Confía en Ti"<br>
Este email fue enviado porque completaste un formulario de postulación.
</div>
</div></body></html>"""
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": from_email,
                    "to": email,
                    "subject": f"Confirmación de postulación — Charlas Confía en Ti",
                    "html": html_content
                }
            )
        if response.status_code == 200:
            print(f"✓ Email confirmación enviado a {email}")
            return True
        else:
            print(f"✗ Error Resend ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error enviando email: {e}")
        return False

# ── ROUTER ──
router = APIRouter(prefix="/api/charlas", tags=["charlas"])

class PostulacionCharla(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=120)
    email: str = Field(..., max_length=200)
    telefono: str = Field(..., min_length=8, max_length=30)
    cargo: str = Field(..., max_length=80)
    empresa: str = Field(..., max_length=200)
    rubro: str = Field(..., max_length=100)
    tamano_equipo: str = Field(..., max_length=30)
    ciudad: str = Field(..., max_length=80)
    modalidad: str = Field(default="no_especificada", max_length=50)
    situacion: str = Field(..., max_length=500)
    expectativa: str = Field(..., max_length=500)
    fuente: str = Field(default="no_especificada", max_length=80)
    clientIp: str = Field(default="", max_length=50)

def validar_email(email: str) -> bool:
    """Validar formato email básico"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def sanitizar_texto(texto: str) -> str:
    """Remover caracteres peligrosos"""
    dangerous_patterns = ['<script', '<iframe', 'javascript:', 'onclick', 'onerror', '<img', '<svg']
    for pattern in dangerous_patterns:
        if pattern.lower() in texto.lower():
            raise ValueError("Contenido inválido")
    return texto.strip()

@router.post("/aplicacion")
async def crear_postulacion(data: PostulacionCharla, db: Session = Depends(get_db)):
    """
    POST /api/charlas/aplicacion
    Guardar postulación + enviar email
    Devuelve JSON para que el frontend muestre modal
    """
    
    try:
        # Validar email
        if not validar_email(data.email):
            raise HTTPException(status_code=400, detail="Email inválido")
        
        # Sanitizar campos de texto
        try:
            nombre_limpio = sanitizar_texto(data.nombre)
            situacion_limpia = sanitizar_texto(data.situacion)
            expectativa_limpia = sanitizar_texto(data.expectativa)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Crear registro en BD
        postulacion = ConfiaPostulaciones(
            nombre=nombre_limpio,
            email=data.email.lower().strip(),
            telefono=data.telefono,
            cargo=data.cargo,
            empresa=data.empresa,
            rubro=data.rubro,
            tamano_equipo=data.tamano_equipo,
            ciudad=data.ciudad,
            modalidad=data.modalidad,
            situacion=situacion_limpia,
            expectativa=expectativa_limpia,
            fuente=data.fuente,
            client_ip=data.clientIp,
            estado="pendiente"
        )
        
        db.add(postulacion)
        db.commit()
        db.refresh(postulacion)
        
        # Enviar email de confirmación (background)
        await enviar_email_resend(nombre_limpio, data.email, data.empresa)
        
        # Devolver JSON
        return {
            "ok": True,
            "message": "Postulación guardada exitosamente",
            "nombre": nombre_limpio,
            "email": data.email,
            "id": postulacion.id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error crear postulación: {e}")
        raise HTTPException(status_code=500, detail=f"Error al guardar: {str(e)}")

@router.get("/postulaciones/{estado}")
async def listar_postulaciones(estado: str = "pendiente", db: Session = Depends(get_db)):
    """
    GET /api/charlas/postulaciones/{estado}
    Listar postulaciones por estado (pendiente, en_revision, contactado, rechazado, confirmado)
    """
    
    estados_validos = ["pendiente", "en_revision", "contactado", "rechazado", "confirmado"]
    if estado not in estados_validos:
        raise HTTPException(status_code=400, detail=f"Estado debe ser uno de: {', '.join(estados_validos)}")
    
    try:
        postulaciones = db.query(ConfiaPostulaciones)\
            .filter(ConfiaPostulaciones.estado == estado)\
            .order_by(ConfiaPostulaciones.created_at.desc())\
            .all()
        
        return {
            "ok": True,
            "estado": estado,
            "total": len(postulaciones),
            "postulaciones": [
                {
                    "id": p.id,
                    "nombre": p.nombre,
                    "email": p.email,
                    "telefono": p.telefono,
                    "cargo": p.cargo,
                    "empresa": p.empresa,
                    "ciudad": p.ciudad,
                    "rubro": p.rubro,
                    "tamano_equipo": p.tamano_equipo,
                    "modalidad": p.modalidad,
                    "fuente": p.fuente,
                    "calificacion": p.calificacion,
                    "estado": p.estado,
                    "created_at": p.created_at.isoformat() if p.created_at else None
                }
                for p in postulaciones
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
