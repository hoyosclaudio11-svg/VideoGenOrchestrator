"""Prueba del pipeline de render sin LLM ni servicios: imagenes sinteticas + voz de prueba.
Uso: venv\\Scripts\\python.exe probar_pipeline.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from renderizar import renderizar
from voz import narrar, duracion

DIR = Path(__file__).parent / "prueba_render"
DIR.mkdir(exist_ok=True)


def imagen_sintetica(destino: Path, c1: str, c2: str) -> None:
    p = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"gradients=s=768x1344:c0={c1}:c1={c2}:n=2",
         "-frames:v", "1", str(destino)],
        capture_output=True,
    )
    if p.returncode != 0:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={c2}:s=768x1344",
             "-frames:v", "1", str(destino)],
            capture_output=True, check=True,
        )


def main() -> None:
    escenas = []
    for i, (c1, c2) in enumerate([("0x0b1d3a", "0x7c5cff"), ("0x3a0b0b", "0xff9d5c")]):
        img = DIR / f"img_{i}.jpg"
        imagen_sintetica(img, c1, c2)
        audio = DIR / f"voz_{i}.mp3"
        try:
            narrar(f"Escena numero {i + 1} de la prueba del pipeline de VideoGen.", audio)
        except Exception as e:
            print(f"TTS no disponible ({e}); genero silencio de 3 segundos")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", "3", str(audio)],
                capture_output=True, check=True,
            )
        escenas.append({"imagen": str(img), "audio": str(audio),
                        "dur": duracion(audio) + 0.7})
    final, total = renderizar(escenas, DIR, 1080, 1920)
    print(f"OK -> {final} ({total:.1f}s)")


if __name__ == "__main__":
    main()
