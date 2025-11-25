# app/stop_server.py
import threading
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
import os
import signal
import sys

app = FastAPI()

class CrawlURLRequest(BaseModel):
    url: str


@app.get("/health")
def health():
    return {"status": "running", "pid": os.getpid()}

@app.post("/stop")
def stop_crawl():
    pid = 1  # PID của process uvicorn (FastAPI)
    os.kill(pid, signal.SIGTERM)  # Gửi tín hiệu SIGTERM cho process chính
    return {"status": f"Stopping process {pid}"}


@app.post("/crawl")
def crawl(request: CrawlURLRequest):
    from app.crawl_request import process_crawl
    url = request.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # Tạo payload chuẩn để gọi process_crawl
    payload = {
        "message": {
            "source": "NEWS",
            "action": "GENERAL",
            "body": {
                "inputData": url,
                "type": "TEXT",
                "dataToCollect": ["profile", "comment", "audio"],
                "username": "tuan",
                "password": "123",
                "email": "t@gmail.com",
                "token": "",
                "crawlId": "smart_analysis-c-22-s-114-17634389355841763438935584",
                "jobId": "5d72df7d-9e5f-4f45-abf0-9905adeba500",
                "crawlSetting": "{\"POST\":{\"AUDIENCE_INFORMATION\":true,\"AUTHOR_INFORMATION\":true,\"COMMENTS\":{\"ENABLE\":true,\"NUMBER_OF_COMMENTS\":100},\"DATE_RANGE\":30,\"ENABLE\":true,\"IMAGE_DOWNLOAD\":true,\"LOCATION\":true,\"REACTIONS\":{\"ENABLE\":true,\"NUMBER_OF_REACTIONS\":100},\"VIDEO_DOWNLOAD\":false,\"VIDEO_QUALITY\":\"HD\",\"VIDEO_THUMBNAIL\":true},\"PROFILE\":{\"ENABLE\":true}}"
            },
              "proxy": {
                "username": "hieu",
                "password": "via",
                "host": "192.111.135.156",
                "proxyType": "HTTP",
                "port": "2222"
            }
        }
    }

    try:
        result = process_crawl(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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




