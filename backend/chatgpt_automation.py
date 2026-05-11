import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "work" / "prompt.txt"
SOURCE_PATH = ROOT / "uploads" / "source.txt"
WORK = ROOT / "work"
DATASETS = ROOT / "datasets"
PROFILE = ROOT / "playwright-profile"
TRAIN_FILENAME = os.environ.get("TRAIN_FILENAME", "train.jsonl")
TRAIN_PATH = Path(os.environ.get("TRAIN_PATH", str(DATASETS / TRAIN_FILENAME)))
CDP_URL = os.environ.get("CHATGPT_CDP_URL", "http://127.0.0.1:9222")
BROWSER_CHANNELS = {
    "edge": "msedge",
    "msedge": "msedge",
    "microsoft-edge": "msedge",
    "chrome": "chrome",
    "google-chrome": "chrome",
    "chromium": None,
    "playwright": None,
}


def extract_jsonl(text):
    fenced = re.findall(r"```(?:jsonl|json|text)?\s*([\s\S]*?)```", text, flags=re.I)
    candidates = fenced or [text]
    for candidate in candidates:
        lines = []
        for line in candidate.splitlines():
            raw = line.strip()
            if not raw or not raw.startswith("{"):
                continue
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                continue
            lines.append(raw)
        if lines:
            return "\n".join(lines) + "\n"
    raise RuntimeError("没有从 ChatGPT 响应中找到合法 JSONL")


def find_prompt_box(page, timeout_seconds=900):
    selectors = ["textarea", "div[contenteditable='true']", "[data-testid='prompt-textarea']"]
    deadline = time.time() + timeout_seconds
    last_url = ""

    while time.time() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector).last
                locator.wait_for(timeout=2000)
                return locator
            except PlaywrightTimeoutError:
                continue

        current_url = page.url
        if current_url != last_url:
            print(f"等待 ChatGPT 输入框出现。当前页面: {current_url}", flush=True)
            last_url = current_url
        time.sleep(2)

    raise RuntimeError("等待 ChatGPT 输入框超时。请确认已经完成登录和真人验证，并且页面停留在 ChatGPT 聊天页。")


def fill_prompt(page, prompt):
    box = find_prompt_box(page)
    try:
        box.fill(prompt, timeout=5000)
    except Exception:
        box.click()
        page.keyboard.insert_text(prompt)


def append_debug_log(message):
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / "chatgpt_attach_debug.txt").open("a", encoding="utf-8") as file:
        file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def attachment_is_visible(page):
    filename = SOURCE_PATH.name
    original_name = ""
    name_path = ROOT / "uploads" / "source_filename.txt"
    if name_path.exists():
        original_name = name_path.read_text(encoding="utf-8").strip()

    # Only treat real file names as proof. Generic words like "上传" can be
    # present on the menu/button even when no attachment was added.
    patterns = [filename, original_name]
    for pattern in [item for item in patterns if item]:
        try:
            if page.locator(f"text={pattern}").count() > 0:
                append_debug_log(f"附件已在页面出现: {pattern}")
                return True
        except Exception:
            continue
    return False


def wait_for_attachment(page, timeout_seconds=20):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if attachment_is_visible(page):
            return True
        time.sleep(1)
    return False


def attach_uploaded_txt(page):
    source_file = str(SOURCE_PATH)
    if not SOURCE_PATH.exists():
        raise RuntimeError(f"附件文件不存在: {source_file}")

    append_debug_log(f"开始上传附件: {source_file}")

    attach_selectors = [
        "[data-testid='composer-plus-btn']",
        "[data-testid='composer-attach-button']",
        "[data-testid='paperclip-button']",
        "button[aria-label*='Attach']",
        "button[aria-label*='attach']",
        "button[aria-label*='Upload']",
        "button[aria-label*='upload']",
        "button[aria-label*='Add']",
        "button[aria-label*='添加']",
        "button[aria-label*='上传']",
        "button[aria-label*='附件']",
        "button[aria-label*='文件']",
        "button:has-text('+')",
    ]
    menu_selectors = [
        "button:has-text('添加照片和文件')",
        "[role='menuitem']:has-text('添加照片和文件')",
        "[role='button']:has-text('添加照片和文件')",
        "div[role='menuitem']:has-text('添加照片和文件')",
        "text=添加照片和文件",
        "button:has-text('Add photos and files')",
        "[role='menuitem']:has-text('Add photos and files')",
        "[role='button']:has-text('Add photos and files')",
        "div[role='menuitem']:has-text('Add photos and files')",
        "text=Add photos and files",
        "text=Upload from computer",
        "text=Upload file",
        "text=Upload files",
        "text=Add files",
        "text=Attach files",
        "text=上传文件",
        "text=从电脑上传",
        "text=添加文件",
        "text=附件",
    ]
    for attach_selector in attach_selectors:
        attach_button = page.locator(attach_selector).last
        if attach_button.count() == 0:
            continue
        try:
            append_debug_log(f"尝试打开附件菜单，selector: {attach_selector}")
            attach_button.click(timeout=3000)
            time.sleep(1.5)
        except Exception:
            continue
        for menu_selector in menu_selectors:
            menu_item = page.locator(menu_selector).last
            if menu_item.count() == 0:
                continue
            try:
                append_debug_log(f"尝试通过菜单项上传，menu_selector: {menu_selector}")
                menu_item.wait_for(state="visible", timeout=3000)
                with page.expect_file_chooser(timeout=4000) as chooser_info:
                    menu_item.click()
                chooser_info.value.set_files(source_file)
                if wait_for_attachment(page):
                    return
                append_debug_log(f"菜单项设置后未看到附件，menu_selector: {menu_selector}")
            except Exception as exc:
                append_debug_log(f"菜单项上传失败，menu_selector: {menu_selector}，错误: {exc}")
                continue

    for selector in attach_selectors:
        locator = page.locator(selector).last
        if locator.count() == 0:
            append_debug_log(f"未找到附件按钮 selector: {selector}")
            continue
        try:
            append_debug_log(f"尝试通过文件选择器上传，selector: {selector}")
            with page.expect_file_chooser(timeout=4000) as chooser_info:
                locator.click()
            chooser_info.value.set_files(source_file)
            if wait_for_attachment(page):
                return
            append_debug_log(f"文件选择器设置后未看到附件，selector: {selector}")
        except Exception as exc:
            append_debug_log(f"文件选择器方式失败，selector: {selector}，错误: {exc}")
            pass

    inputs = page.locator("input[type='file']")
    append_debug_log(f"页面 input[type=file] 数量: {inputs.count()}")
    for index in range(inputs.count()):
        try:
            inputs.nth(index).set_input_files(source_file, timeout=3000)
            append_debug_log(f"已尝试直接设置第 {index} 个 file input")
            if wait_for_attachment(page):
                return
            append_debug_log(f"第 {index} 个 file input 设置后未看到文件名，继续尝试")
        except Exception as exc:
            append_debug_log(f"第 {index} 个 file input 设置失败: {exc}")
            continue

    try:
        (WORK / "chatgpt_attach_page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(WORK / "chatgpt_attach_page.png"), full_page=True)
    except Exception:
        pass
    raise RuntimeError("没有找到 ChatGPT 的添加文件入口，无法上传 txt 附件")


def send_current_prompt(page):
    selectors = [
        "button[data-testid='send-button']",
        "button[aria-label*='Send']",
        "button[aria-label*='send']",
        "button[aria-label*='发送']",
        "button[aria-label*='提交']",
        "button:has-text('Send')",
        "button:has-text('发送')",
        "[role='button'][aria-label*='Send']",
        "[role='button'][aria-label*='发送']",
    ]
    deadline = time.time() + 30
    last_error = None
    while time.time() < deadline:
        for selector in selectors:
            button = page.locator(selector).last
            if button.count() > 0:
                try:
                    button.click(timeout=3000)
                    append_debug_log(f"已点击发送按钮: {selector}")
                    return
                except Exception as exc:
                    last_error = exc
        time.sleep(1)

    append_debug_log(f"未能点击发送按钮，尝试聚焦输入框后按 Enter。最后错误: {last_error}")
    try:
        find_prompt_box(page, timeout_seconds=5).click(timeout=3000)
    except Exception as exc:
        append_debug_log(f"回退发送时聚焦输入框失败: {exc}")
    page.keyboard.press("Enter")

def wait_for_answer(page):
    time.sleep(8)
    stable_rounds = 0
    previous = ""
    deadline = time.time() + 600
    while time.time() < deadline:
        body = page.locator("body").inner_text(timeout=5000)
        if body == previous:
            stable_rounds += 1
        else:
            stable_rounds = 0
            previous = body
        if stable_rounds >= 6:
            return body
        time.sleep(2)
    raise RuntimeError("等待 ChatGPT 生成结果超时")


def save_debug_response(page, text):
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "chatgpt_response.txt").write_text(text, encoding="utf-8")
    try:
        (WORK / "chatgpt_page.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def click_and_expect_download(page, locator, timeout=10000):
    try:
        with page.expect_download(timeout=timeout) as download_info:
            locator.click(timeout=4000)
        download = download_info.value
        download.save_as(str(TRAIN_PATH))
        return True
    except Exception:
        return False


def click_matching_targets(page, patterns):
    targets = page.locator("a, button, [role='button'], [data-testid], [aria-label]")
    count = min(targets.count(), 250)
    for index in range(count - 1, -1, -1):
        locator = targets.nth(index)
        try:
            text = " ".join(
                value for value in [
                    locator.inner_text(timeout=500),
                    locator.get_attribute("aria-label", timeout=500),
                    locator.get_attribute("title", timeout=500),
                    locator.get_attribute("download", timeout=500),
                ] if value
            ).lower()
        except Exception:
            continue
        if any(pattern in text for pattern in patterns):
            if click_and_expect_download(page, locator):
                return True
            try:
                locator.click(timeout=3000)
                time.sleep(2)
            except Exception:
                continue
    return False


def try_download_once(page):
    DATASETS.mkdir(parents=True, exist_ok=True)
    selectors = [
        "a[download]",
        f"a:has-text('{TRAIN_FILENAME}')",
        "a:has-text('train.jsonl')",
        "a:has-text('source.jsonl')",
        "a:has-text('.jsonl')",
        f"button:has-text('{TRAIN_FILENAME}')",
        "button:has-text('train.jsonl')",
        "button:has-text('source.jsonl')",
        "button:has-text('.jsonl')",
        f"[role='button']:has-text('{TRAIN_FILENAME}')",
        "[role='button']:has-text('train.jsonl')",
        "[role='button']:has-text('source.jsonl')",
        "[role='button']:has-text('.jsonl')",
        f"[data-testid]:has-text('{TRAIN_FILENAME}')",
        "[data-testid]:has-text('train.jsonl')",
        "[data-testid]:has-text('source.jsonl')",
        "[data-testid]:has-text('.jsonl')",
        "a:has-text('Download')",
        "button:has-text('Download')",
        "[role='button']:has-text('Download')",
        "a:has-text('下载')",
        "button:has-text('下载')",
        "[role='button']:has-text('下载')",
    ]
    for selector in selectors:
        locator = page.locator(selector).last
        if locator.count() == 0:
            continue
        if click_and_expect_download(page, locator):
            return True

    if click_matching_targets(page, [".jsonl", "train.jsonl", "source.jsonl", "download", "下载"]):
        return True

    for file_name in ("train.jsonl", "source.jsonl", ".jsonl"):
        file_text = page.locator(f"text={file_name}").last
        if file_text.count() > 0:
            try:
                file_text.click(timeout=3000)
                time.sleep(2)
                if click_matching_targets(page, ["download", "下载", "save", "保存", ".jsonl"]):
                    return True
            except Exception:
                pass
    return False


def wait_for_download(page, timeout_seconds=90):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if try_download_once(page):
            return True
        time.sleep(2)
    return False


def browser_channel():
    requested = os.environ.get("CHATGPT_BROWSER_REQUESTED") or os.environ.get("CHATGPT_BROWSER", "msedge")
    requested = requested.strip().lower()
    if requested not in BROWSER_CHANNELS:
        choices = ", ".join(sorted(BROWSER_CHANNELS))
        raise RuntimeError(f"CHATGPT_BROWSER 不支持 {requested!r}，可选值: {choices}")
    return requested, BROWSER_CHANNELS[requested]


def open_browser(playwright, requested_browser, channel):
    mode = os.environ.get("CHATGPT_CONNECT_MODE", "cdp-first").strip().lower()
    if mode not in {"cdp-first", "cdp", "launch"}:
        raise RuntimeError("CHATGPT_CONNECT_MODE 只支持 cdp-first、cdp、launch")

    if mode in {"cdp-first", "cdp"}:
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            print(f"已连接远程调试浏览器: {CDP_URL}", flush=True)
            return browser, context, "cdp"
        except Exception as exc:
            if mode == "cdp":
                raise RuntimeError(f"连接远程调试浏览器失败: {CDP_URL}。请先用调试端口启动 Edge/Chrome。") from exc
            print(f"没有发现远程调试浏览器，回退到自动启动 {requested_browser}: {exc}", flush=True)

    launch_options = {
        "user_data_dir": str(PROFILE),
        "headless": False,
        "accept_downloads": True,
    }
    if channel:
        launch_options["channel"] = channel
    context = playwright.chromium.launch_persistent_context(**launch_options)
    return None, context, "launch"


def main():
    if not PROMPT_PATH.exists():
        raise RuntimeError("缺少 work/prompt.txt")
    if not SOURCE_PATH.exists():
        raise RuntimeError("缺少 uploads/source.txt，请先上传 txt 文件")
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    DATASETS.mkdir(parents=True, exist_ok=True)
    PROFILE.mkdir(parents=True, exist_ok=True)
    requested_browser, channel = browser_channel()

    with sync_playwright() as playwright:
        browser, context, mode = open_browser(playwright, requested_browser, channel)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        print(f"已使用 {requested_browser}，连接模式: {mode}。请手动登录 ChatGPT 并完成人机验证；脚本会一直等待聊天输入框出现。", flush=True)
        find_prompt_box(page, timeout_seconds=900)
        fill_prompt(page, prompt)
        attach_uploaded_txt(page)
        send_current_prompt(page)
        answer_text = wait_for_answer(page)

        if wait_for_download(page):
            print(f"已通过下载链接保存 {TRAIN_PATH}")
        else:
            save_debug_response(page, answer_text)
            jsonl = extract_jsonl(answer_text)
            TRAIN_PATH.write_text(jsonl, encoding="utf-8")
            print(f"没有发现可点击下载链接，已从响应文本提取并保存 {TRAIN_PATH}")
        if mode == "launch":
            context.close()


if __name__ == "__main__":
    main()
