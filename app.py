"""VideoGen Orchestrator - servidor que orquesta: voz/prompt -> guion (LLM) ->
imagenes (difusion) -> narracion (TTS) -> video final (ffmpeg)."""
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import clips
import director
import imagenes
import recursos
import renderizar
import subtitulos
import transcribir
import voz
from almacen import (actualizar_job, crear_job, feedback_del_proyecto, guardar_feedback,
                     historial, init_db, metricas, obtener_job)
from util import cargar_config, log

CONFIG = cargar_config()
BASE = Path(__file__).parent
SALIDAS = BASE / "salidas"
SALIDAS.mkdir(exist_ok=True)

_JOBS = {}
_COLA: queue.Queue = queue.Queue()
_modelos_cache = {"t": 0.0, "lista": []}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    threading.Thread(target=_worker, daemon=True).start()
    yield


app = FastAPI(title="VideoGen Orchestrator", lifespan=lifespan)
app.mount("/salidas", StaticFiles(directory=SALIDAS), name="salidas")


class PedidoGenerar(BaseModel):
    proyecto: str = "general"
    texto: str
    estilo: str = ""
    modelo: str = ""


class PedidoFeedback(BaseModel):
    job_id: str
    puntaje: int
    comentario: str = ""


# ---------------------------------------------------------------- pipeline

def _worker() -> None:
    while True:
        job_id = _COLA.get()
        try:
            _ejecutar(job_id)
        finally:
            _COLA.task_done()


def _ejecutar(job_id: str) -> None:
    job = _JOBS[job_id]
    datos = job["datos"]
    cfg = cargar_config()
    dir_sal = SALIDAS / job_id
    dir_sal.mkdir(parents=True, exist_ok=True)
    actual = None

    def marcar(texto: str) -> None:
        nonlocal actual
        actual = {"texto": texto, "estado": "curso", "detalle": ""}
        job["pasos"].append(actual)

    def ok(detalle: str = "") -> None:
        if actual is not None:
            actual["estado"] = "ok"
            actual["detalle"] = detalle

    def detalle_sub(extra: str) -> None:
        if actual is not None:
            actual["detalle"] = extra

    try:
        texto = datos["texto"].strip()
        modelo = datos.get("modelo") or cfg["modelo_texto"]
        actualizar_job(job_id, estado="procesando")

        marcar(f"Director ajustando parametros (modelo {modelo})")
        feedbacks = feedback_del_proyecto(datos["proyecto"])
        plan = director.planear(texto, datos.get("estilo", ""), feedbacks, modelo)
        extra = f"{plan['cantidad_escenas']} escenas, ritmo {plan['ritmo']}"
        if feedbacks:
            extra += f" | corrige: {plan['ajustes_por_feedback'][:100]}"
        ok(extra)

        marcar("Escribiendo el guion")
        con_clips = clips.habilitado()
        guion = director.guion(texto, plan, modelo, con_clips=con_clips)
        ok(guion["titulo"])

        escenas = guion["escenas"][: cfg["max_escenas"]]
        vertical = cfg["aspecto"] == "vertical"
        w_img, h_img = (768, 1344) if vertical else (1344, 768)

        marcar(f"Generando {len(escenas)} visuales"
               + (" (imagenes + clips de banco)" if con_clips else ""))
        conc = recursos.concurrencia()
        rutas = [None] * len(escenas)
        tipos = ["imagen"] * len(escenas)

        def _visual(i: int) -> tuple:
            esc = escenas[i]
            if con_clips and esc.get("medio") == "video":
                clip = clips.buscar(esc.get("query_video", ""))
                if clip:
                    return i, str(clip), "clip"
            return i, str(imagenes.generar(esc["prompt_imagen"], w_img, h_img)), "imagen"

        with ThreadPoolExecutor(max_workers=conc) as ex:
            futuros = {ex.submit(_visual, i): i for i in range(len(escenas))}
            for fut in as_completed(futuros):
                i, ruta, tipo = fut.result()
                rutas[i], tipos[i] = ruta, tipo
                detalle_sub(f"{sum(r is not None for r in rutas)}/{len(escenas)}"
                            f" - escala: {conc} en paralelo")
        n_clips = tipos.count("clip")
        ok(f"{len(escenas) - n_clips} imagenes + {n_clips} clips"
           if con_clips else f"{len(escenas)} imagenes (cache + FreeLLMAPI/Pollinations)")

        marcar("Generando la narracion (voz)")
        for i, esc in enumerate(escenas):
            voz.narrar(esc["narracion"], dir_sal / f"voz_{i:02d}.mp3")
            detalle_sub(f"{i + 1}/{len(escenas)}")
        ok(f"proveedor: {voz.proveedor()}")

        marcar("Renderizando el video")
        piezas = [{"imagen": rutas[i],
                   "clip": rutas[i] if tipos[i] == "clip" else None,
                   "audio": str(dir_sal / f"voz_{i:02d}.mp3"),
                   "dur": voz.duracion(dir_sal / f"voz_{i:02d}.mp3") + 0.7}
                  for i in range(len(escenas))]
        w, h = (1080, 1920) if vertical else (1920, 1080)

        def progreso(i: int, n: int) -> None:
            detalle_sub(f"escena {i}/{n}")

        subs = None
        if cfg.get("subtitulos", True):
            subs = subtitulos.armar(escenas, piezas, dir_sal / "subs.ass")
        final, dur_total = renderizar.renderizar(piezas, dir_sal, w, h, progreso,
                                                 subtitulos=subs)
        ok(f"{dur_total:.0f}s a {w}x{h}" + (" con subtitulos" if subs else ""))

        job.update(estado="listo", video_url=f"/salidas/{job_id}/final.mp4",
                   titulo=guion["titulo"], duracion=round(dur_total, 1),
                   guion=guion, plan=plan)
        actualizar_job(job_id, estado="listo", titulo=guion["titulo"],
                       params_json=json.dumps(plan, ensure_ascii=False),
                       guion_json=json.dumps(guion, ensure_ascii=False),
                       video_path=str(final), duracion=dur_total)
        log(f"[{job_id[:8]}] LISTO {guion['titulo']} ({dur_total:.0f}s)")
    except Exception as e:  # noqa: BLE001 - el error viaja a la UI
        log(f"[{job_id[:8]}] ERROR: {e}")
        if actual is not None:
            actual["estado"] = "error"
            actual["detalle"] = str(e)[:300]
        job["estado"] = "error"
        job["error"] = str(e)
        actualizar_job(job_id, estado="error", error=str(e)[:2000])


# ---------------------------------------------------------------- endpoints

@app.get("/")
def inicio() -> FileResponse:
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/salud")
def salud() -> dict:
    ok_ffmpeg = bool(shutil.which("ffmpeg"))
    try:
        r = httpx.get(
            CONFIG["freellmapi_url"].rstrip("/") + "/v1/models",
            headers={"Authorization": f"Bearer {CONFIG['freellmapi_key']}"},
            timeout=4,
        )
        freellm = r.status_code == 200
    except Exception:
        freellm = False
    return {
        "ffmpeg": ok_ffmpeg,
        "freellmapi": freellm,
        "tts": voz.proveedor(),
        "whisper": CONFIG["whisper_model"],
        "modelo_default": CONFIG["modelo_texto"],
        "aspecto": CONFIG["aspecto"],
    }


@app.get("/api/modelos")
def modelos() -> dict:
    if time.time() - _modelos_cache["t"] > 300 or not _modelos_cache["lista"]:
        try:
            r = httpx.get(
                CONFIG["freellmapi_url"].rstrip("/") + "/v1/models",
                headers={"Authorization": f"Bearer {CONFIG['freellmapi_key']}"},
                timeout=6,
            )
            r.raise_for_status()
            _modelos_cache["lista"] = [m["id"] for m in r.json()["data"]]
            _modelos_cache["t"] = time.time()
        except Exception as e:
            log(f"No pude listar modelos ({e}); devuelvo el default")
            _modelos_cache["lista"] = [CONFIG["modelo_texto"]]
    return {"modelos": _modelos_cache["lista"], "default": CONFIG["modelo_texto"]}


@app.post("/api/transcribe")
async def transcribe(archivo: UploadFile) -> dict:
    SUFIJOS = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
               "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav"}
    sufijo = SUFIJOS.get(archivo.content_type or "")
    if not sufijo and archivo.filename and "." in archivo.filename:
        sufijo = "." + archivo.filename.rsplit(".", 1)[1].lower()
    sufijo = sufijo or ".webm"
    datos = await archivo.read()
    if len(datos) > 30 * 1024 * 1024:
        raise HTTPException(413, "El audio pasa los 30 MB")
    fd, tmp = tempfile.mkstemp(suffix=sufijo)
    try:
        with open(fd, "wb") as f:
            f.write(datos)
        texto = transcribir.de_audio(Path(tmp))
    finally:
        Path(tmp).unlink(missing_ok=True)
    return {"texto": texto}


@app.post("/api/generate")
def generate(pedido: PedidoGenerar) -> dict:
    if not pedido.texto.strip():
        raise HTTPException(400, "Falta el contenido: graba tu voz o escribe el tema")
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "id": job_id, "estado": "en_cola", "pasos": [], "error": None,
        "proyecto": pedido.proyecto.strip() or "general",
        "datos": pedido.model_dump(),
    }
    crear_job(job_id, _JOBS[job_id]["proyecto"], pedido.texto.strip(),
              pedido.modelo or CONFIG["modelo_texto"])
    _COLA.put(job_id)
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def estado_job(job_id: str) -> dict:
    if job_id in _JOBS:
        j = _JOBS[job_id]
        return {k: j[k] for k in ("id", "estado", "pasos", "error", "proyecto",
                                  "video_url", "titulo", "duracion", "guion", "plan")
                if k in j}
    fila = obtener_job(job_id)
    if not fila:
        raise HTTPException(404, "Job inexistente")
    video = f"/salidas/{job_id}/final.mp4" if fila.get("video_path") else None
    return {"id": job_id, "estado": fila["estado"], "error": fila.get("error"),
            "titulo": fila.get("titulo"), "duracion": fila.get("duracion"),
            "video_url": video, "pasos": [], "proyecto": fila["proyecto"]}


@app.post("/api/feedback")
def feedback(p: PedidoFeedback) -> dict:
    if not 1 <= p.puntaje <= 5:
        raise HTTPException(400, "El puntaje va de 1 a 5")
    fila = obtener_job(p.job_id)
    if not fila:
        raise HTTPException(404, "Job inexistente")
    guardar_feedback(p.job_id, fila["proyecto"], p.puntaje, p.comentario)
    return {"ok": True, "metricas": metricas()}


@app.get("/api/metricas")
def _metricas() -> dict:
    return metricas()


@app.get("/api/historial")
def _historial(limite: int = 20) -> dict:
    return {"jobs": historial(min(limite, 50))}


if __name__ == "__main__":
    import uvicorn

    init_db()
    url = f"http://127.0.0.1:{CONFIG['puerto']}"
    log(f"VideoGen Orchestrator en {url}")
    if "--sin-navegador" not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=CONFIG["puerto"], log_level="warning")
