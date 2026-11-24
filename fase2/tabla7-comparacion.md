# Tabla 7 — Predicción vs. realidad (Prácticas 3 a 6)

| Prueba | Predicho (calculos.py o guía) | Medido | Diferencia | ¿Por qué? |
|---|---|---|---|---|
| `ratio_wall/cpu` con 1 petición | ≈ 4 | 4.00 | 0.00 | Coincide exacto con la cuota de 0,25 núcleos (`25000 100000` en `cpu.max`): el kernel pausa el proceso 75 ms de cada 100 ms. |
| `ratio_wall/cpu` con 2 peticiones | ≈ 8 | 7.91 y 8.04 (prom. 7.98) | -0.02 | Ambas peticiones compiten por la misma cuota de 0,25 núcleos; `nr_throttled` subió de 53 a 488 (+435 pausas). |
| Memoria base de la API | 24.3 MiB | ~31.5 MiB RSS (32364 kB en reposo P5) | +7.2 MiB | `calculos.py --medir` lee `memory.current` recién iniciado; al atender peticiones HTTP Python retiene algo más de RSS. |
| Llamada a `/ram` que dispara el OOM | Llamada 4 | Llamada 4 (`502 Bad Gateway`) | 0 | Al sumar 4 × 15 MiB sobre la memoria base superó el límite de 76 MiB sin swap (`memswap_limit = 76m`). |
| Exit code tras el OOM | 137 | 137 (`OOMKilled=true`) | 0 | El OOM Killer del kernel mató al proceso Python con `SIGKILL` (señal 9: `128 + 9 = 137`). |
| Descriptores con N = 50 | 105 (`calculos.py`) / ≈ 104 (guía) | 104 | -1 | En reposo real el proceso tenía 4 FDs abiertos (0, 1, 2 y socket 3) en lugar de 5; `4 + 50 × 2 = 104`. |
| Descriptores con N = 100 | 205 (`calculos.py`) / ≈ 204 (guía) | 204 | -1 | Misma diferencia de 1 FD base (`4 + 100 × 2 = 204`); se observaron 100 sockets en `:8080` y 100 en `:6379`. |
| Máximo de peticiones simultáneas | 125 (`calculos.py`) / 126 (guía) | 126 (256 FDs, `EMFILE`) | +1 | Con 4 FDs base y tope `nofile=256` caben `(256 - 4) ÷ 2 = 126` peticiones simultáneas; las 24 restantes esperan tras `[Errno 24]`. |
| Tiempo de `docker stop` con SIGTERM | ≈ 3 s | 3.977 s | +0.977 s | Además del `sleep(3)` del manejador, Python cerró los sockets abiertos de la prueba anterior y Docker finalizó el contenedor. |
| Exit code con SIGTERM | 0 | 0 | 0 | El proceso capturó `SIGTERM`, cerró Redis y terminó limpiamente con `exit_group(0)`. |
| Tiempo de `docker stop` con SIGKILL | ≈ 10 s | 10.354 s | +0.354 s | Con `SHUTDOWN_DELAY=15`, Docker agotó su espera de 10 s y envió `SIGKILL`; el excedente es la sobrecarga de detención. |
| Exit code con SIGKILL | 137 | 137 | 0 | `SIGKILL` (señal 9) mató el proceso de inmediato sin dejarlo terminar su `clock_nanosleep` (`128 + 9 = 137`). |
