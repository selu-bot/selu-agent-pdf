FROM python:3.12-slim AS builder

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

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=builder /build/capability_pb2.py .
COPY --from=builder /build/capability_pb2_grpc.py .
COPY server.py .

EXPOSE 50051

CMD ["python", "server.py"]
