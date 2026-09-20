"""Clips de video de bancos gratuitos.
Orden: Pexels (API oficial, con key) -> Pixabay (con key) -> Wikimedia Commons
(sin key, calidad variable) -> None (la escena usa imagen generada).
Keys gratis: pexels.com/api y pixabay.com/api/docs/"""
import hashlib
from pathlib import Path

import httpx

from util import cargar_config, log

CACHE = Path(__file__).parent / "cache_clips"
CACHE.mkdir(exist_ok=True)

# Wikimedia exige un User-Agent con contacto (politica de API); sin el, 403.
UA = ("VideoGenOrchestrator/1.0 "
      "(https://github.com/hoyosclaudio11-svg/VideoGenOrchestrator)")


def habilitado() -> bool:
    # Commons no necesita key: los clips siempre estan disponibles.
    return True


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


def _commons_busqueda(query: str) -> list:
    r = httpx.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:video {query}",
            "gsrnamespace": "6",
            "gsrlimit": "10",
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        },
        headers={"User-Agent": UA},
        timeout=30,
    )
    if r.status_code != 200:
        log(f"Commons HTTP {r.status_code}")
        return []
    candidatos = []
    for pagina in (r.json().get("query", {}).get("pages") or {}).values():
        for info in pagina.get("imageinfo", []):
            mime = info.get("mime", "")
            ancho, alto = info.get("width") or 0, info.get("height") or 0
            if not mime.startswith("video") or not info.get("url"):
                continue
            if not (500_000 <= (info.get("size") or 0) <= 80_000_000):
                continue  # descarta diminutos y monstruos
            puntos = 0
            if alto > ancho:
                puntos += 2  # vertical es oro
            if mime in ("video/mp4", "video/webm"):
                puntos += 1
            puntos += min(alto, 2160) / 4320
            candidatos.append((puntos, info["url"]))
    return candidatos


def _commons(query: str) -> str | None:
    """Wikimedia Commons: sin key, footage real bajo licencia libre."""
    try:
        candidatos = _commons_busqueda(query)
        if not candidatos:
            # reintento con las dos primeras palabras (busqueda full-text estricta)
            corta = " ".join(query.split()[:2])
            if corta and corta != query:
                candidatos = _commons_busqueda(corta)
        if not candidatos:
            log(f"Commons sin videos utilizables para '{query}'")
            return None
        candidatos.sort(key=lambda c: -c[0])
        return candidatos[0][1]
    except Exception as e:
        log(f"Commons fallo: {e}")
        return None


def _descargar(url: str, destino: Path) -> Path | None:
    try:
        r = httpx.get(url, timeout=240, follow_redirects=True,
                      headers={"User-Agent": UA})
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
    proveedores.append(("Commons", _commons))
    for via, fn in proveedores:
        url = fn(query)
        if url and _descargar(url, destino):
            log(f"Clip OK via {via}: {destino.name} "
                f"({destino.stat().st_size // 1024} KB) para '{query}'")
            return destino
    log(f"Ningun banco devolvio clip para '{query}'; la escena va con imagen")
    return None
