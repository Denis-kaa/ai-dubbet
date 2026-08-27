FROM python:3.12-slim-bookworm

# FFmpeg, Node.js, Deno va tizim kutubxonalarini o'rnatish
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    git \
    unzip \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# yt-dlp config: enable Deno for PO tokens + EJS for JS challenge solving +
# bgutil PO token provider (sidecar container "pot-provider") — without a
# valid PO token, YouTube serves "UNPLAYABLE" for most videos from datacenter
# IPs even with valid cookies (confirmed 2026-08-12 on production).
RUN mkdir -p /root/.config/yt-dlp \
    && printf '%s\n' '--js-runtimes' 'deno' '--remote-components' 'ejs:github' \
       '--extractor-args' 'youtubepot-bgutilhttp:base_url=http://pot-provider:4416' > /root/.config/yt-dlp/config

# OAuth token cache directory (persisted via volume)
RUN mkdir -p /root/.cache/yt-dlp

COPY backend/ ./backend/

RUN mkdir -p /app/uploads /app/outputs
