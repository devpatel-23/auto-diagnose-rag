import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AutoMechAI Frontend", docs_url=None, redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(os.path.join(PUBLIC_DIR, "index.html"))

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    return FileResponse(os.path.join(PUBLIC_DIR, "index.html"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("frontend.app:app", host="0.0.0.0", port=port, reload=True)
