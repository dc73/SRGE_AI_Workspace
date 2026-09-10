FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    ca-certificates curl git python3 python3-pip build-essential \
    && rm -rf /var/lib/apt/lists/*

# code-server (browser-based VS Code)
RUN curl -fsSL https://code-server.dev/install.sh | sh

# OpenCode CLI (native binary)
RUN curl -fsSL https://opencode.ai/install | bash

# LiteLLM endpoint + Qwen model (OpenCode talks to Qwen through LiteLLM)
ENV OPENCODE_PROVIDER=srge
ENV OPENCODE_MODEL=qwen3.8-27b
ENV LITELLM_URL=http://host.docker.internal:4000/v1
