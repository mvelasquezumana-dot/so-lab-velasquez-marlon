FROM python:3.11-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
RUN pip install --no-cache-dir "redis>=5"
COPY app.py .
EXPOSE 8080

# Forma exec (lista JSON): python es el PID 1 del contenedor y recibe SIGTERM directamente.
# Con forma shell (CMD python app.py) el PID 1 sería /bin/sh y la señal no llegaría a Python.
CMD ["python", "app.py"]
