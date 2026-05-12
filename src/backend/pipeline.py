import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
UPLOADS = ROOT / "uploads"
WORK = ROOT / "work"
DATASETS = ROOT / "datasets"
MODELS = ROOT / "models"
STATUS_PATH = WORK / "status.json"
OVERLAY_PID_PATH = WORK / "browser_overlay.pid"
CDP_PORT = 9222
LOGIN_EXTENSION = ROOT / "chatgpt-login-only-extension"

for directory in (UPLOADS, WORK, DATASETS, MODELS):
    directory.mkdir(parents=True, exist_ok=True)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def get_status():
    if not STATUS_PATH.exists():
        return {"stage": "idle", "message": "等待上传 txt 文件", "updated_at": _now()}
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def update_status(stage, message, **extra):
    payload = get_status()
    payload.update({"stage": stage, "message": message, "updated_at": _now()})
    payload.update(extra)
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _safe_ai_name(ai_name=None):
    raw = (ai_name or get_status().get("ai_name") or "").strip()
    if not raw:
        raise ValueError("请先为 AI 命名")
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .")
    safe = re.sub(r"\s+", "_", safe)
    if not safe:
        raise ValueError("AI 名称不能只包含特殊字符")
    return raw, safe[:80]


def _dataset_path(ai_name=None):
    display_name, safe_name = _safe_ai_name(ai_name)
    return display_name, safe_name, DATASETS / f"{safe_name}.jsonl"


def _model_path(ai_name=None):
    display_name, safe_name = _safe_ai_name(ai_name)
    return display_name, safe_name, MODELS / safe_name


def list_lora_models():
    models = []
    for path in sorted(MODELS.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        weight_files = sorted(
            item.name
            for item in path.iterdir()
            if item.is_file() and item.name.startswith("adapter_model")
        )
        has_adapter_config = (path / "adapter_config.json").exists()
        if not weight_files and not has_adapter_config:
            continue
        models.append(
            {
                "name": path.name,
                "path": str(path),
                "weight_files": weight_files,
            }
        )
    return {"models": models}


def _safe_decode(content):
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def build_prompt():
    return """请将我上传的整个 txt 文件转换为可下载的 JSONL 文件，文件名使用 train.jsonl。

每一行必须是一个独立 JSON 对象，并且只能使用下面三个字段：

{"fields": [...], "prompt_q": "...", "prompt_a": "..."}

字段要求：
1. fields：从原文中抽取与这一条问答相关的背景、人物、事实、上下文或结构化信息。必须是数组，可以是字符串数组，也可以是嵌套数组；数组里最终必须包含文本。
2. prompt_q：根据原文生成的问题，必须是非空字符串。
3. prompt_a：根据原文生成的答案，必须是非空字符串。

转换要求：
1. 覆盖整个 txt 文件，不要只处理开头或摘要。
2. 尽量把原文拆成多条训练样本；每条样本都要能独立用于训练。
3. 不要输出解释、Markdown 表格或额外文字。
4. 优先提供 train.jsonl 下载文件；如果不能提供下载文件，就直接在回答中输出完整 JSONL 内容。
"""


def prepare_uploaded_txt(filename, content):
    text = _safe_decode(content)
    source_path = UPLOADS / "source.txt"
    prompt_path = WORK / "prompt.txt"
    source_path.write_text(text, encoding="utf-8")
    (UPLOADS / "source_filename.txt").write_text(filename, encoding="utf-8")
    prompt_path.write_text(build_prompt(), encoding="utf-8")
    update_status(
        "uploaded",
        "txt 已上传，prompt 已生成。下一步运行 Playwright 打开 ChatGPT。",
        filename=filename,
        source_path=str(source_path),
        prompt_path=str(prompt_path),
        chars=len(text),
    )
    return {"message": "txt 已上传，prompt 已生成", "filename": filename, "chars": len(text), "prompt_path": str(prompt_path)}


def run_chatgpt_pipeline(browser=None):
    prompt_path = WORK / "prompt.txt"
    if not prompt_path.exists():
        raise RuntimeError("缺少 work/prompt.txt，请先上传 txt 文件")
    update_status("chatgpt_running", "Playwright 正在打开 ChatGPT。请手动登录；脚本会输入 prompt 并通过添加文件上传 txt。")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if browser:
        env["CHATGPT_BROWSER_REQUESTED"] = browser
    process = subprocess.run(
        [sys.executable, str(BACKEND / "chatgpt_automation.py")],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "ChatGPT 自动化失败").strip())
    update_status("chatgpt_done", "train.jsonl 已保存，开始校验。", output=process.stdout.strip())
    return validate_dataset()


def _port_is_open(host="127.0.0.1", port=CDP_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _browser_executable(browser):
    requested = (browser or os.environ.get("CHATGPT_BROWSER") or "msedge").strip().lower()
    if requested in {"edge", "msedge", "microsoft-edge"}:
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        normalized = "msedge"
    elif requested in {"chrome", "google-chrome"}:
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
        normalized = "chrome"
    else:
        raise RuntimeError("browser 只支持 msedge 或 chrome")

    for candidate in candidates:
        if candidate.exists():
            return normalized, candidate
    raise RuntimeError(f"未找到 {normalized} 浏览器程序")


def _sanitize_color(value):
    value = (value or "#f4efe6").strip()
    if len(value) == 7 and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:]):
        return value
    return "#f4efe6"


def _stop_existing_overlay():
    if not OVERLAY_PID_PATH.exists():
        return
    try:
        pid = int(OVERLAY_PID_PATH.read_text(encoding="utf-8").strip())
        os.kill(pid, 15)
    except Exception:
        pass
    try:
        OVERLAY_PID_PATH.unlink()
    except OSError:
        pass


def stop_window_overlay():
    _stop_existing_overlay()
    update_status("overlay_stopped", "遮罩条已关闭")
    return {"message": "遮罩条已关闭"}


def _start_window_overlay(width, height, x, y, bg, text=""):
    if not all(value is not None for value in (width, height, x, y)):
        return None
    _stop_existing_overlay()
    process = subprocess.Popen(
        [
            sys.executable,
            str(BACKEND / "window_overlay.py"),
            "--x",
            str(int(x)),
            "--y",
            str(int(y)),
            "--width",
            str(max(320, int(width))),
            "--height",
            str(max(240, int(height))),
            "--color",
            _sanitize_color(bg),
            "--text",
            text,
        ],
        cwd=str(BACKEND),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    OVERLAY_PID_PATH.write_text(str(process.pid), encoding="utf-8")
    return process.pid


def update_window_overlay(width=None, height=None, x=None, y=None, bg=None, text=""):
    overlay_pid = _start_window_overlay(width, height, x, y, bg, text=text)
    update_status("overlay_updated", text or "遮罩条已更新", overlay_pid=overlay_pid)
    return {"message": "遮罩条已更新", "overlay_pid": overlay_pid}


def start_debug_browser(browser=None, width=None, height=None, x=None, y=None, bg=None):
    normalized, executable = _browser_executable(browser)
    if _port_is_open():
        update_status("browser_ready", "远程调试浏览器已经在运行，可以登录 ChatGPT 后继续第二步。", browser=normalized)
        return {
            "message": "远程调试浏览器已经在运行",
            "browser": normalized,
            "cdp_url": f"http://127.0.0.1:{CDP_PORT}",
        }

    profile_dir = ROOT / f"{normalized}-cdp-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch_args = [
        str(executable),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        f"--disable-extensions-except={LOGIN_EXTENSION}",
        f"--load-extension={LOGIN_EXTENSION}",
    ]
    if width and height:
        launch_args.append(f"--window-size={max(320, int(width))},{max(240, int(height))}")
    if x is not None and y is not None:
        launch_args.append(f"--window-position={int(x)},{int(y)}")
    launch_args.append("https://chatgpt.com/")

    window = {"width": width, "height": height, "x": x, "y": y}
    overlay_pid = _start_window_overlay(width, height, x, y, bg, text="请完成登录")
    subprocess.Popen(
        launch_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    update_status(
        "browser_started",
        "调试浏览器已启动。请在新窗口里登录 ChatGPT，然后回到本地网页点击第二步。",
        browser=normalized,
        cdp_url=f"http://127.0.0.1:{CDP_PORT}",
        profile_path=str(profile_dir),
        window=window,
        overlay_pid=overlay_pid,
    )
    return {
        "message": "调试浏览器已启动，请在新窗口里登录 ChatGPT",
        "browser": normalized,
        "cdp_url": f"http://127.0.0.1:{CDP_PORT}",
        "profile_path": str(profile_dir),
        "extension_path": str(LOGIN_EXTENSION),
        "window": window,
        "overlay_pid": overlay_pid,
    }


def browser_status(browser=None):
    normalized, executable = _browser_executable(browser)
    profile_dir = ROOT / f"{normalized}-cdp-profile"
    connected = _port_is_open()
    return {
        "browser": normalized,
        "browser_path": str(executable),
        "connected": connected,
        "cdp_url": f"http://127.0.0.1:{CDP_PORT}",
        "profile_path": str(profile_dir),
        "extension_path": str(LOGIN_EXTENSION),
        "message": "调试浏览器已连接，可以登录 ChatGPT 后继续第二步。" if connected else "调试浏览器未连接，请点击启动调试浏览器。",
    }


def _has_text(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_text(item) for item in value)
    return False


def _validate_train_item(obj, line_no):
    if not isinstance(obj, dict):
        raise ValueError(f"第 {line_no} 行不是 JSON 对象")

    required = {"fields", "prompt_q", "prompt_a"}
    missing = required - set(obj)
    if missing:
        raise ValueError(f"第 {line_no} 行缺少字段: {', '.join(sorted(missing))}")

    if not isinstance(obj["fields"], list) or not _has_text(obj["fields"]):
        raise ValueError(f"第 {line_no} 行 fields 必须是包含文本的数组")
    if not isinstance(obj["prompt_q"], str) or not obj["prompt_q"].strip():
        raise ValueError(f"第 {line_no} 行 prompt_q 不能为空")
    if not isinstance(obj["prompt_a"], str) or not obj["prompt_a"].strip():
        raise ValueError(f"第 {line_no} 行 prompt_a 不能为空")


def validate_dataset():
    train_path = DATASETS / "train.jsonl"
    preview_path = DATASETS / "preview.json"
    if not train_path.exists():
        raise RuntimeError("缺少 datasets/train.jsonl")
    content = train_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError("train.jsonl 是空文件")
    lines = [line for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines, start=1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"第 {index} 行不是合法 JSON: {exc}") from exc
        _validate_train_item(obj, index)

    preview = [{"line": index + 1, "text": line} for index, line in enumerate(lines[:10])]
    preview_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    update_status(
        "validated",
        "train.jsonl 结构校验通过，preview.json 已保存。可以继续本地实验。",
        rows=len(lines),
        train_path=str(train_path),
        preview_path=str(preview_path),
    )
    return {"message": "校验通过：每行都包含 fields、prompt_q、prompt_a 且有文本", "rows": len(lines), "train_path": str(train_path), "preview_path": str(preview_path), "preview": preview}


def start_lora_training():
    if not (DATASETS / "train.jsonl").exists():
        raise RuntimeError("缺少 datasets/train.jsonl")
    validate_dataset()
    # base_model = os.environ.get("BASE_MODEL", "").strip()
    # if not base_model:
    #     raise RuntimeError("未设置 BASE_MODEL。请设置本地基础模型路径或 Hugging Face 模型名后再训练。")
    base_model = os.environ.get("BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507").strip()
    update_status("training", "LoRA 微调已启动，请等待训练完成。", base_model=base_model)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.run(
        [sys.executable, str(BACKEND / "train_lora.py")],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "LoRA 微调失败").strip())
    update_status("trained", "LoRA 微调完成，可以加载模型。", output=process.stdout.strip())
    return {"message": "LoRA 微调完成", "model_path": str(MODELS / "lora")}


def load_model():
    model_path = MODELS / "lora"
    if not model_path.exists():
        raise RuntimeError("缺少 models/lora，请先完成 LoRA 微调")
    update_status("loaded", "模型已标记为加载状态，网页聊天窗口可以开始对话。", model_path=str(model_path))
    return {"message": "模型已加载", "model_path": str(model_path)}


def chat_with_loaded_model(message):
    if get_status().get("stage") != "loaded":
        raise RuntimeError("模型尚未加载")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.run(
        [sys.executable, str(BACKEND / "chat_lora.py"), message],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "模型对话失败").strip())
    return {"reply": process.stdout.strip()}


def build_prompt(dataset_filename):
    return f"""请将我上传的整个 txt 文件转换为可下载的 JSONL 文件，文件名必须使用 {dataset_filename}。

每一行必须是一个独立 JSON 对象，并且只能使用下面三个字段：

{{"fields": [...], "prompt_q": "...", "prompt_a": "..."}}

字段要求：
1. fields：从原文中抽取与这一条问答相关的背景、人物、事实、上下文或结构化信息。必须是数组，可以是字符串数组，也可以是嵌套数组；数组里最终必须包含文本。
2. prompt_q：根据原文生成的问题，必须是非空字符串。
3. prompt_a：根据原文生成的答案，必须是非空字符串。

转换要求：
1. 覆盖整个 txt 文件，不要只处理开头或摘要。
2. 尽量把原文拆成多条训练样本；每条样本都要能独立用于训练。
3. 不要输出解释、Markdown 表格或额外文字。
4. 优先提供 {dataset_filename} 下载文件；如果不能提供下载文件，就直接在回答中输出完整 JSONL 内容。
"""


def prepare_uploaded_txt(filename, content, ai_name):
    display_name, safe_name, dataset_path = _dataset_path(ai_name)
    text = _safe_decode(content)
    source_path = UPLOADS / "source.txt"
    prompt_path = WORK / "prompt.txt"
    source_path.write_text(text, encoding="utf-8")
    (UPLOADS / "source_filename.txt").write_text(filename, encoding="utf-8")
    prompt_path.write_text(build_prompt(dataset_path.name), encoding="utf-8")
    update_status(
        "uploaded",
        f"{display_name} 的 txt 已上传，prompt 已生成。下一步运行 Playwright 打开 ChatGPT。",
        ai_name=display_name,
        safe_ai_name=safe_name,
        dataset_filename=dataset_path.name,
        dataset_path=str(dataset_path),
        model_dir=str(MODELS / safe_name),
        filename=filename,
        source_path=str(source_path),
        prompt_path=str(prompt_path),
        chars=len(text),
    )
    return {
        "message": f"{display_name} 的 txt 已上传，prompt 已生成",
        "ai_name": display_name,
        "dataset_path": str(dataset_path),
        "model_dir": str(MODELS / safe_name),
        "filename": filename,
        "chars": len(text),
        "prompt_path": str(prompt_path),
    }


def run_chatgpt_pipeline(browser=None, ai_name=None):
    display_name, safe_name, dataset_path = _dataset_path(ai_name)
    prompt_path = WORK / "prompt.txt"
    if not prompt_path.exists():
        raise RuntimeError("缺少 work/prompt.txt，请先上传 txt 文件")
    update_status("chatgpt_running", f"Playwright 正在打开 ChatGPT，准备生成 {dataset_path.name}。")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["AI_NAME"] = display_name
    env["TRAIN_FILENAME"] = dataset_path.name
    env["TRAIN_PATH"] = str(dataset_path)
    if browser:
        env["CHATGPT_BROWSER_REQUESTED"] = browser
    process = subprocess.run(
        [sys.executable, str(BACKEND / "chatgpt_automation.py")],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "ChatGPT 自动化失败").strip())
    update_status("chatgpt_done", f"{dataset_path.name} 已保存，开始校验。", output=process.stdout.strip())
    return validate_dataset(ai_name=display_name)


def validate_dataset(ai_name=None):
    display_name, safe_name, train_path = _dataset_path(ai_name)
    preview_path = DATASETS / f"{safe_name}.preview.json"
    if not train_path.exists():
        raise RuntimeError(f"缺少 {train_path}")
    content = train_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"{train_path.name} 是空文件")
    lines = [line for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines, start=1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"第 {index} 行不是合法 JSON: {exc}") from exc
        _validate_train_item(obj, index)

    preview = [{"line": index + 1, "text": line} for index, line in enumerate(lines[:10])]
    preview_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    update_status(
        "validated",
        f"{train_path.name} 结构校验通过，preview 已保存。",
        ai_name=display_name,
        safe_ai_name=safe_name,
        dataset_filename=train_path.name,
        dataset_path=str(train_path),
        preview_path=str(preview_path),
        rows=len(lines),
    )
    return {"message": f"校验通过：{train_path.name} 每行都包含 fields、prompt_q、prompt_a 且有文本", "rows": len(lines), "train_path": str(train_path), "preview_path": str(preview_path), "preview": preview}


def start_lora_training(ai_name=None):
    display_name, safe_name, train_path = _dataset_path(ai_name)
    _, _, model_path = _model_path(display_name)
    if not train_path.exists():
        raise RuntimeError(f"缺少 {train_path}")
    validate_dataset(ai_name=display_name)
    base_model = os.environ.get("BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507").strip()
    update_status("training", f"{display_name} 的 LoRA 微调已启动，请等待训练完成。", base_model=base_model, train_path=str(train_path), model_dir=str(model_path))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["TRAIN_PATH"] = str(train_path)
    env["OUTPUT_DIR"] = str(model_path)
    env["AI_NAME"] = display_name
    process = subprocess.run(
        [sys.executable, str(BACKEND / "train_lora.py")],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "LoRA 微调失败").strip())
    update_status("trained", f"{display_name} 的 LoRA 微调完成，可以加载模型。", output=process.stdout.strip(), model_dir=str(model_path))
    return {"message": f"{display_name} 的 LoRA 微调完成", "model_path": str(model_path), "train_path": str(train_path)}


def load_model(ai_name=None):
    display_name, safe_name, model_path = _model_path(ai_name)
    if not model_path.exists():
        raise RuntimeError(f"缺少 {model_path}，请先完成 {display_name} 的 LoRA 微调")
    update_status("loaded", f"{display_name} 模型已标记为加载状态，网页聊天窗口可以开始对话。", ai_name=display_name, safe_ai_name=safe_name, model_dir=str(model_path))
    return {"message": f"{display_name} 模型已加载", "model_path": str(model_path)}


def chat_with_loaded_model(message):
    status = get_status()
    if status.get("stage") != "loaded":
        raise RuntimeError("模型尚未加载")
    model_dir = status.get("model_dir")
    if not model_dir:
        _, _, model_path = _model_path(status.get("ai_name"))
        model_dir = str(model_path)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["LORA_MODEL_PATH"] = model_dir
    process = subprocess.run(
        [sys.executable, str(BACKEND / "chat_lora.py"), message],
        cwd=str(BACKEND),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "模型对话失败").strip())
    return {"reply": process.stdout.strip()}
