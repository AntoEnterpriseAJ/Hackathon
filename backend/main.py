from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")  # explicit path, works regardless of cwd

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from routers import documents  # noqa: E402

app = FastAPI(title="Teacher Paperwork Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Shift-Report"],
)

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
