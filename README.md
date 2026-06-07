# 深大公文通自动同步工具

这个目录用于在一台能访问深大公文通的电脑上定期运行爬虫，并把新抓到的公文通 Excel 上传到 Lychee Memoir 后端导入知识库。

如果这是交给其他部门同事维护，请先阅读完整交接文档：

```text
backend_ingestion_guide.md
```

那份文档会解释 Lychee Memoir 为什么需要公文通数据、Excel 每个字段的用途、后端如何入库、双方职责边界和验收标准。本 README 只保留运行命令和排错入口。

## 1. 工作方式

```text
本机 Chrome 登录公文通
  |
  v
szu_board_cdp_scraper.py 抓取最近 2 天
  |
  v
生成 xlsx
  |
  v
POST /api/admin/knowledge/ingest/szu-board-excel-upload
  |
  v
后端幂等导入 knowledge_document / knowledge_chunk
```

注意：

- 不绕过深大统一认证。
- 不把统一认证 Cookie 上传服务器。
- 默认每天运行一次。
- 默认抓最近 2 天，后端按 URL 幂等去重。

## 2. 准备 Python 环境

```bash
cd tools/szu-board-crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
cd tools\szu-board-crawler
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. 准备配置

复制配置模板：

```bash
cp config.example.yaml config.yaml
```

填写：

```yaml
api_base_url: "https://lychee-memoir.cn"
ingest_token: "后端 SZU_BOARD_INGEST_TOKEN"
chrome_debugger_address: "127.0.0.1:9222"
chrome_user_data_dir: "~/.szu-board-chrome"
crawler_script: "/Users/ice/IdeaProjects/资料/szu_board_cdp_scraper.py"
crawl_overlap_days: 2
```

`config.yaml` 可以填写 `username/password`，但 v1 默认复用 Chrome 登录态；如果统一认证需要验证码、短信或页面结构变化，仍需要人工登录。

不要提交 `config.yaml`。

## 4. 首次登录

运行一次同步脚本，它会尝试启动专用 Chrome profile：

```bash
./run_once_macos.sh
```

Windows：

```powershell
.\run_once_windows.ps1
```

如果 Chrome 跳到统一身份认证页面，请在这个 Chrome 窗口里手动登录。登录后重新执行脚本。

## 5. macOS 定时运行

复制 plist 模板：

```bash
cp lychee.szu-board-crawler.plist.example ~/Library/LaunchAgents/lychee.szu-board-crawler.plist
```

编辑其中的绝对路径：

```text
/absolute/path/to/tools/szu-board-crawler/run_once_macos.sh
/absolute/path/to/tools/szu-board-crawler/config.yaml
```

加载任务：

```bash
launchctl load ~/Library/LaunchAgents/lychee.szu-board-crawler.plist
```

手动触发：

```bash
launchctl start lychee.szu-board-crawler
```

卸载：

```bash
launchctl unload ~/Library/LaunchAgents/lychee.szu-board-crawler.plist
```

## 6. Windows 定时运行

打开“任务计划程序”：

1. 创建基本任务。
2. 触发器选择“每天”，建议时间 06:30。
3. 操作选择“启动程序”。
4. 程序填写：

```text
powershell.exe
```

参数填写：

```text
-ExecutionPolicy Bypass -File "C:\absolute\path\tools\szu-board-crawler\run_once_windows.ps1" -ConfigPath "C:\absolute\path\tools\szu-board-crawler\config.yaml"
```

建议勾选：

- 只有在用户登录时运行。
- 如果任务失败，间隔 30 分钟重试一次，最多重试 2 次。

## 7. 日志和状态

默认目录：

```text
~/lychee-szu-board-crawler/logs/szu-board-sync.log
~/lychee-szu-board-crawler/data/state.json
~/lychee-szu-board-crawler/data/szu_board_incremental_YYYYMMDD.xlsx
```

常见失败：

- `Chrome 已尝试启动，但远程调试端口仍不可用`：检查 Chrome 路径或端口占用。
- `当前页面仍是统一身份认证`：打开专用 Chrome 手动登录。
- `后端导入失败 status=401`：检查 `ingest_token` 是否和后端一致。
- `爬虫脚本不存在`：检查 `crawler_script` 路径。

## 8. 后端要求

后端需要配置：

```bash
SZU_BOARD_INGEST_TOKEN=一个足够长的随机字符串
SZU_BOARD_EXCEL_UPLOAD_MAX_SIZE_BYTES=52428800
```

上传接口：

```http
POST /api/admin/knowledge/ingest/szu-board-excel-upload
X-Ingestion-Token: <token>
Content-Type: multipart/form-data
```

字段：

```text
file=@szu_board_incremental_YYYYMMDD.xlsx
```

上传的 Excel 第一行字段建议固定为：

```text
date, department, category, title, url, content, attachments, fetched_at
```

最低可用要求是 `title`、`url`、`content` 非空；为了 Echo 搜索准确，建议完整提供全部字段。`url` 是后端幂等键，同一 URL 重复上传会更新，不会重复插入。

## 9. 安全注意

- `config.yaml` 不提交 git。
- 不在日志里打印账号、密码或 token。
- Chrome 远程调试地址只绑定 `127.0.0.1`。
- token 只允许调用公文通 Excel 上传接口，不给其他后台权限。
- 后端按 URL 幂等导入，重复上传是安全的。
