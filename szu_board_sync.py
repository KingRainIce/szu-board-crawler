#!/usr/bin/env python3
"""Run SZU board crawler and upload the generated Excel to Lychee Memoir API."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4


DEFAULTS = {
    "api_base_url": "https://lychee-memoir.cn",
    "ingest_token": "",
    "chrome_debugger_address": "127.0.0.1:9222",
    "chrome_user_data_dir": "~/.szu-board-chrome",
    "chrome_path": "",
    "crawler_script": "/Users/ice/IdeaProjects/资料/szu_board_cdp_scraper.py",
    "crawl_overlap_days": "2",
    "detail_batch_size": "25",
    "checkpoint_every": "10",
    "delay_min": "0.5",
    "delay_max": "1.0",
    "output_dir": "~/lychee-szu-board-crawler/data",
    "log_dir": "~/lychee-szu-board-crawler/logs",
    "username": "",
    "password": "",
}


def main() -> int:
    args = parse_args()
    config = {**DEFAULTS, **load_config(Path(args.config))}
    output_dir = expand_path(config["output_dir"])
    log_dir = expand_path(config["log_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "szu-board-sync.log"

    def write(message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    try:
        ensure_chrome(config, write)
        start_date, end_date = crawl_window(int(config["crawl_overlap_days"]))
        output = output_dir / f"szu_board_incremental_{end_date.isoformat().replace('-', '')}.xlsx"
        run_crawler(config, output, start_date, end_date, write)
        response = upload_excel(config, output, write)
        save_state(output_dir / "state.json", output, response)
        write(f"[完成] uploaded={output} job={response.get('id')} status={response.get('status')}")
        return 0
    except Exception as exc:
        write(f"[失败] {type(exc).__name__}: {exc}")
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync SZU board notices to Lychee Memoir.")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"配置文件不存在：{path}。请复制 config.example.yaml 为 config.yaml 后填写。")
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        result[key.strip()] = value
    return result


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def debugger_json(address: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{address}/json/version", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def ensure_chrome(config: dict[str, str], log) -> None:
    address = config["chrome_debugger_address"]
    if debugger_json(address):
        log(f"[Chrome] connected {address}")
        return

    chrome_path = config["chrome_path"].strip() or detect_chrome_path()
    if not chrome_path:
        raise RuntimeError("未找到 Chrome。请在 config.yaml 配置 chrome_path。")
    user_data_dir = expand_path(config["chrome_user_data_dir"])
    user_data_dir.mkdir(parents=True, exist_ok=True)
    host, port = parse_debugger_address(address)
    command = [
        chrome_path,
        f"--remote-debugging-address={host}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        "https://www1.szu.edu.cn/board/infolist.asp",
    ]
    log(f"[Chrome] starting dedicated profile at {user_data_dir}")
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        time.sleep(1)
        if debugger_json(address):
            log(f"[Chrome] started {address}")
            return
    raise RuntimeError("Chrome 已尝试启动，但远程调试端口仍不可用。")


def detect_chrome_path() -> str:
    system = platform.system().lower()
    candidates: list[str]
    if system == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif system == "windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        candidates = ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def parse_debugger_address(address: str) -> tuple[str, str]:
    if ":" not in address:
        return "127.0.0.1", address
    host, port = address.rsplit(":", 1)
    return host or "127.0.0.1", port


def crawl_window(overlap_days: int) -> tuple[date, date]:
    days = max(1, overlap_days)
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def run_crawler(config: dict[str, str], output: Path, start: date, end: date, log) -> None:
    script = expand_path(config["crawler_script"])
    if not script.exists():
        raise RuntimeError(f"爬虫脚本不存在：{script}")
    years = ",".join(str(year) for year in range(start.year, end.year + 1))
    command = [
        sys.executable,
        str(script),
        "--debugger-address", config["chrome_debugger_address"],
        "--output", str(output),
        "--start-date", start.isoformat(),
        "--end-date", end.isoformat(),
        "--years", years,
        "--detail-batch-size", config["detail_batch_size"],
        "--checkpoint-every", config["checkpoint_every"],
        "--delay-min", config["delay_min"],
        "--delay-max", config["delay_max"],
    ]
    log(f"[抓取] {start}..{end} output={output}")
    process = subprocess.run(command, text=True, capture_output=True)
    append_subprocess_log(log, process.stdout)
    append_subprocess_log(log, process.stderr)
    if process.returncode != 0:
        message = "公文通爬虫失败。请确认 Chrome 已登录校园公文通；如跳到统一身份认证，请人工登录后重试。"
        raise RuntimeError(message)
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("爬虫没有生成有效 Excel 文件。")


def append_subprocess_log(log, text: str) -> None:
    for line in (text or "").splitlines():
        if line.strip():
            log(f"[crawler] {line}")


def upload_excel(config: dict[str, str], output: Path, log) -> dict:
    token = config["ingest_token"].strip()
    if not token:
        raise RuntimeError("ingest_token 未配置。")
    base = config["api_base_url"].rstrip("/")
    url = base + "/api/admin/knowledge/ingest/szu-board-excel-upload"
    fields = {
        "request_id": str(uuid4()),
        "backfill_metadata": "true",
        "backfill_embeddings": "false",
    }
    files = {"file": output}
    body, content_type = multipart_body(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "X-Ingestion-Token": token,
        },
    )
    log(f"[上传] {url} file={output.name} size={output.stat().st_size}")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"后端导入失败 status={ex.code} body={detail[:500]}") from ex


def multipart_body(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = "----lychee-szu-board-" + uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    for name, path in files.items():
        filename = path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def save_state(path: Path, output: Path, response: dict) -> None:
    state = {
        "last_success_at": datetime.now().isoformat(timespec="seconds"),
        "last_output": str(output),
        "last_job": response,
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
