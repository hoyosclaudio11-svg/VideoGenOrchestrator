# VideoGen Orchestrator

De una idea (escrita o hablada) a un video vertical listo para publicar: un **agente director**
ajusta los parámetros de producción, un LLM escribe el guion, un modelo de difusión genera las
imágenes, Edge-TTS/ElevenLabs narra y ffmpeg arma el video. En cada iteración el director corrige
los parámetros según el feedback del usuario.

## Instalación (desde cero)

```
git clone https://github.com/hoyosclaudio11-svg/VideoGenOrchestrator.git
cd VideoGenOrchestrator
copy config.example.json config.json
```

Editá `config.json` con la URL y la key de tu gateway OpenAI-compatible
(FreeLLMAPI u otro). `config.json` está en `.gitignore`: **nunca se publica**.
Después arrancá con `iniciar.bat` (crea el venv e instala dependencias solo).

## Arranque

```
iniciar.bat
```

Abre `http://127.0.0.1:5190` solo. La primera vez crea el venv e instala dependencias.

## Cómo funciona (pipeline)

1. **Ingesta de voz** — grabás en el navegador; transcribe local con `faster-whisper` (CPU, es).
   También acepta texto directo.
2. **Director (agente)** — vía FreeLLMAPI (puerto 3001) fija tono, estilo visual, ritmo,
   cantidad de escenas y duración. Si el proyecto tiene feedback de iteraciones previas, el plan
   corrige exactamente esas quejas.
3. **Guion** — el LLM escribe título, gancho y N escenas (`narración` + `prompt_imagen` en inglés).
4. **Imágenes** — FreeLLMAPI (Tier 1) con respaldo automático en Pollinations; cache por prompt
   (iterar no regenera las escenas que no cambiaron).
5. **Voz** — Edge-TTS gratis (`es-AR-TomasNeural`); si cargás key de ElevenLabs en `config.json`,
   la usa automáticamente.
6. **Render** — ffmpeg: Ken Burns alternado + fundidos + mux de audio. 1080x1920.

**Escala dinámica de recursos**: la concurrencia de generación de imágenes se adapta a la carga
real de la PC (CPU y RAM por psutil: 1–4 workers).

**Feedback loop**: calificás cada video con estrellas + comentario. Eso alimenta al director de la
próxima iteración y alimenta la métrica de éxito del MVP: **promedio > 4/5 tras 3 iteraciones**
(se ve en el panel de Satisfacción).

## Configuración (`config.json`)

| Clave | Default | Qué es |
|---|---|---|
| `modelo_texto` | `grok-4.3` | Modelo del director/guionista (cambiable desde la UI) |
| `modelo_imagen` | `auto` | Modelo de imagen que pide a FreeLLMAPI |
| `whisper_model` | `base` | Tamaño de Whisper (`small` = mejor, más pesado) |
| `tts_provider` | `auto` | `auto` / `edge` / `elevenlabs` |
| `elevenlabs_api_key` | vacío | Si está, narra con ElevenLabs |
| `edge_voice` | `es-AR-TomasNeural` | Voz de Edge-TTS |
| `aspecto` | `vertical` | `vertical` (9:16) o `horizontal` (16:9) |
| `puerto` | `5190` | Puerto del panel |

## Notas

- **FreeLLMAPI tiene que estar arriba** (puerto 3001). El puntito rojo en la cabecera lo avisa.
- Cualquier gateway OpenAI-compatible sirve apuntando `freellmapi_url` + `freellmapi_key`.
- Prueba offline del render (sin LLM ni servicios): `venv\Scripts\python.exe probar_pipeline.py`
- API: `POST /api/generate`, `GET /api/job/{id}`, `POST /api/feedback`, `GET /api/metricas`,
  `GET /api/historial`, `POST /api/transcribe`, `GET /api/salud`.
