FROM python:3.12-slim

WORKDIR /app

# System deps for grpcio build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Build context is the repo root (set in docker-compose.yml)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source and proto definitions
COPY backend/ .
COPY proto/ /proto/

# Generate gRPC stubs from proto/v1/
RUN python -m grpc_tools.protoc \
    -I/proto/v1 \
    --python_out=app/generated \
    --grpc_python_out=app/generated \
    /proto/v1/agent_events.proto \
 && sed -i 's/^import agent_events_pb2/from app.generated import agent_events_pb2/' \
    app/generated/agent_events_pb2_grpc.py

EXPOSE 8000 50051

CMD ["python", "-m", "app.main"]
