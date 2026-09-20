"""Render final con ffmpeg: Ken Burns por escena, fundidos, concat y mux de audio."""
import subprocess
from pathlib import Path

FPS = 30
ZOOM = 1.16


def _run(cmd: list) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg fallo: {p.stderr[-800:]}")


def _video_escena(imagen: Path, dur: float, destino: Path, w: int, h: int,
                  acercar: bool) -> None:
    frames = max(2, round(dur * FPS))
    pre_w, pre_h = int(w * 1.6) // 2 * 2, int(h * 1.6) // 2 * 2
    paso = (ZOOM - 1) / frames
    z = f"min(zoom+{paso:.6f},{ZOOM})" if acercar else \
        f"if(lte(zoom,1.0),{ZOOM},max(1.0,zoom-{paso:.6f}))"
    fade_out = max(0.0, dur - 0.3)
    vf = (
        f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,"
        f"crop={pre_w}:{pre_h},"
        f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={w}x{h}:fps={FPS},"
        f"format=yuv420p,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.2f}:d=0.3"
    )
    p = subprocess.run(
        ["ffmpeg", "-y", "-i", str(imagen), "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(destino)],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg fallo en escena {destino.name}: {p.stderr[-600:]}")


def renderizar(escenas: list, dir_sal: Path, w: int, h: int, progreso=None,
               subtitulos=None) -> tuple:
    """escenas: [{imagen, audio, dur}]. Devuelve (video_final, duracion_total).
    subtitulos: ruta a un .ass para quemar en el render final (opcional)."""
    videos = []
    for i, esc in enumerate(escenas):
        v = dir_sal / f"esc_{i:02d}.mp4"
        _video_escena(Path(esc["imagen"]), esc["dur"], v, w, h, acercar=(i % 2 == 0))
        videos.append(v)
        if progreso:
            progreso(i + 1, len(escenas))

    lista = dir_sal / "lista.txt"
    lista.write_text("".join(f"file '{v.name}'\n" for v in videos), encoding="utf-8")
    mudo = dir_sal / "video_mudo.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
          "-c", "copy", str(mudo)])

    entradas = []
    for i, esc in enumerate(escenas):
        wav = dir_sal / f"voz_{i:02d}.wav"
        # El pad deja cada pieza tan larga como su escena: la narracion de la
        # escena i arranca justo donde arranca su imagen (sin drift acumulado).
        _run(["ffmpeg", "-y", "-i", str(esc["audio"]), "-af", "apad=pad_dur=0.7",
              "-ar", "44100", "-ac", "2", str(wav)])
        entradas += ["-i", str(wav)]
    narracion = dir_sal / "narracion.wav"
    _run(["ffmpeg", "-y", *entradas,
          "-filter_complex",
          f"concat=n={len(escenas)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
          "-map", "[aout]", "-ar", "44100", "-ac", "2", str(narracion)])

    final = dir_sal / "final.mp4"
    if subtitulos is not None:
        # Quemar subtitulos exige re-encode del video; cwd evita escapar la ruta
        # de Windows dentro del filtro ass= (los : de C:\ rompen el parser).
        p = subprocess.run(
            ["ffmpeg", "-y", "-i", mudo.name, "-i", narracion.name,
             "-filter_complex",
             f"[0:v]ass={subtitulos.name}[v];[1:a]apad=pad_dur=0.7[a]",
             "-map", "[v]", "-map", "[a]", "-shortest",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "160k", final.name],
            capture_output=True, text=True, cwd=str(dir_sal))
        if p.returncode != 0:
            raise RuntimeError(f"ffmpeg fallo quemando subtitulos: {p.stderr[-600:]}")
    else:
        _run(["ffmpeg", "-y", "-i", str(mudo), "-i", str(narracion),
              "-map", "0:v", "-map", "1:a", "-c:v", "copy",
              "-af", "apad=pad_dur=0.7", "-shortest",
              "-c:a", "aac", "-b:a", "160k", str(final)])
    return final, sum(esc["dur"] for esc in escenas)
