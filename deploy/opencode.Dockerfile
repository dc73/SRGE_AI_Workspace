FROM debian:trixie-slim
# node/npm are required so OpenCode can install the `@ai-sdk/openai-compatible`
# npm package that backs the `srge` provider (baseURL -> vLLM). Without the
# node toolchain the provider's npm package never lands in node_modules and
# `POST /session/{id}/message` fails with `UnknownError`.
RUN apt-get update && apt-get install -y --no-install-recommends binutils libc6 curl nodejs npm ca-certificates && rm -rf /var/lib/apt/lists
COPY opencode /usr/local/bin/opencode
RUN chmod +x /usr/local/bin/opencode
ENV OPENCODE_DISABLE_TELEMETRY=1
EXPOSE 4096
# Bind 0.0.0.0 so the OpenCode API is reachable via the container's
# bridge IP (172.17.x.x). The default binds 127.0.0.1 (container loopback),
# which is unreachable from the SRGE backend over the Docker port mapping.
CMD ["opencode", "serve", "--port", "4096", "--hostname", "0.0.0.0"]
