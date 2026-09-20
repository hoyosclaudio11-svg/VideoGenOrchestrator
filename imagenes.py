"""Generacion de imagenes: FreeLLMAPI (Tier 1) -> Pollinations de respaldo, con cache."""
import base64
import hashlib
import random
import urllib.parse
from pathlib import Path

import httpx

from util import cargar_config, log

CACHE = Path(__file__).parent / "cache_imagenes"
CACHE.mkdir(exist_ok=True)


def _via_freellmapi(prompt: str, w_img: int, h_img: int) -> bytes | None:
    cfg = cargar_config()
    try:
        r = httpx.post(
            cfg["freellmapi_url"].rstrip("/") + "/v1/images/generations",
            headers={"Authorization": f"Bearer {cfg['freellmapi_key']}"},
            json={
                "model": cfg["modelo_imagen"],
                "prompt": prompt,
                "n": 1,
                "size": "1024x1792" if h_img > w_img else "1792x1024",
                "response_format": "b64_json",
            },
            timeout=300,
        )
        if r.status_code != 200:
            log(f"Imagen FreeLLMAPI HTTP {r.status_code}; paso al respaldo")
            return None
        dato = r.json()["data"][0]
        if dato.get("b64_json"):
            return base64.b64decode(dato["b64_json"])
        if dato.get("url"):
            img = httpx.get(dato["url"], timeout=120, follow_redirects=True)
            if img.status_code == 200:
                return img.content
        return None
    except Exception as e:
        log(f"Imagen FreeLLMAPI fallo ({type(e).__name__}: {e}); paso al respaldo")
        return None


def _via_pollinations(prompt: str, w_img: int, h_img: int) -> bytes | None:
    for intento in range(3):
        seed = random.randint(1, 999_999)
        url = (
            "https://image.pollinations.ai/prompt/"
            + urllib.parse.quote(prompt[:900])
            + f"?width={w_img}&height={h_img}&nologo=true&model=flux&seed={seed}"
        )
        try:
            r = httpx.get(url, timeout=240, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 20_000:
                return r.content
            log(f"Pollinations intento {intento + 1}: HTTP {r.status_code}, "
                f"{len(r.content)} bytes")
        except Exception as e:
            log(f"Pollinations intento {intento + 1} fallo: {e}")
    return None


def generar(prompt: str, w_img: int = 768, h_img: int = 1344) -> Path:
    """Genera (o recupera de cache) una imagen para el prompt. Nunca regenera
    el mismo prompt dos veces: las iteraciones solo pagan las escenas cambiadas."""
    clave = hashlib.sha1(f"{prompt}|{w_img}x{h_img}".encode("utf-8")).hexdigest()[:16]
    destino = CACHE / f"{clave}.jpg"
    if destino.exists() and destino.stat().st_size > 20_000:
        log(f"Imagen en cache: {destino.name}")
        return destino
    for via, fn in (("FreeLLMAPI", _via_freellmapi), ("Pollinations", _via_pollinations)):
        datos = fn(prompt, w_img, h_img)
        if datos and len(datos) > 20_000:
            destino.write_bytes(datos)
            log(f"Imagen OK via {via}: {destino.name} ({len(datos) // 1024} KB)")
            return destino
    raise RuntimeError(f"Ningun generador pudo crear la imagen de: {prompt[:80]!r}")
