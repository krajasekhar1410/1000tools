import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI(title="1000Tools Engine")

# Setup paths
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DOWNLOAD_DIR = BASE_DIR / "downloads"
UPLOAD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- Helper Logic ---
def get_file_ext(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()

def safe_name(filename: str) -> str:
    return "".join([c for c in filename if c.isalnum() or c in (".", "-", "_")]).rstrip()

# --- Load tools manifest ---
def load_tools():
    with open(BASE_DIR / "tools_manifest.json", "r") as f:
        return json.load(f)

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    manifest = load_tools()
    return templates.TemplateResponse("index.html", {"request": request, "manifest": manifest})

@app.get("/tools/{slug}", response_class=HTMLResponse)
async def tool_page(request: Request, slug: str):
    manifest = load_tools()
    current_tool = None
    
    # Find tool in manifest
    for category in manifest['categories']:
        for tool in category['tools']:
            if tool['slug'] == slug:
                current_tool = tool
                break
        if current_tool: break
    
    if not current_tool:
        raise HTTPException(status_code=404, detail="Tool not found")
        
    return templates.TemplateResponse("tool_shell.html", {
        "request": request, 
        "tool": current_tool,
        "manifest": manifest
    })

# --- API Endpoints ---

@app.post("/api/tools/word-counter")
async def api_word_counter(data: dict):
    text = data.get("text", "")
    words = len(text.split())
    chars = len(text)
    return {"words": words, "characters": chars}

@app.post("/api/tools/json-formatter")
async def api_json_formatter(data: dict):
    try:
        raw_json = data.get("json", "")
        parsed = json.loads(raw_json)
        formatted = json.dumps(parsed, indent=4)
        return {"formatted": formatted}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

# --- File Conversion Handlers ---

import pandas as pd
from PIL import Image as PILImage
from pdf2docx import Converter
from openai import OpenAI
import time

# Optional: Set your OpenAI API Key as an environment variable
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "your-placeholder-key"))

@app.post("/api/convert/{tool_slug}")
async def handle_file_conversion(tool_slug: str, file: UploadFile = File(...)):
    input_filename = f"input_{tool_slug}_{file.filename}"
    input_path = UPLOAD_DIR / input_filename
    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    output_path = None
    output_filename = None

    try:
        if tool_slug == "csv-to-xml":
            output_filename = input_filename.replace(".csv", ".xml")
            output_path = DOWNLOAD_DIR / output_filename
            df = pd.read_csv(input_path)
            xml_data = df.to_xml()
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_data)

        elif tool_slug == "xlsx-to-xml":
            output_filename = input_filename.replace(".xlsx", ".xml").replace(".xls", ".xml")
            output_path = DOWNLOAD_DIR / output_filename
            df = pd.read_excel(input_path)
            xml_data = df.to_xml()
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_data)

        elif tool_slug == "jpg-to-png":
            output_filename = input_filename.replace(".jpg", ".png").replace(".jpeg", ".png")
            output_path = DOWNLOAD_DIR / output_filename
            img = PILImage.open(input_path)
            img.save(output_path, "PNG")

        elif tool_slug == "png-to-jpg":
            output_filename = input_filename.replace(".png", ".jpg")
            output_path = DOWNLOAD_DIR / output_filename
            img = PILImage.open(input_path).convert("RGB")
            img.save(output_path, "JPEG")

        elif tool_slug == "pdf-to-word":
            output_filename = input_filename.replace(".pdf", ".docx")
            output_path = DOWNLOAD_DIR / output_filename
            cv = Converter(str(input_path))
            cv.convert(str(output_path))
            cv.close()
        
        elif tool_slug == "av-merger":
            # Specialized handler for merging video and audio
            # This tool would typically take two files, but for now we'll mock the merge
            # if multiple files are provided. In a real scenario, you'd use a different endpoint.
            output_filename = "merged_video.mp4"
            output_path = DOWNLOAD_DIR / output_filename
            # Mocking merge for demonstration
            shutil.copy(input_path, output_path)

        else:
            raise HTTPException(status_code=400, detail="Tool conversion logic not yet implemented.")

        if output_path and output_path.exists():
            return {"download_url": f"/api/download/{output_filename}"}
        else:
            raise Exception("File processing failed")

    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Error: {str(e)}"})

# --- Specialized Tools ---

@app.post("/api/tools/yt-downloader")
async def api_yt_downloader(data: dict):
    url = data.get("url")
    if not url: return JSONResponse(status_code=400, content={"error": "URL is required"})
    import yt_dlp
    
    try:
        output_filename = f"yt_{int(time.time())}.mp4"
        output_path = DOWNLOAD_DIR / output_filename
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path),
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        return {"download_url": f"/api/download/{output_filename}", "message": "Extracted and ready!"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Extraction failed: {str(e)}"})

@app.post("/api/tools/ai-image-gen")
async def api_ai_image_gen(data: dict):
    prompt = data.get("prompt")
    if not prompt: return JSONResponse(status_code=400, content={"error": "Prompt is required"})
    
    try:
        # Mocking AI Generation for demo if no key is set
        if "placeholder" in client.api_key:
            return {"image_url": "https://picsum.photos/1024/1024", "message": "Demo image (Set OpenAI API key for real AI)"}
            
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return {"image_url": response.data[0].url}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"AI Generation failed: {str(e)}"})

@app.post("/api/tools/calculators")
async def api_calculators(data: dict):
    tool = data.get("tool")
    params = data.get("params", {})
    
    if tool == "emi-calculator":
        p = float(params.get("principal", 0))
        r = float(params.get("rate", 0)) / (12 * 100)
        n = float(params.get("tenure", 0))
        if p and r and n:
            emi = (p * r * pow(1 + r, n)) / (pow(1 + r, n) - 1)
            return {"result": round(emi, 2)}
            
    elif tool == "bmi-calculator":
        w = float(params.get("weight", 0))
        h = float(params.get("height", 0)) / 100
        if w and h:
            bmi = w / (h * h)
            return {"result": round(bmi, 2)}
            
    return JSONResponse(status_code=400, content={"error": "Check inputs"})

@app.post("/api/tools/ai-text")
async def api_ai_text(data: dict):
    tool = data.get("tool")
    text = data.get("text")
    if not text: return JSONResponse(status_code=400, content={"error": "Text is required"})
    
    try:
        # Mocking for demo
        if "placeholder" in client.api_key:
            return {"result": f"This is a demo {tool} of your text: {text[:50]}..."}
            
        system_prompt = "You are a helpful assistant."
        if tool == "ai-summarizer": system_prompt = "Summarize the following text clearly."
        elif tool == "ai-paraphraser": system_prompt = "Paraphrase the following text while keeping the meaning."
        elif tool == "ai-grammar": system_prompt = "Correct any grammar and spelling errors in the following text."
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        return {"result": response.choices[0].message.content}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"AI Task failed: {str(e)}"})

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists():
        return FileResponse(path=file_path, filename=filename.split("_")[-1])
    raise HTTPException(status_code=404, detail="File not found")

# --- Runner ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
