# 本地 TXT 到 LoRA 实验项目

流程：

1. 前端上传 `.txt`
2. 后端保存 `uploads/source.txt`，生成 `work/prompt.txt`
3. Playwright 打开 ChatGPT，你手动登录
4. 脚本在聊天框输入 prompt，并通过 ChatGPT 的添加文件入口上传你的 txt 文件
5. 脚本尝试点击下载链接并保存 `datasets/train.jsonl`
6. 如果页面没有真实下载链接，脚本会从 ChatGPT 响应文本中提取 JSONL 并保存到同一路径
7. 后端读取前 10 条保存 `datasets/preview.json`
8. 校验通过后启动本地 LoRA 微调
9. 微调完成后加载模型，网页聊天窗口开始对话

## 启动后端

```powershell
cd C:\Users\dell\Desktop\ai_web_project\backend
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 选择打开 ChatGPT 的浏览器

点击前端“打开 ChatGPT 生成 train.jsonl”时，前端会根据你当前打开本地网页的浏览器自动选择：

- 用 Edge 打开本地网页，则 Playwright 尝试用 Microsoft Edge 打开 ChatGPT
- 用 Chrome 打开本地网页，则 Playwright 尝试用 Google Chrome 打开 ChatGPT

如果自动识别不到，会使用默认值。

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

## 使用远程调试浏览器连接

这是最接近手动操作的方式。先启动一个带调试端口的 Edge 或 Chrome，在这个窗口里手动登录 ChatGPT，然后脚本会连接这个窗口继续操作。

前端已经提供按钮方式：

1. 打开本地网页
2. 点击“启动调试浏览器”
3. 在新打开的 Edge/Chrome 窗口里登录 ChatGPT
4. 回到本地网页点击“2 打开 ChatGPT 生成 train.jsonl”

调试浏览器启动时会自动加载本地扩展：

```text
chatgpt-login-only-extension
```

这个扩展只在 ChatGPT/OpenAI 登录相关页面生效。未登录时会弱化无关内容、突出登录/继续/验证相关按钮；检测到聊天输入框后会自动恢复正常页面。

也可以手动运行脚本：

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

然后在打开的浏览器窗口里登录 ChatGPT。登录完成后，回到本地网页点击“2 打开 ChatGPT 生成 train.jsonl”。

默认连接地址：

```text
http://127.0.0.1:9222
```

如果你只想使用远程调试连接，不希望连接失败后回退到自动启动浏览器：

```powershell
$env:CHATGPT_CONNECT_MODE="cdp"
```

默认是：

```powershell
$env:CHATGPT_CONNECT_MODE="cdp-first"
```

## 打开前端

直接用浏览器打开：

```text
C:\Users\dell\Desktop\ai_web_project\frontend\index.html
```

## 启动 LoRA 前设置基础模型

把 `BASE_MODEL` 设置为本地模型路径或 Hugging Face 模型名：

```powershell
$env:BASE_MODEL="C:\models\your-base-model"
```

需要安装训练依赖：

```powershell
.\.venv\Scripts\python -m pip install -r requirements-train.txt
```

## 生成文件

- `uploads/source.txt`
- `work/prompt.txt`
- `datasets/train.jsonl`
- `datasets/preview.json`
- `models/lora`
- `playwright-profile`
