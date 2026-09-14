from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
import httpx, os, json

app = FastAPI(title="SRGE Control API")

VLLM_BASE = os.environ.get("SRGE_VLLM_BASE_URL", "http://qwen38:8000/v1")
PROM_BASE = os.environ.get("SRGE_PROMETHEUS_BASE_URL", "http://prometheus:9090")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/health")
def health():
    """Aggregate health of Qwen (vLLM), Coder, and Prometheus."""
    results = {}
    client = httpx.Client(timeout=5)
    try:
        r = client.get(VLLM_BASE + "/models")
        results["qwen"] = {"status": "up" if r.status_code == 200 else "down", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        results["qwen"] = {"status": "down", "detail": str(e)}
    try:
        r = client.get("http://srge-coder:7080/api/v2/buildinfo")
        results["coder"] = {"status": "up" if r.status_code == 200 else "down", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        results["coder"] = {"status": "down", "detail": str(e)}
    try:
        r = client.get(PROM_BASE + "/-/healthy")
        results["prometheus"] = {"status": "up" if r.status_code == 200 else "down", "detail": f"HTTP {r.status_code}"}
    except Exception as e:
        results["prometheus"] = {"status": "down", "detail": str(e)}
    client.close()
    return results

@app.get("/metrics", response_class=Response)
def metrics():
    """SRGE-specific resource data in Prometheus text exposition format."""
    lines = [
        "# HELP srge_capacity_state 1 = available, 0 = exhausted",
        "# TYPE srge_capacity_state gauge",
        "srge_capacity_state 1",
        "# HELP srge_gpu_util_pct GPU utilization percentage",
        "# TYPE srge_gpu_util_pct gauge",
        "srge_gpu_util_pct 0",
        "# HELP srge_inference_queue_depth Current inference queue depth",
        "# TYPE srge_inference_queue_depth gauge",
        "srge_inference_queue_depth 0",
        "# HELP srge_active_workspaces Number of active Coder workspaces",
        "# TYPE srge_active_workspaces gauge",
        "srge_active_workspaces 0",
    ]
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
