from fastapi import FastAPI, HTTPException
from utils.service_utils import process_crawl


app = FastAPI()

@app.post("/crawl/")
def crawl_article(data: dict):
    try:
        return process_crawl(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))