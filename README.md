# VideoGen Orchestrator

De una idea (escrita o hablada) a un video vertical listo para publicar: un **agente director**
ajusta los parámetros de producción, un LLM escribe el guion, un modelo de difusión genera las
imágenes, Edge-TTS/ElevenLabs narra y ffmpeg arma el video. En cada iteración el director corrige
los parámetros según el feedback del usuario.

## ¿Qué problema resuelve?

Entre "tengo una idea" y "tengo un video publicado" hay 2-3 horas y 4 herramientas:
guion, imágenes, voz y edición. Esta app convierte eso en hablar 30 segundos al
micrófono (o escribir una línea) y tener en ~1 minuto un video vertical publicable
con subtítulos. El problema que resuelve es la fricción, no la creatividad.

Para quién tiene sentido:

- **Operaciones de contenido con volumen** (canales faceless, cuotas diarias): es una
  fábrica del formato corto con gancho a los 3 segundos.
- **Iteración barata**: calificás, escribís qué no te gustó, y el director regenera
  ajustando ritmo/estilo/guion sin re-generar las imágenes que ya estaban bien.
- **Sin lock-in**: el modelo se cambia desde un dropdown; corre local contra cualquier
  gateway OpenAI-compatible.

Lo que NO resuelve:

1. **No elige buenas ideas.** Produce rápido cualquier idea, incluso las malas: la
   viralidad sigue dependiendo del tema y del gancho.
2. **No genera footage propio**: usa imágenes con movimiento de cámara y clips de bancos
   gratuitos (Pexels/Pixabay); el footage generado por modelos de video es otro nivel.
3. **El >4/5 mide la satisfacción iterando, no la de la audiencia.** La validación
   real es la retención en el canal.

En una línea: le quita horas a la parte mecánica de producir video corto y le pone
un loop medible a la parte de calidad, para que el tiempo se vaya a elegir temas.

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
4. **Imágenes y clips** — el director decide qué escena lleva footage real. Sin configurar nada
   los clips salen de **Wikimedia Commons** (sin key, calidad variable); con `pexels_api_key` /
   `pixabay_api_key` (gratis) usa bancos con mejor material. Si no encuentra, imagen generada
   (FreeLLMAPI → Pollinations). Cache por query/prompt (iterar no regenera lo que no cambió).
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
| `modelo_texto` | `auto` | Modelo del director/guionista (cambiable desde la UI) |
| `modelo_imagen` | `auto` | Modelo de imagen que pide a FreeLLMAPI |
| `whisper_model` | `base` | Tamaño de Whisper (`small` = mejor, más pesado) |
| `tts_provider` | `auto` | `auto` / `edge` / `elevenlabs` |
| `elevenlabs_api_key` | vacío | Si está, narra con ElevenLabs |
| `pexels_api_key` | vacío | Clips de mejor calidad (API oficial de Pexels, gratis en pexels.com/api). Sin key: Wikimedia Commons |
| `pixabay_api_key` | vacío | Segundo banco de clips (API de Pixabay) |
| `edge_voice` | `es-AR-TomasNeural` | Voz de Edge-TTS |
| `aspecto` | `vertical` | `vertical` (9:16) o `horizontal` (16:9) |
| `puerto` | `5190` | Puerto del panel |

## Notas

- **FreeLLMAPI tiene que estar arriba** (puerto 3001). El puntito rojo en la cabecera lo avisa.
- Cualquier gateway OpenAI-compatible sirve apuntando `freellmapi_url` + `freellmapi_key`.
- Prueba offline del render (sin LLM ni servicios): `venv\Scripts\python.exe probar_pipeline.py`
- API: `POST /api/generate`, `GET /api/job/{id}`, `POST /api/feedback`, `GET /api/metricas`,
  `GET /api/historial`, `POST /api/transcribe`, `GET /api/salud`.
