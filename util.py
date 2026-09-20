"""Utilidades compartidas: config, log, cliente LLM con control de finish_reason."""
import json
import re
import time
from pathlib import Path

import httpx

BASE = Path(__file__).parent
_LOG = BASE / "_videogen.log"

_CONFIG_DEFAULTS = {
    "puerto": 5190,
    "freellmapi_url": "http://127.0.0.1:3001",
    "freellmapi_key": "",
    "modelo_texto": "grok-4.3",
    "modelo_imagen": "auto",
    "whisper_model": "base",
    "tts_provider": "auto",
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "",
    "edge_voice": "es-AR-TomasNeural",
    "aspecto": "vertical",
    "max_escenas": 6,
    "segundos_objetivo": 50,
    "subtitulos": True,
}


def cargar_config() -> dict:
    cfg = dict(_CONFIG_DEFAULTS)
    archivo = BASE / "config.json"
    if archivo.exists():
        try:
            cfg.update(json.loads(archivo.read_text(encoding="utf-8")))
        except Exception as e:
            log(f"config.json ilegible ({e}); uso defaults")
    return cfg


def log(msg: str) -> None:
    linea = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(_LOG, "a", encoding="utf-8", errors="replace") as f:
            f.write(linea + "\n")
    except OSError:
        pass
    print(linea, flush=True)


def _limpiar_think(texto: str) -> str:
    return re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL).strip()


def post_chat(
    modelo: str,
    messages: list,
    temperatura: float = 0.8,
    max_tokens: int = 2500,
    timeout: int = 240,
) -> str:
    """Chat completion via FreeLLMAPI. Reintenta fallas de servicio y, si el
    texto se corta (finish_reason=length), reintenta con mas tokens."""
    cfg = cargar_config()
    url = cfg["freellmapi_url"].rstrip("/") + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['freellmapi_key']}"}
    payload = {
        "model": modelo,
        "messages": messages,
        "temperature": temperatura,
        "max_tokens": max_tokens,
    }
    ultimo_error = ""
    for intento in range(3):
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code in (429,) or r.status_code >= 500:
                ultimo_error = f"HTTP {r.status_code}"
                espera = 8 + intento * 8
                log(f"LLM {ultimo_error}, reintento en {espera}s ({intento + 1}/3)")
                time.sleep(espera)
                continue
            r.raise_for_status()
            data = r.json()
            eleccion = data["choices"][0]
            fin = eleccion.get("finish_reason")
            contenido = _limpiar_think(eleccion["message"].get("content") or "")
            if fin == "length" and not contenido:
                ultimo_error = "respuesta vacia por max_tokens"
                log(f"LLM sin contenido (finish=length); subo tokens y reintento")
                payload["max_tokens"] = int(payload["max_tokens"]) * 2
                continue
            if fin == "length":
                log("AVISO: respuesta truncada (finish=length); sigo con lo que hay")
            return contenido
        except (httpx.TimeoutException, httpx.TransportError) as e:
            ultimo_error = type(e).__name__
            log(f"LLM sin respuesta ({ultimo_error}), reintento {intento + 1}/3")
            time.sleep(3 + intento * 4)
        except (httpx.HTTPStatusError, KeyError, ValueError) as e:
            detalle = str(e)
            if "429" in detalle:
                raise RuntimeError(
                    "El gateway devolvio 429 en todos los intentos: los proveedores "
                    "estan rechazando o sin cuota. Proba con el modelo 'auto' o fijate "
                    "el dashboard de FreeLLMAPI.") from e
            raise RuntimeError(f"FreeLLMAPI respondio mal: {e}") from e
    if "429" in ultimo_error:
        raise RuntimeError(
            "429 persistente del gateway: proveedores sin cuota. "
            "Proba con el modelo 'auto'.")
    raise RuntimeError(f"FreeLLMAPI no respondio tras 3 intentos ({ultimo_error}). "
                       "Verificar que este arriba en el puerto 3001.")


def extraer_json(texto: str) -> dict:
    """Extrae el primer objeto JSON de una respuesta de LLM (tolerante a fences)."""
    limpio = _limpiar_think(texto).strip()
    limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
    limpio = re.sub(r"\s*```$", "", limpio).strip()
    ini, fin = limpio.find("{"), limpio.rfind("}")
    if ini == -1 or fin <= ini:
        raise ValueError(f"El modelo no devolvio JSON: {texto[:200]!r}")
    try:
        return json.loads(limpio[ini : fin + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON malformado del modelo ({e}): {limpio[:300]!r}") from e
