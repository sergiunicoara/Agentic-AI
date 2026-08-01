FROM node:20-bookworm-slim AS builder

WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl protobuf-compiler \
 && curl -fsSL https://github.com/grpc/grpc-web/releases/download/1.5.0/protoc-gen-grpc-web-1.5.0-linux-x86_64 \
      -o /usr/local/bin/protoc-gen-grpc-web \
 && chmod +x /usr/local/bin/protoc-gen-grpc-web \
 && rm -rf /var/lib/apt/lists/*
COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
COPY proto/ /proto/
RUN npm run gen:proto
ENV VITE_ENVOY_URL=
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
