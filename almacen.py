"""Persistencia ligera en SQLite (WAL): jobs, feedback y metricas de satisfaccion."""
import sqlite3
import time
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "datos.db"


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init_db() -> None:
    with conectar() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                proyecto TEXT NOT NULL,
                entrada TEXT NOT NULL,
                modelo TEXT,
                titulo TEXT,
                params_json TEXT,
                guion_json TEXT,
                video_path TEXT,
                duracion REAL,
                estado TEXT DEFAULT 'en_cola',
                error TEXT,
                creado TEXT
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                proyecto TEXT NOT NULL,
                puntaje INTEGER NOT NULL,
                comentario TEXT DEFAULT '',
                creado TEXT
            );
            """
        )


def _ahora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def crear_job(job_id: str, proyecto: str, entrada: str, modelo: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO jobs (id, proyecto, entrada, modelo, estado, creado) VALUES (?,?,?,?,?,?)",
            (job_id, proyecto, entrada, modelo, "en_cola", _ahora()),
        )


def actualizar_job(job_id: str, **campos) -> None:
    if not campos:
        return
    sets = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*campos.values(), job_id))


def obtener_job(job_id: str):
    with conectar() as con:
        fila = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(fila) if fila else None


def guardar_feedback(job_id: str, proyecto: str, puntaje: int, comentario: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO feedback (job_id, proyecto, puntaje, comentario, creado) VALUES (?,?,?,?,?)",
            (job_id, proyecto, puntaje, comentario, _ahora()),
        )


def feedback_del_proyecto(proyecto: str) -> list:
    """[(puntaje, comentario), ...] en orden cronologico, para el director."""
    with conectar() as con:
        filas = con.execute(
            "SELECT puntaje, comentario FROM feedback WHERE proyecto=? ORDER BY id",
            (proyecto,),
        ).fetchall()
    return [(f["puntaje"], f["comentario"] or "") for f in filas]


def metricas() -> dict:
    """Promedio global y promedio de las ultimas 3 iteraciones por proyecto.
    La meta del MVP es promedio > 4/5 despues de 3 iteraciones."""
    with conectar() as con:
        global_row = con.execute(
            "SELECT COUNT(*) n, AVG(puntaje) prom FROM feedback"
        ).fetchone()
        proyectos = [r["proyecto"] for r in con.execute(
            "SELECT DISTINCT proyecto FROM feedback ORDER BY proyecto"
        ).fetchall()]
        por_proyecto = {}
        for p in proyectos:
            ult = con.execute(
                "SELECT puntaje FROM feedback WHERE proyecto=? ORDER BY id DESC LIMIT 3",
                (p,),
            ).fetchall()
            puntajes = [u["puntaje"] for u in ult]
            por_proyecto[p] = {
                "prom_ultimas3": round(sum(puntajes) / len(puntajes), 2),
                "iteraciones": len(puntajes),
                "meta_ok": len(puntajes) >= 3 and sum(puntajes) / len(puntajes) > 4,
            }
    return {
        "total_feedbacks": global_row["n"] or 0,
        "promedio_global": round(global_row["prom"], 2) if global_row["prom"] else None,
        "por_proyecto": por_proyecto,
        "meta": "promedio > 4/5 tras 3 iteraciones",
    }


def historial(limite: int = 20) -> list:
    with conectar() as con:
        filas = con.execute(
            """
            SELECT j.id, j.proyecto, j.titulo, j.duracion, j.estado, j.creado,
                   (SELECT puntaje FROM feedback f WHERE f.job_id = j.id LIMIT 1) AS puntaje
            FROM jobs j ORDER BY j.creado DESC LIMIT ?
            """,
            (limite,),
        ).fetchall()
    return [dict(f) for f in filas]
