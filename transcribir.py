"""Voz a texto local con faster-whisper (CPU int8). El modelo se carga la primera vez."""
import subprocess
from pathlib import Path

from util import cargar_config, log

_modelo = None


def _cargar():
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel

        cfg = cargar_config()
        log(f"Cargando Whisper '{cfg['whisper_model']}' (CPU int8)...")
        _modelo = WhisperModel(cfg["whisper_model"], device="cpu", compute_type="int8")
    return _modelo


def de_audio(path_audio: Path) -> str:
    """Convierte a wav 16k mono y transcribe en espanol. Devuelve el texto."""
    wav = path_audio.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path_audio), "-ar", "16000", "-ac", "1", str(wav)],
        capture_output=True, check=True,
    )
    segmentos, _info = _cargar().transcribe(str(wav), language="es", vad_filter=True)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    wav.unlink(missing_ok=True)
    return texto
