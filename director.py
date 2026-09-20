"""El agente DIRECTOR: ajusta parametros de produccion segun el pedido y el
feedback de iteraciones previas, y despues escribe el guion escena por escena."""
import json

from util import cargar_config, extraer_json, log, post_chat

PLAN_DEFAULT = {
    "tono": "dinamico y cercano",
    "estilo_visual": "cinematografico, colores vivos, alto detalle",
    "ritmo": "rapido",
    "duracion_objetivo_seg": 50,
    "cantidad_escenas": 5,
    "ajustes_por_feedback": "primera iteracion, sin correcciones",
}


def planear(pedido: str, estilo_extra: str, feedbacks: list, modelo: str) -> dict:
    """feedbacks: [(puntaje, comentario)] en orden cronologico. Si hay, el plan
    corrige exactamente lo que el usuario reclamo en iteraciones previas."""
    if feedbacks:
        fb_txt = "\n".join(
            f"- Iteracion {i + 1}: {p}/5. Comentario: {c or '(sin comentario)'}"
            for i, (p, c) in enumerate(feedbacks)
        )
        consigna_fb = (
            "Hubo iteraciones previas con este feedback del usuario. AJUSTA los parametros "
            "para corregir esas quejas (si dijeron 'muy lento', sube el ritmo y baja la "
            "duracion; si 'las imagenes no pegan con el tema', vuelve el estilo_visual mas "
            "literal; etc.) y explicalo en ajustes_por_feedback:\n" + fb_txt
        )
    else:
        consigna_fb = "Es la primera iteracion, no hay feedback previo."

    estilo = f"Estilo pedido por el usuario: {estilo_extra}." if estilo_extra else ""
    system = (
        "Sos el DIRECTOR de un generador de videos cortos verticales (9:16) tipo viral. "
        "Fijas los parametros de produccion antes de escribir el guion. Respondes SOLO con "
        "JSON valido, sin texto alrededor, con esta forma exacta: "
        '{"tono": "...", "estilo_visual": "...", "ritmo": "rapido|medio", '
        '"duracion_objetivo_seg": <int 30-90>, "cantidad_escenas": <int 3-6>, '
        '"ajustes_por_feedback": "..."}'
    )
    user = f"PEDIDO DEL VIDEO:\n{pedido}\n\n{estilo}\n\n{consigna_fb}"
    plan = PLAN_DEFAULT.copy()
    try:
        datos = extraer_json(post_chat(modelo, [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperatura=0.5, max_tokens=900))
        for k in plan:
            if datos.get(k):
                plan[k] = datos[k]
        plan["cantidad_escenas"] = max(3, min(int(plan["cantidad_escenas"]),
                                              cargar_config()["max_escenas"]))
        plan["duracion_objetivo_seg"] = max(25, min(int(plan["duracion_objetivo_seg"]), 90))
    except (ValueError, RuntimeError, TypeError) as e:
        log(f"Director sin plan del LLM ({e}); uso plan por defecto")
    return plan


def guion(pedido: str, plan: dict, modelo: str) -> dict:
    """Devuelve {"titulo", "gancho", "escenas": [{"narracion", "prompt_imagen"}]}."""
    n = plan["cantidad_escenas"]
    system = (
        "Sos un GUIONISTA de videos cortos verticales virales en espanol rioplatense. "
        "Escribis la narracion de cada escena y el prompt de imagen para un modelo de difusion.\n"
        "REGLAS:\n"
        "- El GANCHO va en la primera frase de la primera escena (3 segundos para atrapar).\n"
        "- Cada escena: 1-2 frases cortas para narrar (~6-9 segundos).\n"
        f"- Exactamente {n} escenas.\n"
        "- 'prompt_imagen' en INGLES: descripcion visual rica y concreta, estilo "
        f"{plan['estilo_visual']}. Sin texto ni letras en la imagen, sin marcas de agua.\n"
        "- Respondes SOLO con JSON valido con esta forma exacta: "
        '{"titulo": "...", "gancho": "...", '
        '"escenas": [{"narracion": "...", "prompt_imagen": "..."}]}'
    )
    user = (
        f"TEMA DEL VIDEO:\n{pedido}\n\n"
        f"PARAMETROS DEL DIRECTOR:\n"
        f"tono: {plan['tono']}\nritmo: {plan['ritmo']}\n"
        f"duracion objetivo total: {plan['duracion_objetivo_seg']} segundos\n"
        f"ajustes por feedback: {plan['ajustes_por_feedback']}"
    )
    mensajes = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    ultimo = None
    for intento in range(2):
        try:
            datos = extraer_json(post_chat(modelo, mensajes, temperatura=0.85,
                                           max_tokens=2500))
            escenas = datos.get("escenas") or []
            if len(escenas) >= 3 and all(
                (e.get("narracion") or "").strip() and (e.get("prompt_imagen") or "").strip()
                for e in escenas
            ):
                datos["escenas"] = escenas[: cargar_config()["max_escenas"]]
                datos.setdefault("titulo", "Sin titulo")
                return datos
            ultimo = f"guion invalido ({len(escenas)} escenas o campos vacios)"
        except (ValueError, RuntimeError) as e:
            ultimo = str(e)
        log(f"Guion intento {intento + 1} fallo: {ultimo}")
    raise RuntimeError(f"No se pudo obtener un guion valido del modelo: {ultimo}")
