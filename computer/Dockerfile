# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends xvfb xdotool openbox chromium x11-apps x11-utils libnss3-tools scrot x11vnc fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd -m -u 1000 orbit && mkdir /data && chown orbit:orbit /data
COPY --chown=orbit:orbit . /app
COPY --chown=orbit:orbit novnc/ /opt/novnc/
USER orbit
ENV DISPLAY=:99 ORBIT_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["bash","/app/start.sh"]
