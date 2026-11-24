"""
calculos.py — Calculadora del Documento de Gestión (Tablas 2, 3 y 4)

Uso:
    python3 calculos.py            -> calcula con los valores escritos abajo
    python3 calculos.py --medir    -> además mide la memoria base y los FDs base
                                      del laboratorio en marcha (docker compose up)

Solo necesita Python 3 (sin librerías externas).
Copie cada línea de la salida en la tabla del mismo número.
"""
import re
import subprocess
import sys
import urllib.request

# ============================================================================
# 1. ESCRIBA AQUÍ SUS DATOS  (los mismos de su docker-compose.yml y Tabla 1)
# ============================================================================

NUCLEOS_LINUX = 4            # salida de: nproc
RAM_LINUX_MIB = 11359          # "total" de: free -m   (en WSL2 = memory de .wslconfig)

CPUS = {                     # valor "cpus:" de cada servicio en docker-compose.yml
    "gateway": 0.50,
    "order-api": 0.25,
    "redis": 0.50,
}
LIMITE_MEMORIA_MIB = {       # valor "mem_limit:" de cada servicio (en MiB)
    "gateway": 64,
    "order-api": 76,
    "redis": 128,
}
NOFILE_API = 256             # "ulimits: nofile:" de order-api

# Valores base de order-api. Con --medir se reemplazan por los reales.
MEMORIA_BASE_API_MIB = 20    # docker stats, columna MEM USAGE, en reposo
FDS_BASE_API = 4             # descriptores abiertos en reposo

# Parámetros de las pruebas de estrés
FUGA_POR_LLAMADA_MIB = 15    # LEAK_MB: MiB que retiene cada curl a /ram
LLAMADAS_QUE_DEBEN_SOBREVIVIR = 3
CONCURRENCIAS = [50, 100, 150]          # N de la prueba /slow
PETICIONES_CPU_SIMULTANEAS = [1, 2]     # curl simultáneos a /cpu

PERIODO_US = 100_000         # periodo del planificador que usa Docker (100 ms)
URL = "http://localhost:8000"


# ============================================================================
# 2. MEDICIÓN AUTOMÁTICA (opcional, con --medir)
# ============================================================================

def medir_memoria_base():
    """Lee 'docker stats' y devuelve la memoria de order-api en MiB."""
    salida = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}};{{.MemUsage}}"],
        capture_output=True, text=True, check=True).stdout
    for linea in salida.splitlines():
        nombre, uso = linea.split(";")
        if "order-api" in nombre:
            valor, unidad = re.match(r"([\d.]+)\s*([KMG]i?B)", uso).groups()
            factor = {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "kB": 1 / 1024, "MB": 1, "GB": 1024}
            return float(valor) * factor.get(unidad, 1)
    raise RuntimeError("No encontré el contenedor order-api en docker stats")


def medir_fds_base():
    """Pide /fd a la API. Se restan 2: el socket de esa petición y el directorio que abre."""
    texto = urllib.request.urlopen(URL + "/fd", timeout=5).read().decode()
    fds = int(re.search(r"fds=(\d+)", texto).group(1))
    return fds - 2


# ============================================================================
# 3. CÁLCULOS
# ============================================================================

def linea(texto=""):
    print(texto)


def tabla_2_cpu():
    linea("TABLA 2 - CPU (archivo cpu.max del cgroup)")
    linea("-" * 76)
    total = 0
    for servicio, cpus in CPUS.items():
        cuota = int(cpus * PERIODO_US)
        ms = cuota / 1000
        total += cpus
        linea(f"{servicio:10} cpus={cpus:<5} cpu.max esperado: \"{cuota} {PERIODO_US}\""
              f"  -> puede usar {ms:g} ms de cada 100 ms")
    linea()
    linea("Prueba /cpu en order-api (cuánto más tarda por estar limitada):")
    for k in PETICIONES_CPU_SIMULTANEAS:
        # k peticiones comparten la cuota; Python ejecuta un hilo a la vez
        veces = k / min(CPUS["order-api"], 1)
        linea(f"  {k} petición(es) simultánea(s) -> ratio_wall/cpu esperado ≈ {veces:g}")
    estado = "OK" if total < NUCLEOS_LINUX else "PELIGRO: supera los núcleos de Linux"
    linea(f"\nTotal reservado: {total:g} núcleos de {NUCLEOS_LINUX} disponibles -> {estado}")
    linea()


def tabla_3_memoria(base):
    limite = LIMITE_MEMORIA_MIB["order-api"]
    linea("TABLA 3 - MEMORIA Y OOM KILLER (order-api)")
    linea("-" * 76)
    linea(f"Memoria base: {base:.1f} MiB | límite (mem_limit = memswap_limit): {limite} MiB"
          f" | fuga por llamada: {FUGA_POR_LLAMADA_MIB} MiB")
    llamada, consumo = 0, base
    while True:
        llamada += 1
        consumo += FUGA_POR_LLAMADA_MIB
        if consumo > limite:
            linea(f"  curl /ram #{llamada}: {consumo:.1f} MiB > {limite} -> OOM Killer, exit 137")
            break
        margen = limite - consumo
        aviso = "  (margen muy pequeño)" if margen < 5 else ""
        linea(f"  curl /ram #{llamada}: {consumo:.1f} MiB <= {limite} -> sobrevive{aviso}")
    linea(f"Predicción: el proceso muere en la llamada {llamada}.")

    # Límite recomendado: deja medio bloque de margen a cada lado
    recomendado = base + FUGA_POR_LLAMADA_MIB * (LLAMADAS_QUE_DEBEN_SOBREVIVIR + 0.5)
    recomendado = int(recomendado)
    linea(f"Para que sobreviva {LLAMADAS_QUE_DEBEN_SOBREVIVIR} llamadas y muera en la "
          f"{LLAMADAS_QUE_DEBEN_SOBREVIVIR + 1}: mem_limit: {recomendado}m y memswap_limit: {recomendado}m")

    suma = sum(LIMITE_MEMORIA_MIB.values())
    estado = "OK, el OOM será solo del contenedor" if suma < RAM_LINUX_MIB else "PELIGRO: supera la RAM de Linux"
    linea(f"\nSuma de límites: {suma} MiB de {RAM_LINUX_MIB} MiB en Linux -> {estado}")
    linea()


def tabla_4_descriptores(fds_base):
    linea("TABLA 4 - DESCRIPTORES DE ARCHIVO (order-api, prueba /slow)")
    linea("-" * 76)
    linea(f"FDs base: {fds_base} | límite nofile: {NOFILE_API} | cada petición /slow abre 2"
          " (1 socket desde nginx + 1 socket a Redis)")
    n_max = (NOFILE_API - fds_base) // 2
    for n in CONCURRENCIAS:
        fds = fds_base + 2 * n
        if fds <= NOFILE_API:
            uso = fds * 100 // NOFILE_API
            estado = "estable" if uso < 90 else "estable, al borde"
            linea(f"  N={n:<4} FDs={fds:<5} uso={uso}% de {NOFILE_API} -> {estado};"
                  f" nginx usa {2 * n} sockets, Redis {n} clientes")
        else:
            linea(f"  N={n:<4} FDs={fds:<5} > {NOFILE_API} -> 'Too many open files' (EMFILE);"
                  f" solo {n_max} se atienden a la vez, Redis {n_max} clientes")
    linea(f"Máximo de peticiones /slow simultáneas: {n_max}")
    linea()


if __name__ == "__main__":
    base, fds = MEMORIA_BASE_API_MIB, FDS_BASE_API
    if "--medir" in sys.argv:
        try:
            urllib.request.urlopen(URL + "/", timeout=5).read()   # petición de calentamiento
            base, fds = medir_memoria_base(), medir_fds_base()
            print(f"[medido] memoria base = {base:.1f} MiB, FDs base = {fds}\n")
        except Exception as e:
            print(f"[aviso] no pude medir ({e}); uso los valores escritos en el script\n")
    tabla_2_cpu()
    tabla_3_memoria(base)
    tabla_4_descriptores(fds)
