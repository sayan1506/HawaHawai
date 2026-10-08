# Reuse this verified local image by digest. Builds never pull or retag the base.
ARG PYTHON_BASE=python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
FROM ${PYTHON_BASE}
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HAWAHAWAI_BIND=0.0.0.0
COPY backend/requirements-runtime.txt ./requirements-runtime.txt
COPY backend/requirements-runtime.lock.txt ./requirements-runtime.lock.txt
RUN pip install --no-cache-dir --no-compile -r requirements-runtime.txt
COPY backend/app.py backend/local_server.py ./
COPY backend/environmental ./environmental
COPY backend/safety ./safety
COPY backend/advisory ./advisory
COPY backend/persistence ./persistence
COPY agent ./agent
USER 10001:10001
EXPOSE 8000
CMD ["python", "local_server.py"]
