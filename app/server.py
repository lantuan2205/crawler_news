# app/stop_server.py
import threading
import uvicorn
from fastapi import FastAPI
import os
import signal
import sys

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "running", "pid": os.getpid()}

@app.post("/stop")
def stop_crawl():
    pid = 1  # PID của process uvicorn (FastAPI)
    os.kill(pid, signal.SIGTERM)  # Gửi tín hiệu SIGTERM cho process chính
    return {"status": f"Stopping process {pid}"}


def _run_server(port: int = 8111, host: str = "0.0.0.0"):
    uvicorn.run(app, host=host, port=port, log_level="info")


def start_background_server(port: int = 8111, host: str = "0.0.0.0"):
    server_thread = threading.Thread(
        target=_run_server,
        kwargs={"port": port, "host": host},
        daemon=True
    )
    server_thread.start()
    return server_thread




