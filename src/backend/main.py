from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from pipeline import (
    ROOT,
    browser_status,
    chat_with_loaded_model,
    get_status,
    list_lora_models,
    load_model,
    prepare_uploaded_txt,
    run_chatgpt_pipeline,
    start_debug_browser,
    stop_window_overlay,
    update_window_overlay,
    start_lora_training,
    update_status,
    validate_dataset,
)

app = FastAPI(title="Local TXT to LoRA Lab")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return {
        "message": "本地后端运行成功",
        "root": str(ROOT),
        "status": get_status(),
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "local-agent",
        "message": "Local Agent 已连接",
        "root": str(ROOT),
    }


@app.get("/status")
def status():
    return get_status()


@app.get("/models")
def models():
    try:
        return list_lora_models()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), ai_name: str = Form(...)):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="只接受 .txt 文件")
    content = await file.read()
    return prepare_uploaded_txt(file.filename, content, ai_name)


@app.post("/chatgpt")
def chatgpt(browser: str | None = Query(default=None), ai_name: str | None = Query(default=None)):
    try:
        return run_chatgpt_pipeline(browser=browser, ai_name=ai_name)
    except Exception as exc:
        update_status("chatgpt_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/browser/start")
def browser_start(
    browser: str | None = Query(default=None),
    width: int | None = Query(default=None),
    height: int | None = Query(default=None),
    x: int | None = Query(default=None),
    y: int | None = Query(default=None),
    bg: str | None = Query(default=None),
):
    try:
        return start_debug_browser(browser=browser, width=width, height=height, x=x, y=y, bg=bg)
    except Exception as exc:
        update_status("browser_start_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/browser/status")
def browser_status_endpoint(browser: str | None = Query(default=None)):
    try:
        return browser_status(browser=browser)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/browser/overlay/stop")
def browser_overlay_stop():
    try:
        return stop_window_overlay()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/browser/overlay/update")
def browser_overlay_update(
    width: int | None = Query(default=None),
    height: int | None = Query(default=None),
    x: int | None = Query(default=None),
    y: int | None = Query(default=None),
    bg: str | None = Query(default=None),
    text: str = Query(default=""),
):
    try:
        return update_window_overlay(width=width, height=height, x=x, y=y, bg=bg, text=text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/validate")
def validate(ai_name: str | None = Query(default=None)):
    try:
        return validate_dataset(ai_name=ai_name)
    except Exception as exc:
        update_status("validation_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/train")
def train(ai_name: str | None = Query(default=None)):
    try:
        return start_lora_training(ai_name=ai_name)
    except Exception as exc:
        update_status("training_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/load")
def load(ai_name: str | None = Query(default=None)):
    try:
        return load_model(ai_name=ai_name)
    except Exception as exc:
        update_status("load_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat")
def chat(request: ChatRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    try:
        return chat_with_loaded_model(request.message)
    except Exception as exc:
        update_status("chat_failed", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/files")
def files():
    status = get_status()
    dataset_filename = status.get("dataset_filename", "train.jsonl")
    model_dir = status.get("model_dir")
    preview_path = status.get("preview_path")
    paths = {
        "prompt": ROOT / "work" / "prompt.txt",
        "train": ROOT / "datasets" / dataset_filename,
        "preview": Path(preview_path) if preview_path else ROOT / "datasets" / "preview.json",
        "model": Path(model_dir) if model_dir else ROOT / "models" / "lora",
    }
    return {name: {"path": str(path), "exists": path.exists()} for name, path in paths.items()}
