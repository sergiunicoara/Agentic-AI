FROM node:20-bookworm-slim AS builder

# Pinned release of protoc-gen-grpc-web, verified before it is executed.
ARG GRPC_WEB_PLUGIN_VERSION=1.5.0
ARG GRPC_WEB_PLUGIN_SHA256=2e6e074497b221045a14d5a54e9fc910945bfdd1198b12b9fc23686a95671d64

WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl protobuf-compiler \
 && curl -fsSL "https://github.com/grpc/grpc-web/releases/download/${GRPC_WEB_PLUGIN_VERSION}/protoc-gen-grpc-web-${GRPC_WEB_PLUGIN_VERSION}-linux-x86_64" \
      -o /usr/local/bin/protoc-gen-grpc-web \
 && echo "${GRPC_WEB_PLUGIN_SHA256}  /usr/local/bin/protoc-gen-grpc-web" | sha256sum -c - \
 && chmod +x /usr/local/bin/protoc-gen-grpc-web \
 && rm -rf /var/lib/apt/lists/*

# npm ci installs exactly what package-lock.json pins, so the image is
# reproducible and transitive dependencies cannot drift between builds.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
COPY proto/ /proto/
RUN npm run gen:proto
ENV VITE_ENVOY_URL=
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
