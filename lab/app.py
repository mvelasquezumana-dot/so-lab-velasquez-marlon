"""
Microservicio de laboratorio — Sistemas Operativos (kernel Linux + Docker)
Solo librería estándar + cliente redis. Cada ruta ejercita un recurso del kernel:
  /      -> red + IPC con Redis (sockets TCP)
  /cpu   -> trabajo FIJO de CPU (CFS / cpu.max -> throttling medible)
  /ram   -> fuga de memoria acumulativa (memory.max -> OOM Killer, exit 137)
  /slow  -> retiene 1 socket cliente + 1 socket Redis durante HOLD_S s (descriptores, ulimit -n)
  /fd    -> lee /proc/self para reportar FDs abiertos, hilos y RSS
"""
import os, sys, time, signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import redis

REDIS_HOST     = os.getenv("REDIS_HOST", "redis")
LEAK_MB        = int(os.getenv("LEAK_MB", "15"))          # MiB retenidos por cada /ram
CPU_ITER       = int(os.getenv("CPU_ITER", "10000000"))    # trabajo fijo por cada /cpu
HOLD_S         = int(os.getenv("HOLD_S", "15"))           # segundos que /slow retiene sus sockets
SHUTDOWN_DELAY = float(os.getenv("SHUTDOWN_DELAY", "3"))  # cierre "en curso" tras SIGTERM

db = redis.Redis(host=REDIS_HOST, port=6379,
                 socket_connect_timeout=2,
                 socket_timeout=HOLD_S + 10,   # explícito: redis-py 8 usa 5 s por defecto y cortaría /slow
                 max_connections=1000)         # explícito: redis-py 8 topa el pool en 100; queremos que mande el kernel
memory_leak = []


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def proc_status(campo):
    with open("/proc/self/status") as f:
        for linea in f:
            if linea.startswith(campo):
                return linea.split(":", 1)[1].strip()
    return "?"


# --- Señales POSIX: SIGTERM se puede capturar; SIGKILL no -----------------
def graceful_shutdown(signum, frame):
    log(f"[SO-SIGNAL] Señal {signum} ({signal.Signals(signum).name}) recibida. Cerrando conexiones...")
    time.sleep(SHUTDOWN_DELAY)          # visible en strace como clock_nanosleep
    db.close()
    log("[SO-SIGNAL] Conexión a Redis cerrada. Saliendo limpiamente (exit 0).")
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_shutdown)


class LabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        ruta = self.path.split("?")[0]
        try:
            if ruta == "/":
                hits = db.incr("visitas")
                self.respond(200, f"OK visita={hits} pid_ns={os.getpid()}\n")

            elif ruta == "/cpu":
                w0, c0 = time.perf_counter(), time.thread_time()
                x = 0
                for i in range(CPU_ITER):          # trabajo fijo, no tiempo fijo
                    x = (x + i * i) % 1_000_003
                wall, cpu = time.perf_counter() - w0, time.thread_time() - c0
                self.respond(200, f"cpu_s={cpu:.3f} wall_s={wall:.3f} ratio_wall/cpu={wall/cpu:.2f}\n")

            elif ruta == "/ram":
                memory_leak.append(bytearray(LEAK_MB * 1024 * 1024))   # bytearray escribe ceros -> páginas reales (RSS)
                self.respond(200, f"retenido={len(memory_leak) * LEAK_MB} MiB rss={proc_status('VmRSS')}\n")

            elif ruta == "/slow":
                db.blpop("cola-vacia", timeout=HOLD_S)  # retiene un socket Redis bloqueado
                self.respond(200, f"liberado tras {HOLD_S}s\n")

            elif ruta == "/fd":
                fds = len(os.listdir("/proc/self/fd"))
                self.respond(200, f"fds={fds} hilos={proc_status('Threads')} rss={proc_status('VmRSS')} "
                                  f"limite_nofile={open('/proc/self/limits').read().split('Max open files')[1].split()[0]}\n")
            else:
                self.respond(404, "Rutas: / /cpu /ram /slow /fd\n")
        except Exception as e:                    # p. ej. redis ConnectionError [Errno 24] Too many open files
            log(f"[ERROR] {ruta}: {e}")
            try:
                self.respond(503, f"error: {e}\n")
            except Exception:
                pass

    def respond(self, code, message):
        body = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):              # silencia el log por petición
        pass


class LabServer(ThreadingHTTPServer):
    request_queue_size = 512                   # backlog de listen(); el kernel lo topa en net.core.somaxconn
    _ultimo_aviso = 0.0

    def get_request(self):
        try:
            return super().get_request()
        except OSError as e:                   # EMFILE en accept(): sin FD libre para el nuevo socket
            if time.time() - self._ultimo_aviso > 1:
                log(f"[KERNEL] accept() falló: {e}")
                self._ultimo_aviso = time.time()
            time.sleep(0.05)                   # evita girar al 100 % de CPU
            raise


if __name__ == "__main__":
    log(f"[INICIO] Escuchando en :8080 | PID en el namespace: {os.getpid()} | LEAK_MB={LEAK_MB} CPU_ITER={CPU_ITER}")
    LabServer(("0.0.0.0", 8080), LabHandler).serve_forever()
