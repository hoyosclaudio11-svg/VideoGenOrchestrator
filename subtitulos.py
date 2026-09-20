"""Subtitulos quemados: genera un .ass sincronizado con la narracion de cada escena."""
from pathlib import Path

MAX_CHARS = 38
FUENTE = "Segoe UI"
PAD_ESCENA = 0.7  # tiene que coincidir con el pad de renderizar.py

_CABECERA = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,%(fuente)s,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,4,2,2,90,90,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seg: float) -> str:
    seg = max(0.0, seg)
    h = int(seg // 3600)
    m = int(seg % 3600 // 60)
    s = seg % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _limpiar(texto: str) -> str:
    return texto.replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _trozos(texto: str) -> list:
    """Sube el texto en trozos de <= MAX_CHARS sin cortar palabras."""
    palabras = _limpiar(texto).split()
    trozos, actual = [], ""
    for p in palabras:
        candidato = f"{actual} {p}".strip()
        if len(candidato) > MAX_CHARS and actual:
            trozos.append(actual)
            actual = p
        else:
            actual = candidato
    if actual:
        trozos.append(actual)
    return trozos or [""]


def armar(escenas: list, piezas: list, destino: Path) -> Path:
    """escenas[i]['narracion'] sobre el audio de piezas[i]; pieza['dur'] = voz + pad."""
    lineas, t0 = [], 0.0
    for esc, pieza in zip(escenas, piezas):
        dur_voz = max(0.8, pieza["dur"] - PAD_ESCENA)
        trozos = _trozos(esc.get("narracion", ""))
        total = sum(len(t) for t in trozos) or 1
        acum = 0
        for t in trozos:
            ini = t0 + dur_voz * acum / total
            acum += len(t)
            fin = max(t0 + dur_voz * acum / total, ini + 0.6)
            lineas.append(
                f"Dialogue: 0,{_ts(ini)},{_ts(fin)},Base,,0,0,0,,{_limpiar(t)}")
        t0 += pieza["dur"]
    destino.write_text(_CABECERA % {"fuente": FUENTE} + "\n".join(lineas),
                       encoding="utf-8")
    return destino
