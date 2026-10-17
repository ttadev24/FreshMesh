# routing-PL solver image with FreshMesh's patches (routing/solver-patches/*.patch) applied to the pinned
# submodule, which itself stays unmodified. Otherwise mirrors routing/routing-PL/Dockerfile.
# Build context: ./routing (see docker-compose.yml).
#   0001: routing-PL decoders now add each stop's service time (docs/experiments/frn-protocol-v1.2.md).
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libyaml-cpp-dev \
    nlohmann-json3-dev \
    patch \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY routing-PL/src/ /app/src/
COPY solver-patches/ /tmp/solver-patches/
RUN for p in /tmp/solver-patches/*.patch; do patch -p1 -d /app < "$p" || exit 1; done

WORKDIR /app/src/build
RUN cmake .. && make test

WORKDIR /app/backend
COPY routing-PL/backend/ /app/backend/
RUN mkdir -p bin && cp /app/src/build/test bin/test
RUN uv pip install --system .

WORKDIR /app/streamlit
COPY routing-PL/streamlit/ /app/streamlit/
RUN uv pip install --system .

WORKDIR /app
COPY routing-PL/start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8000
EXPOSE 8501
CMD ["/app/start.sh"]
