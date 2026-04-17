FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    protobuf-compiler \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY capability.proto .
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    capability.proto

FROM python:3.12-slim-bookworm

WORKDIR /app

# WeasyPrint native dependencies + font tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    fontconfig \
    fonts-dejavu-core \
    unzip \
    wget \
  && rm -rf /var/lib/apt/lists/*

# Install Inter font family (variable weight, modern sans-serif)
RUN mkdir -p /usr/share/fonts/inter && \
    wget -q -O /tmp/inter.zip \
      "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip" && \
    unzip -q /tmp/inter.zip -d /tmp/inter-extract && \
    find /tmp/inter-extract -name "InterVariable*.ttf" -exec cp {} /usr/share/fonts/inter/ \; && \
    rm -rf /tmp/inter.zip /tmp/inter-extract && \
    fc-cache -f

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=builder /build/capability_pb2.py .
COPY --from=builder /build/capability_pb2_grpc.py .
COPY server.py .

EXPOSE 50051

CMD ["python", "server.py"]
