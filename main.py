from fastapi import FastAPI

app = FastAPI(title="Media Pipeline", version="0.1.0")

# TODO: include_router(...) from api/* when implemented

@app.get("/health")
def health():
    return {"status": "ok"}
