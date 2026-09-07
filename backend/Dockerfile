FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Проект переносится через Windows, файлы приезжают с CRLF, и контейнер
# падает с «env: bash\r: No such file or directory». Чиним в том же слое.
COPY entrypoint.sh /srv/entrypoint.sh
RUN sed -i 's/\r$//' /srv/entrypoint.sh && chmod +x /srv/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/srv/entrypoint.sh"]
