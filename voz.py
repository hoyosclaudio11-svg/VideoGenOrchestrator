"""Narracion TTS: ElevenLabs si hay key configurada, Edge-TTS (gratis, es-AR) como base."""
import asyncio
import subprocess
import time
from pathlib import Path

from util import cargar_config, log


def proveedor() -> str:
    cfg = cargar_config()
    if cfg["tts_provider"] in ("elevenlabs", "edge"):
        return cfg["tts_provider"]
    if cfg["elevenlabs_api_key"] and cfg["elevenlabs_voice_id"]:
        return "elevenlabs"
    return "edge"


def _elevenlabs(texto: str, destino: Path) -> None:
    import httpx

    cfg = cargar_config()
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['elevenlabs_voice_id']}",
        headers={"xi-api-key": cfg["elevenlabs_api_key"]},
        json={"text": texto, "model_id": "eleven_multilingual_v2"},
        timeout=120,
    )
    r.raise_for_status()
    destino.write_bytes(r.content)


def _edge(texto: str, destino: Path) -> None:
    import edge_tts

    async def _hacer():
        com = edge_tts.Communicate(texto, cargar_config()["edge_voice"])
        await com.save(str(destino))

    asyncio.run(_hacer())


def narrar(texto: str, destino: Path) -> Path:
    prov = proveedor()
    fn = _elevenlabs if prov == "elevenlabs" else _edge
    ultimo = None
    for intento in range(3):
        try:
            fn(texto, destino)
            if destino.exists() and destino.stat().st_size > 1_000:
                return destino
            ultimo = RuntimeError("audio vacio")
        except Exception as e:
            ultimo = e
            log(f"TTS ({prov}) intento {intento + 1} fallo: {e}")
            time.sleep(2)
    raise RuntimeError(f"TTS no pudo generar el audio tras 3 intentos: {ultimo}")


def duracion(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())
