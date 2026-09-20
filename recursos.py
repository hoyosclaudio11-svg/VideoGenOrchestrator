"""Escalado dinamico de recursos: la concurrencia se adapta a la carga real de la PC."""
import psutil

from util import log


def concurrencia() -> int:
    """Workers para generacion en paralelo, segun CPU y RAM libre del momento."""
    cpu = psutil.cpu_percent(interval=0.6)
    ram = psutil.virtual_memory()
    libre_gb = ram.available / 1024**3
    workers = 4
    if cpu > 60:
        workers = 3
    if cpu > 75:
        workers = 2
    if cpu > 88 or libre_gb < 2:
        workers = 1
    log(f"Escala dinamica: {workers} workers (CPU {cpu:.0f}%, RAM libre {libre_gb:.1f} GB)")
    return workers
