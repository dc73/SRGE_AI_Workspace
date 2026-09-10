from fastapi import FastAPI
from fastapi.responses import JSONResponse
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

@app.get("/metrics")
def metrics():
    """SRGE-specific resource data (GPU, inference queue, workspace usage)."""
    data = {
        "capacity_state": "Available",
        "gpu_util_pct": None,
        "inference_queue_depth": 0,
        "active_workspaces": 0,
        "note": "Populated by Phase 5/6 with live values."
    }
    return data
