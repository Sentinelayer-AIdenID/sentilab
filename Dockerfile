# Thermal Flight Lab API image: the starter, HotSpot built with SuperLU, and the FastAPI service.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libsuperlu-dev libblas-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Solver results feed the discrete surrogate search; pin OpenBLAS dispatch.
ENV OPENBLAS_CORETYPE=Haswell
COPY requirements.txt requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-service.txt

COPY . .
RUN cd sundai_hotspot && make -j4 SUPERLU=1 \
 && mkdir -p /licenses \
 && cp /app/sundai_hotspot/LICENSE /licenses/HotSpot-LICENSE \
 && cp /app/sundai_tap/LICENSE /licenses/TAP-2.5D-LICENSE \
 && cp /app/THIRD_PARTY_NOTICES.md /licenses/ \
 && cp "$(ls /usr/share/doc/libsuperlu[0-9]*/copyright | head -n 1)" /licenses/SuperLU-copyright

RUN bash /app/scripts/container_smoke.sh

ARG BUILD_SHA=unknown
ENV BUILD_SHA=${BUILD_SHA} PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
