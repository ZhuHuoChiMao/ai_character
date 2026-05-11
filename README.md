# AI Character Local LoRA Lab

这是一个本地 TXT 到个性化 AI 训练的实验项目。前端上传 `.txt` 文件，后端通过 ChatGPT 辅助生成 JSONL 训练数据，再用本地 LoRA 流程训练并加载角色模型。

## 功能流程

1. 在前端为 AI 命名并上传 `.txt` 文件。
2. 后端保存原文到 `uploads/source.txt`，并生成 `work/prompt.txt`。
3. Playwright 打开 ChatGPT，你在浏览器中手动登录。
4. 脚本把 prompt 输入 ChatGPT，并上传 txt 文件。
5. 脚本下载或提取 JSONL，保存到 `datasets/<AI名称>.jsonl`。
6. 后端校验 JSONL，并生成 `datasets/<AI名称>.preview.json`。
7. 校验通过后启动本地 LoRA 微调。
8. 训练完成后模型保存到 `models/<AI名称>/`，网页聊天窗口可以加载并对话。

## 目录说明

```text
backend/                         FastAPI 后端和训练流程
frontend/                        前端页面
chatgpt-login-only-extension/    ChatGPT 登录辅助扩展
tools/                           本地安装包构建脚本
start-edge-cdp.ps1               启动 Edge 调试浏览器
start-chrome-cdp.ps1             启动 Chrome 调试浏览器
```

以下目录是本地生成内容，不会提交到 Git：

```text
backend/.venv/
uploads/
work/
datasets/
models/
frontend/downloads/
edge-cdp-profile/
chrome-cdp-profile/
playwright-profile/
msedge-cdp-profile/
```

## 安装后端依赖

在 PowerShell 中执行：

```powershell
cd C:\Users\dell\Desktop\ai_web_project\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

如果你的电脑没有 Python 3.12，可以把 `py -3.12` 换成 `python`。

## 启动后端

```powershell
cd C:\Users\dell\Desktop\ai_web_project\backend
.\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

后端启动后可以打开：

```text
http://127.0.0.1:8000/app/
```

也可以直接打开前端文件：

```text
C:\Users\dell\Desktop\ai_web_project\frontend\index.html
```

## 使用调试浏览器连接 ChatGPT

推荐先启动带调试端口的 Edge 或 Chrome，然后在这个浏览器窗口里手动登录 ChatGPT。

启动 Edge：

```powershell
cd C:\Users\dell\Desktop\ai_web_project
.\start-edge-cdp.ps1
```

启动 Chrome：

```powershell
cd C:\Users\dell\Desktop\ai_web_project
.\start-chrome-cdp.ps1
```

默认调试地址：

```text
http://127.0.0.1:9222
```

如果只允许连接调试浏览器，不希望连接失败后自动启动新浏览器：

```powershell
$env:CHATGPT_CONNECT_MODE="cdp"
```

默认模式是：

```powershell
$env:CHATGPT_CONNECT_MODE="cdp-first"
```

## 选择浏览器

默认使用 Microsoft Edge：

```powershell
$env:CHATGPT_BROWSER="msedge"
```

使用 Google Chrome：

```powershell
$env:CHATGPT_BROWSER="chrome"
```

使用 Playwright 自带 Chromium：

```powershell
$env:CHATGPT_BROWSER="chromium"
```

## LoRA 训练

训练前需要安装额外依赖：

```powershell
cd C:\Users\dell\Desktop\ai_web_project\backend
.\.venv\Scripts\python -m pip install -r requirements-train.txt
```

默认基础模型是代码中的 `Qwen/Qwen3-4B-Instruct-2507`。也可以手动设置：

```powershell
$env:BASE_MODEL="C:\models\your-base-model"
```

训练输出会保存在：

```text
models/<AI名称>/
```

## 本地安装包

`frontend/index.html` 中有下载安装包入口，但 `frontend/downloads/` 属于生成文件目录，没有提交到 GitHub。

需要重新生成安装包时运行：

```powershell
cd C:\Users\dell\Desktop\ai_web_project
.\tools\build-local-agent-package.ps1
.\tools\build-windows-installer.ps1
```

## Git 说明

仓库已经配置 `.gitignore`，不会上传虚拟环境、模型、数据集、浏览器 profile、安装包和临时工作目录。需要共享大模型或数据集时，建议使用单独的网盘、Release 附件或 Git LFS。
