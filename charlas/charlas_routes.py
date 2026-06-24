# ===== AGREGAR A TU main.py DE RAILWAY =====
# Este es el endpoint que recibe datos del formulario de charlas
# Guarda en la tabla confia_postulaciones de Neon

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
import asyncpg
import os

router = APIRouter(prefix="/api/charlas", tags=["charlas"])

class PostulacionCharla(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=120)
    email: EmailStr
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
    calificacion: str = Field(default="no_evaluado", max_length=30)

async def get_neon_pool():
    """Obtener pool de conexiones a Neon PostgreSQL"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")
    
    pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

@router.post("/aplicacion")
async def crear_postulacion(data: PostulacionCharla):
    """
    Guardar nueva postulación de charlas en Neon.
    Validaciones adicionales de seguridad.
    """
    
    # Validaciones adicionales de seguridad
    if len(data.nombre) < 3 or len(data.nombre) > 120:
        raise HTTPException(status_code=400, detail="Nombre inválido")
    
    # Validar teléfono chileno
    tel_clean = data.telefono.replace(" ", "").replace("-", "")
    if not tel_clean.startswith("+56") and not tel_clean.startswith("56"):
        if not (len(tel_clean) == 8 or len(tel_clean) == 9):
            raise HTTPException(status_code=400, detail="Teléfono inválido")
    
    # Validar que no haya HTML/inyección en campos de texto libre
    dangerous_patterns = ['<script', '<iframe', 'javascript:', 'onclick', 'onerror']
    for field in [data.situacion, data.expectativa]:
        if any(pattern in field.lower() for pattern in dangerous_patterns):
            raise HTTPException(status_code=400, detail="Contenido inválido detectado")
    
    try:
        pool = await get_neon_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO confia_postulaciones 
                (nombre, email, telefono, cargo, empresa, rubro, tamano_equipo, 
                 ciudad, modalidad, situacion, expectativa, fuente, estado, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
            ''',
            data.nombre, data.email, data.telefono, data.cargo, data.empresa,
            data.rubro, data.tamano_equipo, data.ciudad, data.modalidad,
            data.situacion, data.expectativa, data.fuente, 'pendiente'
            )
        
        return {
            "ok": True,
            "message": "Postulación guardada exitosamente",
            "email": data.email
        }
    
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Este email ya tiene una postulación pendiente")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar: {str(e)}")
    finally:
        await pool.close()


@router.get("/postulaciones/{estado}")
async def listar_postulaciones(estado: str = "pendiente"):
    """
    Endpoint para Miguel — listar postulaciones por estado
    (pendiente, en_revisión, contactado, rechazado, confirmado)
    Agregar autenticación si es necesario.
    """
    if estado not in ["pendiente", "en_revision", "contactado", "rechazado", "confirmado"]:
        raise HTTPException(status_code=400, detail="Estado inválido")
    
    try:
        pool = await get_neon_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, nombre, email, telefono, empresa, ciudad, 
                       calificacion, estado, created_at
                FROM confia_postulaciones
                WHERE estado = $1
                ORDER BY created_at DESC
            ''', estado)
        
        return {
            "ok": True,
            "estado": estado,
            "total": len(rows),
            "postulaciones": [dict(row) for row in rows]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await pool.close()


# ===== EN TU main.py PRINCIPAL, AGREGA: =====
# app.include_router(router)
