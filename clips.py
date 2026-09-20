"""Clips de video de bancos gratuitos via API oficial (Pexels -> Pixabay).
Sin key configurada devuelve None y la escena usa imagen: degrada bien.
Keys gratis: pexels.com/api y pixabay.com/api/docs/"""
import hashlib
from pathlib import Path

import httpx

from util import cargar_config, log

CACHE = Path(__file__).parent / "cache_clips"
CACHE.mkdir(exist_ok=True)


def habilitado() -> bool:
    cfg = cargar_config()
    return bool(cfg.get("pexels_api_key") or cfg.get("pixabay_api_key"))


def _mejor_archivo(archivos: list) -> str | None:
    """De los mp4 verticales, el que mas cerca este de 1440px de alto (liviano y nítido)."""
    verticales = [a for a in archivos
                  if a.get("file_type", "video/mp4") == "video/mp4"
                  and (a.get("height") or 0) > (a.get("width") or 0)
                  and a.get("link")]
    if not verticales:
        return None
    verticales.sort(key=lambda a: abs((a.get("height") or 0) - 1440))
    return verticales[0]["link"]


def _pexels(query: str) -> str | None:
    cfg = cargar_config()
    try:
        r = httpx.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "orientation": "portrait", "per_page": "5"},
            headers={"Authorization": cfg["pexels_api_key"]},
            timeout=30,
        )
        if r.status_code != 200:
            log(f"Pexels HTTP {r.status_code}")
            return None
        for video in r.json().get("videos", []):
            link = _mejor_archivo(video.get("video_files", []))
            if link:
                return link
        log(f"Pexels sin resultados verticales para '{query}'")
    except Exception as e:
        log(f"Pexels fallo: {e}")
    return None


def _pixabay(query: str) -> str | None:
    cfg = cargar_config()
    try:
        r = httpx.get(
            "https://pixabay.com/api/videos/",
            params={"key": cfg["pixabay_api_key"], "q": query, "per_page": "5"},
            timeout=30,
        )
        if r.status_code != 200:
            log(f"Pixabay HTTP {r.status_code}")
            return None
        for hit in r.json().get("hits", []):
            verticales = [v for v in (hit.get("videos") or {}).values()
                          if (v.get("height") or 0) > (v.get("width") or 0)
                          and v.get("url")]
            if verticales:
                verticales.sort(key=lambda v: abs((v.get("height") or 0) - 1440))
                return verticales[0]["url"]
    except Exception as e:
        log(f"Pixabay fallo: {e}")
    return None


def _descargar(url: str, destino: Path) -> Path | None:
    try:
        r = httpx.get(url, timeout=240, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 100_000:
            destino.write_bytes(r.content)
            return destino
        log(f"Descarga de clip debil: HTTP {r.status_code}, {len(r.content)} bytes")
    except Exception as e:
        log(f"Descarga de clip fallo: {e}")
    return None


def buscar(query: str) -> Path | None:
    """Devuelve la ruta a un clip vertical para la query, o None."""
    query = (query or "").strip()
    if not query or not habilitado():
        return None
    clave = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
    destino = CACHE / f"{clave}.mp4"
    if destino.exists() and destino.stat().st_size > 100_000:
        log(f"Clip en cache: {destino.name}")
        return destino
    cfg = cargar_config()
    proveedores = []
    if cfg.get("pexels_api_key"):
        proveedores.append(("Pexels", _pexels))
    if cfg.get("pixabay_api_key"):
        proveedores.append(("Pixabay", _pixabay))
    for via, fn in proveedores:
        url = fn(query)
        if url and _descargar(url, destino):
            log(f"Clip OK via {via}: {destino.name} "
                f"({destino.stat().st_size // 1024} KB) para '{query}'")
            return destino
    log(f"Ningun banco devolvio clip para '{query}'; la escena va con imagen")
    return None
