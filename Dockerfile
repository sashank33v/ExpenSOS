FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=6969

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

RUN mkdir -p /app/backend/uploads

EXPOSE 6969

CMD ["gunicorn", "--bind", "0.0.0.0:6969", "--workers", "2", "--threads", "4", "--timeout", "120", "--chdir", "/app/backend", "wsgi:application"]
