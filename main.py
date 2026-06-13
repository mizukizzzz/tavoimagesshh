from pathlib import Path
from uuid import uuid4
from datetime import datetime
from urllib.parse import quote
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allows Tavo to securely connect to our server across domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pull the secret key securely from the environment variables
POLLINATIONS_KEY = os.environ.get("POLLINATIONS_API_KEY")
if not POLLINATIONS_KEY:
    raise RuntimeError("Missing POLLINATIONS_API_KEY environment variable")

BASE_URL = os.environ.get("IMAGE_FORGE_BASE_URL", "").rstrip("/")
BASE_DIR = Path("./media/forge_runs")
BASE_DIR.mkdir(parents=True, exist_ok=True)

class ImageJob(BaseModel):
    prompt: str
    model: str = "flux"
    width: int = 1024
    height: int = 1024

@app.post("/image-jobs")
async def create_image(job: ImageJob, request: Request):
    # Dynamically detects the Render secure HTTPS URL if IMAGE_FORGE_BASE_URL isn't explicitly set
    current_base = BASE_URL if BASE_URL else f"{request.url.scheme}://{request.url.netloc}"
    
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:8]
    job_dir = BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    encoded_prompt = quote(job.prompt)

    # Building the Pollinations secure generation URL
    pollinations_url = (
        f"https://gen.pollinations.ai/image/{encoded_prompt}"
        f"?width={job.width}"
        f"&height={job.height}"
        f"&model={job.model}"
        f"&key={POLLINATIONS_KEY}"
    )

    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.get(pollinations_url)

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch from Pollinations")

    image_path = job_dir / "image.jpg"
    image_path.write_bytes(response.content)

    image_url = f"{current_base}/images/{job_id}/image.jpg"

    return {
        "id": job_id,
        "image_url": image_url,
        "markdown": f"![Generated image]({image_url})",
    }

@app.get("/images/{job_id}/image.jpg")
def get_image(job_id: str):
    path = BASE_DIR / job_id / "image.jpg"

    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(path)
