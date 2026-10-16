FROM golang:1.26-bookworm AS go_tools
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto GOMEMLIMIT=1500MiB
COPY addons/sources/clank /src/clank
WORKDIR /src/clank
RUN go build -p 1 -o /out/clank .
COPY addons/sources/phoneinfoga /src/phoneinfoga
WORKDIR /src/phoneinfoga
# Menace uses the CLI; the separate upstream web client is not served.
RUN mkdir -p web/client/dist && touch web/client/dist/.keep && echo 'CLI installation' > web/client/dist/index.html
RUN go build -p 1 -o /out/phoneinfoga .

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git libffi-dev libpango-1.0-0 libpangoft2-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY addons/install.py /app/addons/install.py
COPY addons/sources /app/addons/sources
RUN python addons/install.py sherlock
RUN python addons/install.py maigret
RUN python addons/install.py naminter
RUN python addons/install.py social-analyzer aliens_eye
RUN python addons/install.py toutatis socialscan
RUN python addons/install.py blackbird
RUN python addons/install.py holehe ignorant
COPY --from=go_tools /out/ /opt/addons/bin/
COPY requirements-workspace.txt .
RUN pip install --no-cache-dir -r requirements-workspace.txt
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core poppler-utils && rm -rf /var/lib/apt/lists/*
COPY . .
EXPOSE 8080
CMD ["sh", "start.sh"]
