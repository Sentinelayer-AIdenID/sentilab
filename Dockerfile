# Thermal Flight Lab API image: the starter, HotSpot built with SuperLU, and the FastAPI service.
ARG PYTHON_BASE=python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
FROM ${PYTHON_BASE}
ARG PYTHON_BASE
ARG NODEJS_VERSION=20.19.2+dfsg-1+deb13u3

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libsuperlu-dev libblas-dev "nodejs=${NODEJS_VERSION}" \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Solver results feed the discrete surrogate search; pin OpenBLAS dispatch.
ENV OPENBLAS_CORETYPE=Haswell
COPY requirements.txt requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-service.txt

COPY . .
RUN python scripts/record_build_info.py --base-image "${PYTHON_BASE}" \
    --node-package-version "${NODEJS_VERSION}" --output /app/build-info.json
ARG CI_ALLOCATION=0
ENV CI_ALLOCATION=${CI_ALLOCATION}
# SLAB-049 also builds the material-only HotSpot 7 diagnostic binary (never the default oracle; its own class
# checks its identity tag) and the HotSpot 6.0 evaluator plus its TAP-faithful cross-check (scripts/build_hotspot6.sh).
# Each gate-zero and coupling evaluator gets <binary>.provenance.json, required by validate-reference.
RUN cd sundai_hotspot && make -j4 SUPERLU=1 CI_ALLOCATION=${CI_ALLOCATION} \
 && make SUPERLU=1 CI_ALLOCATION=${CI_ALLOCATION} hotspot-material-only \
 && (cd /app && python3 -m sundai_hotspot.provenance hotspot7_default material_only) \
 && bash /app/scripts/build_hotspot6.sh \
 && mkdir -p /licenses \
 && cp /app/sundai_hotspot/LICENSE /licenses/HotSpot-LICENSE \
 && cp /app/sundai_hotspot6/LICENSE /licenses/HotSpot-6.0-LICENSE \
 && cp /app/sundai_tap/LICENSE /licenses/TAP-2.5D-LICENSE \
 && cp /app/THIRD_PARTY_NOTICES.md /licenses/ \
 && cp "$(ls /usr/share/doc/libsuperlu[0-9]*/copyright | head -n 1)" /licenses/SuperLU-copyright

RUN bash /app/scripts/container_smoke.sh

ARG BUILD_SHA=unknown
ENV BUILD_SHA=${BUILD_SHA} PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
