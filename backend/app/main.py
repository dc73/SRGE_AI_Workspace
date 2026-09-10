import base64
import json
import os
import sys
import time
import uuid

import bcrypt
import docker
import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from sqlmodel import Session

from . import models
from .db import get_session, init_db, get_engine

# --- config ---------------------------------------------------------------
JWT_SECRET = os.getenv("SRGE_JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
OPENCODE_IMAGE = os.getenv("SRGE_OPENCODE_IMAGE", "opencode/opencode:latest")
OPENCODE_PORT = int(os.getenv("SRGE_OPENCODE_PORT", "8080"))
VLLM_BASE_URL = os.getenv("SRGE_VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_API_KEY = os.getenv("SRGE_VLLM_API_KEY", "")
# Runtimes reach vLLM via a shared Docker network service alias (qwen38).
# The host's bridge gateway IP is NOT the host, so it cannot see host-loopback
# vLLM. A dedicated `srge` network connects the vLLM engine + runtimes.
VLLM_HOST_BASE_URL = os.getenv("SRGE_VLLM_HOST_BASE_URL", "http://qwen38:8000/v1")
SRGE_NETWORK = os.getenv("SRGE_NETWORK", "srge")
IDLE_REAP_MINUTES = int(os.getenv("SRGE_IDLE_REAP_MINUTES", "30"))
IDLE_REAP_INTERVAL = int(os.getenv("SRGE_IDLE_REAP_INTERVAL", "300"))
PROMETHEUS_PORT = int(os.getenv("SRGE_PROMETHEUS_PORT", "9400"))
ALLOWED_HOSTS = os.getenv("SRGE_ALLOWED_HOSTS", "localhost,127.0.0.1,spark-f0d1,100.68.61.41")

# --- auth helpers ---------------------------------------------------------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: models.User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": time.time() + 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def current_user(request: Request) -> models.User:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")
    with get_session() as s:
        user = s.get(models.User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(401, "user not found or inactive")
    return user


# --- runtime manager (docker-py) ----------------------------------------
_runtime_client: docker.DockerClient | None = None


def docker_client() -> docker.DockerClient:
    global _runtime_client
    if _runtime_client is None:
        _runtime_client = docker.from_env()
    return _runtime_client


def _safe_name(user_id: int) -> str:
    return f"srge-oc-{user_id}"


def provision_runtime(user: models.User, opencode_password: str) -> str:
    """Spawn a hardened per-user OpenCode container; return container name."""
    client = docker_client()
    name = _safe_name(user.id)
    # Reuse an existing runtime (container or DB row) if present (idempotent).
    with get_session() as s:
        rt = s.query(models.Runtime).filter(models.Runtime.user_id == user.id).first()
    if rt is not None:
        existing = client.containers.list(all=True, filters={"name": rt.container_name})
        if existing:
            existing[0].start()
            ip = _container_ip(client, rt.container_name)
            with get_session() as s:
                r = s.query(models.Runtime).filter(models.Runtime.id == rt.id).first()
                if r is not None:
                    r.status = "running"
                    if ip:
                        r.container_ip = ip
                    s.add(r)
                    s.commit()
        return rt.container_name

    # If the container already exists (leftover from a prior run), reuse it.
    existing = client.containers.list(all=True, filters={"name": name})
    if existing:
        existing[0].start()
        ip = _container_ip(client, name)
        with get_session() as s:
            r = s.query(models.Runtime).filter(models.Runtime.user_id == user.id).first()
            if r is None:
                r = models.Runtime(
                    user_id=user.id,
                    container_name=name,
                    opencode_password=opencode_password,
                    status="running",
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    container_ip=ip,
                )
                s.add(r)
            else:
                r.status = "running"
                if ip:
                    r.container_ip = ip
                s.add(r)
            s.commit()
        return name

    # Ensure the shared network exists and attach vLLM engine + this runtime to it
    # so the agent can reach the local vLLM by service alias.
    _ensure_shared_network(client)
    client.containers.run(
        OPENCODE_IMAGE,
        detach=True,
        name=name,
        environment={"OPENCODE_SERVER_PASSWORD": opencode_password},
        ports={"4096/tcp": ("127.0.0.1", OPENCODE_PORT)},
        network=SRGE_NETWORK,
        labels={"srge": "runtime", "srge.user": str(user.id)},
        mem_limit="4g",
        nano_cpus=2,
        pids_limit=512,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"],
        auto_remove=False,
        restart_policy={"Name": "on-failure", "MaximumRetryCount": 2},
    )
    # Reachability: the runtime image binds OpenCode to 0.0.0.0, so the
    # backend can reach it directly via the container's bridge IP (more
    # reliable than the flaky 127.0.0.1 host port mapping).
    container_ip = _container_ip(client, name)
    with get_session() as s:
        rt = models.Runtime(
            user_id=user.id,
            container_name=name,
            opencode_password=opencode_password,
            status="running",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            container_ip=container_ip,
        )
        s.add(rt)
        s.commit()
    configure_opencode_vllm(name)
    return name


def _ensure_shared_network(client: docker.DockerClient) -> None:
    """Create the shared `srge` network (idempotent) and attach the vLLM engine."""
    try:
        client.networks.get(SRGE_NETWORK)
    except docker.errors.NotFound:
        client.networks.create(SRGE_NETWORK, driver="bridge")
    # Attach the vLLM engine container to the shared network (idempotent).
    try:
        client.networks.connect(SRGE_NETWORK, "qwen38")
    except Exception:
        pass  # already connected


def _container_ip(client: docker.DockerClient, name: str) -> str | None:
    try:
        nets = client.containers.get(name).attrs["NetworkSettings"]["Networks"]
        for n in nets.values():
            ip = n.get("IPAddress")
            if ip:
                return ip
    except Exception:
        pass
    return None


def runtime_endpoint(user: models.User) -> str:
    """Localhost URL of the user's OpenCode runtime."""
    return f"http://127.0.0.1:{OPENCODE_PORT}"


def configure_opencode_vllm(container_name: str) -> None:
    """Write an OpenCode config that registers the SRGE vLLM provider so the agent can call it.

    The vLLM engine is reached from inside the container via the Docker bridge
    gateway (SRGE_VLLM_HOST_BASE_URL). vLLM itself listens on host loopback.
    """
    # The provider's baseURL points to the in-container SSE-sanitizing proxy
    # (SRGE_SSE_PROXY_BASE_URL, default http://127.0.0.1:8811) so the
    # OpenCode bundled adapter sees a clean OpenAI-format stream. The proxy
    # strips vLLM-specific fields (token_ids, stop_reason, system_fingerprint,
    # prompt_token_ids, prompt_text) that the bundled adapter chokes on.
    sse_proxy_url = os.getenv("SRGE_SSE_PROXY_BASE_URL", "http://127.0.0.1:8811")
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "srge": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "SRGE vLLM",
                "options": {
                    "baseURL": sse_proxy_url + "/v1",
                    "apiKey": VLLM_API_KEY or "srge",
                },
                "models": {
                    "qwen3.8-27b": {"name": "Qwen3.8-27B Uncensored NVFP4"}
                },
            }
        },
    }
    client = docker_client()
    # put_archive(container, path, data) — positional; the tar's root dir
    # ("opencode") is relative to /root/.config.
    try:
        cid = client.containers.get(container_name).id
        data = json.dumps(cfg).encode("utf-8")
        client.api.put_archive(
            cid,
            "/root/.config",
            _tar_bytes([("opencode/opencode.jsonc", data)], "opencode"),
        )
    except Exception as e:
        print(f"[srge] warn: could not write opencode config: {e}", file=sys.stderr)


def _tar_bytes(files: list[tuple[str, bytes]], dirname: str) -> bytes:
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in files:
            info = tarfile.TarInfo(name=f"{dirname}/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# --- idle reaper state (module-level, shared by proxy + reaper thread)
last_activity: dict[int, float] = {}

# --- request queue --------------------------------------------------------
class QueueItem(BaseModel):
    user_id: int
    model: str
    payload: dict


# --- app factory ----------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title="SRGE AI Workspace", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in ALLOWED_HOSTS.split(",") if h.strip()])

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    # --- auth routes
    class LoginIn(BaseModel):
        email: str
        password: str

    @app.post("/auth/login")
    def login(body: LoginIn):
        with get_session() as s:
            user = s.query(models.User).filter(models.User.email == body.email).first()
            if not user or not verify_password(body.password, user.password_hash):
                raise HTTPException(401, "invalid credentials")
            if not user.is_active:
                raise HTTPException(403, "user inactive")
            return {"token": create_token(user), "role": user.role, "email": user.email}

    @app.post("/auth/register", status_code=201)
    def register(request: Request):
        raise HTTPException(405, "registration is admin-gated; use /admin/users")

    # --- admin: user + role management
    class UserIn(BaseModel):
        email: str
        password: str
        role: str = "user"

    @app.post("/admin/users", status_code=201)
    def admin_create_user(body: UserIn, request: Request):
        # Bootstrap: the very first admin can be created without a token.
        with get_session() as s:
            count = s.query(models.User).count()
        if count > 0:
            admin = current_user(request)
            if admin.role != "admin":
                raise HTTPException(403, "admin role required")
        with get_session() as s:
            if s.query(models.User).filter(models.User.email == body.email).first():
                raise HTTPException(409, "email already exists")
            u = models.User(email=body.email, password_hash=hash_password(body.password), role=body.role)
            s.add(u)
            s.commit()
            s.refresh(u)
            token = create_token(u)
        return {"id": u.id, "email": u.email, "role": u.role, "token": token}

    @app.get("/admin/users")
    def admin_list_users(request: Request):
        admin = current_user(request)
        if admin.role != "admin":
            raise HTTPException(403, "admin role required")
        with get_session() as s:
            users = s.query(models.User).all()
        return [{"id": u.id, "email": u.email, "role": u.role, "active": u.is_active} for u in users]

    # --- per-user runtime provisioning
    @app.post("/user/runtime/provision", status_code=202)
    def provision(request: Request):
        user = current_user(request)
        with get_session() as s:
            existing = s.query(models.Runtime).filter(models.Runtime.user_id == user.id).first()
        pw = existing.opencode_password if existing else (os.getenv("SRGE_DEFAULT_OC_PASSWORD") or uuid.uuid4().hex)
        name = provision_runtime(user, pw)
        return {"container": name, "endpoint": runtime_endpoint(user)}

    @app.get("/user/runtime")
    def runtime_state(request: Request):
        user = current_user(request)
        with get_session() as s:
            rt = s.query(models.Runtime).filter(models.Runtime.user_id == user.id).first()
        if not rt:
            raise HTTPException(404, "no runtime provisioned yet")
        return {"container": rt.container_name, "status": rt.status, "endpoint": runtime_endpoint(user)}

    # --- vLLM proxy with usage accounting
    @app.post("/v1/chat/completions")
    async def vllm_chat(request: Request):
        user = current_user(request)
        body = await request.json()
        if "model" not in body:
            body["model"] = "qwen3.8-27b"
        import httpx
        url = VLLM_BASE_URL + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if VLLM_API_KEY:
            headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                t0 = time.time()
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                usage = data.get("usage") or {}
                lat_ms = int((time.time() - t0) * 1000)
                rec = models.UsageRecord(
                    user_id=user.id,
                    model=data.get("model", "unknown"),
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    latency_ms=lat_ms,
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
                with get_session() as s:
                    s.add(rec)
                    s.commit()
                return data
        except httpx.HTTPError as e:
            raise HTTPException(502, f"vLLM upstream error: {e}")

    @app.get("/user/usage")
    def user_usage(request: Request):
        user = current_user(request)
        with get_session() as s:
            recs = s.query(models.UsageRecord).filter(models.UsageRecord.user_id == user.id).all()
        total_prompt = sum(r.prompt_tokens for r in recs)
        total_completion = sum(r.completion_tokens for r in recs)
        return {
            "requests": len(recs),
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "recent": [
                {"model": r.model, "prompt": r.prompt_tokens,
                 "completion": r.completion_tokens, "ts": r.created_at}
                for r in recs[-20:]
            ],
        }

    # --- idle reaper: mark idle runtimes and stop containers after N minutes
        # last_activity is a module-level global (see module scope)

    def reap_idle_runtimes() -> None:
        cutoff = time.time() - IDLE_REAP_MINUTES * 60
        client = docker_client()
        with get_session() as s:
            rts = s.query(models.Runtime).all()
            for rt in rts:
                last = last_activity.get(rt.user_id, 0)  # module-level last_activity
                if last > 0 and (time.time() - last) > cutoff:
                    if rt.status != "idle":
                        rt.status = "idle"
                        s.add(rt)
                        s.commit()
                    try:
                        c = client.containers.get(rt.container_name)
                        if c.status == "exited" or c.status == "created":
                            rt.status = "idle"
                            s.add(rt)
                            s.commit()
                    except Exception as e:
                        print(f"[srge] reaper: inspect {rt.container_name} failed: {e}", file=sys.stderr)

    @app.on_event("startup")
    def _start_reaper():
        import threading
        def loop():
            while True:
                time.sleep(IDLE_REAP_INTERVAL)
                try:
                    reap_idle_runtimes()
                except Exception as e:
                    print(f"[srge] reaper error: {e}", file=sys.stderr)
        threading.Thread(target=loop, daemon=True).start()

    # --- OpenCode proxy: forward to the user's runtime with its stored password
    @app.api_route("/user/opencode/{path:path}", methods=["GET", "POST", "DELETE", "PATCH"])
    async def opencode_proxy(path: str, request: Request):
        user = current_user(request)
        with get_session() as s:
            rt = s.query(models.Runtime).filter(models.Runtime.user_id == user.id).first()
        if rt is None:
            raise HTTPException(404, "no runtime provisioned; call /user/runtime/provision first")
        last_activity[user.id] = time.time()
        # Reach the runtime via its container bridge IP (bind 0.0.0.0). Fall
        # back to the host port mapping if the IP is unknown (legacy runtimes).
        host = rt.container_ip or "127.0.0.1"
        endpoint = f"http://{host}:{OPENCODE_PORT}/{path}"
        auth = "Basic " + base64.b64encode(f"opencode:{rt.opencode_password}".encode()).decode()
        body = await request.body()
        headers = {
            "Authorization": auth,
            "Content-Type": request.headers.get("Content-Type", "application/json"),
        }
        method = request.method
        params = dict(request.query_params)
        from fastapi.responses import StreamingResponse
        headers_out = {"Content-Type": "text/event-stream"} if "text/event-stream" in (request.headers.get("Accept") or "") else None
        async def streamer():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    method,
                    endpoint,
                    content=body if body else None,
                    headers=headers,
                    params=params,
                    follow_redirects=True,
                ) as resp:
                    if resp.status_code >= 400:
                        err = await resp.aread()
                        yield err
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        try:
            return StreamingResponse(streamer(), status_code=200, headers=headers_out or {})
        except httpx.HTTPError as e:
            raise HTTPException(502, f"opencode runtime unreachable: {e}")

    # --- vLLM SSE sanitizing proxy (compatibility adapter)
    # The OpenCode binary's bundled OpenAI-compatible adapter chokes on vLLM's
    # extra streaming fields. This proxy strips the proven incompatible fields
    # so OpenCode's parser sees a clean OpenAI-format stream. The vLLM engine
    # container is left untouched (other services depend on it).
    VLLM_PROXY_STRIP_FIELDS = {"token_ids", "stop_reason", "system_fingerprint", "prompt_token_ids", "prompt_text"}

    def _sanitize_sse_line(line: str) -> str:
        if not line.startswith("data:"):
            return line
        payload = line[5:].strip()
        if payload == "[DONE]":
            return line
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return line
        changed = False
        for field in VLLM_PROXY_STRIP_FIELDS:
            if field in obj:
                del obj[field]
                changed = True
        for ch in obj.get("choices", []):
            if isinstance(ch, dict):
                for field in VLLM_PROXY_STRIP_FIELDS:
                    if field in ch:
                        del ch[field]
                        changed = True
                delta = ch.get("delta")
                if isinstance(delta, dict):
                    for field in VLLM_PROXY_STRIP_FIELDS:
                        if field in delta:
                            del delta[field]
                            changed = True
        if not changed:
            return line
        return "data: " + json.dumps(obj)

    @app.api_route("/vllm-proxy/v1/chat/completions", methods=["POST"])
    async def vllm_proxy_chat(request: Request):
        user = current_user(request)
        body = await request.json()
        if "model" not in body:
            body["model"] = "qwen3.8-27b"
        if body.get("stream"):
            body["stream_options"] = {**(body.get("stream_options") or {}), "include_usage": True}
        headers = {"Content-Type": "application/json"}
        if VLLM_API_KEY:
            headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
        stream = body.get("stream")

        from fastapi.responses import StreamingResponse

        async def streamer():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    VLLM_BASE_URL + "/chat/completions",
                    json=body,
                    headers=headers,
                    follow_redirects=True,
                ) as resp:
                    if resp.status_code >= 400:
                        err = await resp.aread()
                        yield err
                        return
                    if stream:
                        buf = ""
                        async for raw in resp.aiter_text():
                            buf += raw
                            while "\n" in buf:
                                line, buf = buf.split("\n", 1)
                                yield _sanitize_sse_line(line) + "\n"
                        if buf:
                            yield _sanitize_sse_line(buf) + "\n"
                    else:
                        data = await resp.aread()
                        try:
                            obj = json.loads(data)
                            for field in VLLM_PROXY_STRIP_FIELDS:
                                obj.pop(field, None)
                        except (ValueError, json.JSONDecodeError):
                            pass
                        else:
                            data = json.dumps(obj).encode("utf-8")
                        # usage accounting
                        try:
                            obj = json.loads(data)
                            usage = obj.get("usage") or {}
                            rec = models.UsageRecord(
                                user_id=user.id,
                                model=obj.get("model", "unknown"),
                                prompt_tokens=usage.get("prompt_tokens", 0),
                                completion_tokens=usage.get("completion_tokens", 0),
                                total_tokens=usage.get("total_tokens", 0),
                                latency_ms=0,
                                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            )
                            with get_session() as s:
                                s.add(rec)
                                s.commit()
                        except (ValueError, json.JSONDecodeError):
                            pass
                        yield data

        try:
            if stream:
                return StreamingResponse(streamer(), media_type="text/event-stream")
            else:
                return StreamingResponse(streamer(), media_type="application/json")
        except httpx.HTTPError as e:
            raise HTTPException(502, f"vLLM proxy error: {e}")

    # --- Prometheus metrics (private, admin-only dashboard per ADR 009)
    def _all_usage():
        with get_session() as s:
            return s.query(models.UsageRecord).all()

    def _all_runtimes():
        with get_session() as s:
            return s.query(models.Runtime).all()

    @app.get("/metrics")
    def metrics():
        import subprocess
        out = []
        recs = _all_usage()
        out.append(f'srge_llm_requests_total {len(recs)}')
        out.append(f'srge_llm_prompt_tokens {sum(r.prompt_tokens for r in recs)}')
        out.append(f'srge_llm_completion_tokens {sum(r.completion_tokens for r in recs)}')
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                util, mem_used, mem_total = r.stdout.strip().split(",")
                out.append(f'srge_gpu_utilization {int(util)}')
                out.append(f'srge_gpu_mem_used {mem_used}')
                out.append(f'srge_gpu_mem_total {mem_total}')
        except Exception:
            out.append("# nvidia-smi unavailable")
        out.append(f'srge_runtimes_total {len(_all_runtimes())}')
        return "\n".join(out) + "\n"

    # --- health
    @app.get("/healthz")
    def healthz():
        return {"ok": True, "vllm_base": VLLM_BASE_URL}

    return app


app = create_app()
