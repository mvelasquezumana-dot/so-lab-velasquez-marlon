# Cuestionario — Fase 1

## 1. Contenedor vs. máquina virtual (analogía del edificio)
En la analogía del edificio, un contenedor es como un apartamento: un proceso normal de Linux aislado que comparte el mismo kernel del host (la administración del edificio), por lo que consume pocos recursos y arranca rápido. Una máquina virtual es como una casa con cimientos propios porque incluye su propio kernel completo y emula hardware, lo que la hace más pesada y lenta al iniciar.

## 2. Dos PID en la Práctica 2
Esto lo causa el namespace PID, que le da al contenedor su propia tabla de identificadores de procesos aislada del resto del sistema. Adentro del contenedor, Python cree ser el proceso `1` (`pid_ns=1`), pero en el host de Ubuntu aparece con su PID real del sistema (por ejemplo `25980`), lo cual se comprueba en la línea `NSpid` de `/proc/$PID/status`.

## 3. Significado de cpu.max
Los dos números de `cpu.max` (`25000 100000`) representan microsegundos: el primero es la cuota permitida (25 000 µs = 25 ms) y el segundo es la duración del ciclo (100 000 µs = 100 ms). Esto significa que la API solo puede usar 25 ms de CPU por cada 100 ms (0,25 núcleos); si agota su cuota antes de que termine el ciclo, el kernel la detiene (throttling) hasta el siguiente periodo.

## 4. Llamada a /ram que causa OOM y exit code 137
Según `calculos.py --medir` (con el límite calibrado en `76m`), la API sobrevive las llamadas 1, 2 y 3 (sumando 15 MiB en cada una) y muere en la llamada 4 al superar `memory.max`. Como no tiene swap disponible, el OOM Killer del kernel mata el proceso enviándole la señal `SIGKILL` (señal 9), por lo que Docker reporta exit code `137` (`128 + 9`).

## 5. Por qué memswap_limit debe igualar a mem_limit
Igualar `memswap_limit` a `mem_limit` hace que `memory.swap.max` quede en `0`, impidiendo que el contenedor use disco como memoria de respaldo. Si pudiera usar swap, al superar `mem_limit` el kernel volcaría páginas de memoria al disco en lugar de disparar el OOM Killer de inmediato, haciendo que la predicción falle y el proceso no muera en la llamada esperada.

## 6. Descriptores de archivo y peticiones a /slow
Un descriptor de archivo (FD) es un número que el kernel asigna para representar cada archivo abierto o conexión de red (socket) de un proceso. Cada petición a `/slow` ocupa 2 descriptores durante 15 segundos: uno para el socket entrante desde Nginx y otro para el socket saliente hacia Redis. Con un límite `nofile` de 256 y 5 FDs base medidos en mi API, caben 125 peticiones simultáneas (`(256 - 5) ÷ 2`).

## 7. SIGTERM vs. SIGKILL y el rol del PID 1
`SIGTERM` (señal 15) es un aviso amable para que el proceso cierre conexiones, guarde estado y termine limpiamente (exit code 0), mientras que `SIGKILL` (señal 9) mata el proceso de inmediato sin dejarlo reaccionar (exit code 137). Como la API corre como PID 1 dentro de su namespace, Linux hace que el PID 1 ignore `SIGTERM` por defecto a menos que el programa defina un manejador explícito para esa señal.

## 8. Camino de curl localhost:8000/ hasta Redis
La petición sale de la terminal hacia el puerto `8000` del host, donde `docker-proxy` y una regla NAT la reenvían al contenedor `gateway` (Nginx). Nginx resuelve el nombre `order-api` en el DNS interno (`127.0.0.11`) y envía el tráfico por su cable virtual `veth` hacia el `bridge` (`br-...`), que lo entrega por el `veth` de `order-api` en el puerto `8080`. Finalmente, `order-api` vuelve a cruzar el `bridge` hacia el `veth` de `redis` (puerto `6379`) para ejecutar `INCR visitas` y devolver la respuesta por el mismo camino.

## 9. Diferencia entre namespace y cgroup
Un namespace controla el aislamiento, es decir, **qué puede ver** un proceso (por ejemplo, el namespace `net` le da al contenedor su propia interfaz de red e IP `172.18.0.x`). Un cgroup controla los recursos, es decir, **cuánto puede consumir** un grupo de procesos (por ejemplo, `memory.max` limita la RAM máxima de `order-api` a 76 MiB).

## 10. Hardware físico vs. lo que ve Linux y rol de .wslconfig
En mi caso estoy usando Ubuntu Server nativo, por lo que Linux ve directamente el hardware real del equipo: `4` núcleos (`nproc`), `11359 MiB` de RAM (`free -m`) y `cgroup2fs`, sin capa intermedia. Cuando se trabaja en Windows con WSL2, el archivo `.wslconfig` sirve para definir el límite de RAM, núcleos y swap que Windows le presta a la máquina virtual ligera de Linux.
