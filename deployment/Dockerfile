FROM golang:1.26-bookworm AS go_tools
ENV CGO_ENABLED=0 GOTOOLCHAIN=auto GOMEMLIMIT=1500MiB
COPY osint/addons/sources/clank /src/clank
WORKDIR /src/clank
RUN go build -p 1 -o /out/clank .
COPY osint/addons/sources/phoneinfoga /src/phoneinfoga
WORKDIR /src/phoneinfoga
# Menace uses the CLI; the separate upstream web client is not served.
RUN mkdir -p web/client/dist && touch web/client/dist/.keep && echo 'CLI installation' > web/client/dist/index.html
RUN go build -p 1 -o /out/phoneinfoga .

COPY osint/addons/sources/subfinder /src/subfinder
WORKDIR /src/subfinder
RUN go build -p 1 -o /out/subfinder ./cmd/subfinder

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git perl libffi-dev libpango-1.0-0 libpangoft2-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY osint/addons/install.py /app/addons/install.py
COPY osint/addons/sources /app/addons/sources
RUN python addons/install.py sherlock
RUN python addons/install.py maigret
RUN python addons/install.py naminter
RUN python addons/install.py social-analyzer aliens_eye
RUN python addons/install.py toutatis socialscan
RUN python addons/install.py blackbird
RUN python addons/install.py holehe ignorant
RUN python addons/install.py unfurl waymore dnstwist theharvester exiftool
RUN python addons/install.py mail-parser
COPY --from=go_tools /out/ /opt/addons/bin/
COPY requirements/requirements-workspace.txt .
RUN pip install --no-cache-dir -r requirements-workspace.txt
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core poppler-utils tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY osint/scripts/install_libpostal.sh /tmp/install_libpostal.sh
RUN sh /tmp/install_libpostal.sh && rm /tmp/install_libpostal.sh
COPY requirements/requirements-discovery.txt .
RUN pip install --no-cache-dir -r requirements-discovery.txt
COPY osint/ .
COPY LICENSE /app/LICENSE
COPY deployment/start.sh /app/start.sh
COPY deployment/setup_checks.py /app/scripts/setup_checks.py
COPY data/catalog/ /app/data/catalog/
EXPOSE 8080
CMD ["sh", "start.sh"]
