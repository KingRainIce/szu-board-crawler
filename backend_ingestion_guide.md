# 深大公文通数据采集与入库交接说明

本文档面向负责“深圳大学校园公文通”采集的同事，也给 Lychee Memoir 后端同事做接口对齐使用。阅读本文不需要提前了解 Lychee Memoir 项目。

## 1. 这件事要解决什么问题

Lychee Memoir 网站里有一个叫 Echo 的校园问答助手。用户会问：

- “深大最近有什么讲座？”
- “某个奖学金通知什么时候截止？”
- “某个学院的答辩公告在哪里看？”
- “校内某项活动是谁发布的？”

Echo 不能凭空回答，它需要一个可信的校内知识库。深大公文通是官方通知来源之一，所以我们需要定期把公文通的新文章抓取下来，上传给后端，后端再导入到知识库表中，用于搜索和 AI 回答。

这条链路分成两部分：

| 环节 | 负责人 | 产物 |
| --- | --- | --- |
| 公文通采集 | 运行爬虫的同事 | `.xlsx` 文件，包含最近公文通文章 |
| 后端入库 | Lychee Memoir 后端 | 写入 `knowledge_document` / `knowledge_chunk`，用于 Echo 检索 |

采集同事只需要保证 Excel 格式正确，并通过上传接口提交即可，不需要直接操作数据库。

## 2. 总体流程

```text
一台能访问深大公文通的电脑
  |
  | 1. 启动专用 Chrome
  | 2. 人工登录深大统一身份认证
  | 3. 脚本复用 Chrome 登录态抓取最近 2 天文章
  v
生成 szu_board_incremental_YYYYMMDD.xlsx
  |
  | 4. 脚本调用后端上传接口
  v
Lychee Memoir 后端
  |
  | 5. 校验 Excel、解析正文、脱敏、分类、切 chunk
  | 6. 按 URL 幂等写入知识库
  v
Echo 校园问答可搜索到新公文
```

默认只抓最近 2 天。原因是这个任务会每天跑，后端按 URL 幂等去重，重复抓取最近 2 天可以覆盖昨天失败、临时更新或漏抓的情况，同时不会带来大量重复数据。

## 3. 为什么需要登录态，能不能绕过登录

目前方案不绕过深大统一身份认证。

公文通部分内容依赖校内访问或统一认证登录，脚本采用“复用本机 Chrome 登录态”的方式：

1. 脚本启动一个专门的 Chrome 用户目录。
2. 第一次运行时，如果跳到统一身份认证页面，由负责人手动登录。
3. 登录成功后，Chrome 会保存登录态。
4. 后续定时任务复用这个 Chrome profile 抓取数据。

不建议把账号、密码、Cookie 写进代码或上传服务器。`config.yaml` 中预留了 `username/password` 字段，只是为了本机人工维护信息，不要求脚本自动绕过登录，也不要提交到 git。

如果登录态失效，脚本会失败并在日志提示重新人工登录。

## 4. 运行机器要求

这台机器可以是 macOS 或 Windows，但必须满足：

- 能打开深大公文通页面。
- 能安装 Python 3.10+。
- 能安装 Google Chrome。
- 能访问 Lychee Memoir 后端接口，例如 `https://lychee-memoir.cn`。
- 机器最好长期在线，适合每天自动运行。

建议：

- 如果是 macOS，用 `launchd` 定时运行。
- 如果是 Windows，用“任务计划程序”定时运行。
- 不建议在普通临时笔记本上跑，容易因为休眠、关机、Chrome 登录态丢失导致中断。

## 5. 爬虫工具目录

Lychee Memoir 项目内已经提供自动同步工具：

```text
tools/szu-board-crawler/
  README.md
  config.example.yaml
  requirements.txt
  szu_board_sync.py
  run_once_macos.sh
  run_once_windows.ps1
  lychee.szu-board-crawler.plist.example
```

其中：

| 文件 | 作用 |
| --- | --- |
| `szu_board_sync.py` | 总控脚本：启动 Chrome、调用实际爬虫、上传 Excel 到后端。 |
| `config.example.yaml` | 配置模板。复制成 `config.yaml` 后填写。 |
| `run_once_macos.sh` | macOS 手动运行入口。 |
| `run_once_windows.ps1` | Windows 手动运行入口。 |
| `requirements.txt` | Python 依赖。 |
| `README.md` | 项目内简版说明。 |

注意：`szu_board_sync.py` 会调用实际采集脚本 `szu_board_cdp_scraper.py`。这个脚本路径在 `config.yaml` 的 `crawler_script` 字段里配置。

## 6. 首次部署步骤

### 6.1 准备 Python 环境

macOS：

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

### 6.2 创建配置文件

复制模板：

```bash
cp config.example.yaml config.yaml
```

Windows：

```powershell
Copy-Item config.example.yaml config.yaml
```

`config.yaml` 不要提交到 git，不要发到群里。里面会放上传令牌，也可能放账号备注。

推荐配置示例：

```yaml
api_base_url: "https://lychee-memoir.cn"
ingest_token: "由 Lychee Memoir 后端提供的 SZU_BOARD_INGEST_TOKEN"

chrome_debugger_address: "127.0.0.1:9222"
chrome_user_data_dir: "~/.szu-board-chrome"
chrome_path: ""

crawler_script: "/absolute/path/to/szu_board_cdp_scraper.py"
crawl_overlap_days: 2
detail_batch_size: 25
checkpoint_every: 10
delay_min: 0.5
delay_max: 1.0

output_dir: "~/lychee-szu-board-crawler/data"
log_dir: "~/lychee-szu-board-crawler/logs"

username: ""
password: ""
```

关键字段解释：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `api_base_url` | 是 | Lychee Memoir 后端地址。线上填 `https://lychee-memoir.cn`。 |
| `ingest_token` | 是 | 后端上传接口令牌，只用于公文通 Excel 上传。 |
| `chrome_debugger_address` | 是 | Chrome DevTools 地址，默认 `127.0.0.1:9222`。不要暴露到公网。 |
| `chrome_user_data_dir` | 是 | 专用 Chrome 用户目录，用来保存公文通登录态。 |
| `chrome_path` | 否 | Chrome 可执行文件路径。留空时脚本会自动尝试识别。 |
| `crawler_script` | 是 | 实际公文通抓取脚本 `szu_board_cdp_scraper.py` 的绝对路径。 |
| `crawl_overlap_days` | 是 | 抓取最近几天，默认 2。 |
| `detail_batch_size` | 是 | 详情页抓取批量大小。网络不稳定时调小。 |
| `checkpoint_every` | 是 | 每抓多少条保存一次中间结果。 |
| `delay_min/delay_max` | 是 | 每次请求之间的随机等待秒数。 |
| `output_dir` | 是 | 生成 Excel 和状态文件的目录。 |
| `log_dir` | 是 | 日志目录。 |
| `username/password` | 否 | 仅供本机负责人记录，不建议脚本自动使用，也不要提交。 |

## 7. 首次登录和手动试跑

macOS：

```bash
./run_once_macos.sh
```

Windows：

```powershell
.\run_once_windows.ps1
```

第一次运行通常会打开一个新的 Chrome 窗口。如果页面跳到统一身份认证，请在这个 Chrome 窗口里手动登录。

登录成功后，重新运行一次脚本。成功时会看到类似：

```text
[Chrome] connected 127.0.0.1:9222
[抓取] 2026-06-06..2026-06-07 output=...
[上传] https://lychee-memoir.cn/api/admin/knowledge/ingest/szu-board-excel-upload file=szu_board_incremental_20260607.xlsx
[完成] uploaded=... status=SUCCEEDED
```

如果手动试跑失败，不要直接上定时任务，先看日志排错。

## 8. 生成的 Excel 必须是什么格式

后端上传接口只接受 `.xlsx`。

Excel 第一行必须是字段名。推荐完整字段如下：

```text
date, department, category, title, url, content, attachments, fetched_at
```

后端最低要求：

- `title` 非空
- `url` 非空
- `content` 非空

但为了搜索准确性，强烈建议完整提供所有字段。

### 8.1 字段说明

| 字段 | 必填 | 示例 | 后端用途 |
| --- | --- | --- | --- |
| `date` | 推荐 | `2026-06-07` | 作为文章发布时间。如果正文里能解析到更精确时间，后端会优先使用正文时间。 |
| `department` | 推荐 | `学生部` | 用于来源部门、排序和搜索过滤。 |
| `category` | 推荐 | `学生事务` | 用于辅助判断知识分类。 |
| `title` | 是 | `关于开展深圳大学学生社团年审工作的通知` | 作为知识标题，也是搜索最重要字段之一。 |
| `url` | 是 | `https://www1.szu.edu.cn/board/view.asp?id=568149` | 作为幂等唯一来源。重复上传同一 URL 会更新，不会重复插入。 |
| `content` | 是 | 详情页可见正文文本 | 用于正文清洗、切片、向量检索和 Echo 回答。 |
| `attachments` | 推荐 | `https://.../a.docx; https://.../b.xlsx` | 附件链接，多个用英文分号 `;` 分隔。 |
| `fetched_at` | 推荐 | `2026-06-07T08:30:00` | 抓取时间，用于排查和追踪。 |

### 8.2 字段格式细节

`date`：

- 推荐格式：`YYYY-MM-DD`
- 也兼容 Excel 日期数字，但不建议依赖这个。

`url`：

- 必须是详情页 URL。
- 推荐保留原始公文通 URL。
- 如果 URL 包含 `id=568149`，后端会解析出 `sourcePath=szu-board/568149`。

`content`：

- 放详情页主要可见文本。
- 可以包含页面导航、标题、发文单位、发布时间，后端会做基础清洗。
- 不要只放摘要。Echo 需要完整正文来回答细节。
- 如果正文有名单、学号、手机号等敏感信息，后端会做脱敏，但采集侧也应尽量避免额外抓取无关个人信息。

`attachments`：

- 多个链接用 `;` 分隔，例如：

```text
https://www1.szu.edu.cn/board/upload/a.docx; https://www1.szu.edu.cn/board/upload/b.xlsx
```

- 当前后端只把附件链接追加到正文中，方便 Echo 提醒用户“有附件”；暂不下载附件正文。

`fetched_at`：

- 推荐 ISO 时间，例如 `2026-06-07T08:30:00`。
- 主要用于排查，不参与幂等判断。

### 8.3 Excel 样例

| date | department | category | title | url | content | attachments | fetched_at |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-07 | 学生部 | 学生事务 | 关于开展学生社团年审工作的通知 | https://www1.szu.edu.cn/board/view.asp?id=568149 | 关于开展学生社团年审工作的通知\n学生部 2026/6/7 10:00:00\n各学院、各社团：... | https://.../附件1.docx | 2026-06-07T10:30:00 |

## 9. 后端如何处理这份 Excel

上传后，后端做这些事情：

1. 校验请求令牌 `X-Ingestion-Token`。
2. 校验文件必须是 `.xlsx`，大小不能超过配置值。
3. 读取第一张 sheet。
4. 按字段名读取每一行。
5. 跳过 `title/content` 为空的行。
6. 清洗正文里的导航、空行、登录用户名等无关文本。
7. 对疑似学号、姓名、手机号等敏感内容做脱敏。
8. 根据标题、分类、部门、正文推断知识分类，例如：
   - `OFFICIAL_NOTICE`
   - `CAMPUS_LIFE`
   - `POLICY_RULE`
   - `PROGRAM_INFO`
9. 以 `url` / `sourcePath` 做幂等写入。
10. 切分成知识片段，写入 `knowledge_chunk`。
11. 如果后端配置了 metadata backfill，会补充搜索关键词、摘要等字段。

这意味着：同一个 Excel 可以重复上传。只要 URL 一样，后端会更新已有记录，不会制造重复知识。

## 10. 上传接口

接口：

```http
POST /api/admin/knowledge/ingest/szu-board-excel-upload
X-Ingestion-Token: <后端提供的上传令牌>
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | `.xlsx` 文件。 |
| `request_id` | 否 | 请求幂等/排查 ID，可用 UUID。 |
| `backfill_metadata` | 否 | 默认 `true`，导入后补搜索元数据。 |
| `backfill_embeddings` | 否 | 默认 `false`，是否立刻补向量。一般不建议采集脚本打开。 |

curl 示例：

```bash
curl -X POST "https://lychee-memoir.cn/api/admin/knowledge/ingest/szu-board-excel-upload" \
  -H "X-Ingestion-Token: $SZU_BOARD_INGEST_TOKEN" \
  -F "request_id=$(uuidgen)" \
  -F "backfill_metadata=true" \
  -F "backfill_embeddings=false" \
  -F "file=@szu_board_incremental_20260607.xlsx"
```

成功响应类似：

```json
{
  "id": 123,
  "job_type": "SZU_BOARD_EXCEL",
  "status": "SUCCEEDED",
  "total_count": 18,
  "success_count": 18,
  "failed_count": 0,
  "error_message": null
}
```

如果 `failed_count > 0`，说明某些行入库失败。采集同事需要把 Excel 和日志发给后端排查。

## 11. 定时运行

### 11.1 macOS 使用 launchd

复制模板：

```bash
cp tools/szu-board-crawler/lychee.szu-board-crawler.plist.example \
  ~/Library/LaunchAgents/lychee.szu-board-crawler.plist
```

编辑 plist，把脚本和配置文件路径改成绝对路径。

加载：

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

### 11.2 Windows 使用任务计划程序

创建任务：

1. 打开“任务计划程序”。
2. 创建基本任务。
3. 触发器选择“每天”，建议早上 06:30。
4. 操作选择“启动程序”。
5. 程序填写：

```text
powershell.exe
```

参数填写：

```text
-ExecutionPolicy Bypass -File "C:\absolute\path\tools\szu-board-crawler\run_once_windows.ps1" -ConfigPath "C:\absolute\path\tools\szu-board-crawler\config.yaml"
```

建议设置：

- 只有在用户登录时运行。
- 失败后 30 分钟重试，最多 2 次。
- 运行时间超过 30 分钟自动停止。

## 12. 日志和产物位置

默认日志：

```text
~/lychee-szu-board-crawler/logs/szu-board-sync.log
```

默认数据：

```text
~/lychee-szu-board-crawler/data/szu_board_incremental_YYYYMMDD.xlsx
~/lychee-szu-board-crawler/data/state.json
```

`state.json` 会记录最近一次成功上传的文件和后端返回的 job 信息。

建议负责人每天检查一次日志，至少上线初期连续观察 3-5 天。

## 13. 常见问题

### 13.1 `Chrome 已尝试启动，但远程调试端口仍不可用`

可能原因：

- Chrome 路径不对。
- 9222 端口被占用。
- 系统权限阻止脚本启动 Chrome。

处理：

- 在 `config.yaml` 显式配置 `chrome_path`。
- 换一个端口，例如 `127.0.0.1:9223`。
- 手动用命令启动 Chrome 看是否报错。

### 13.2 `当前页面仍是统一身份认证`

说明登录态失效或还没登录。

处理：

1. 打开脚本启动的专用 Chrome。
2. 登录深大统一身份认证。
3. 确认能打开公文通列表页。
4. 重新运行脚本。

### 13.3 `后端导入失败 status=401`

说明 `ingest_token` 错了，或者服务器没有配置对应的 `SZU_BOARD_INGEST_TOKEN`。

处理：

- 向后端负责人确认最新 token。
- 确认 `config.yaml` 中没有多余空格。

### 13.4 `公文通 Excel 文件过大`

说明上传文件超过后端限制。

处理：

- 确认 `crawl_overlap_days` 是否被误设太大。
- 默认只抓 2 天，不要长期设为 30 天或更大。
- 如确需全量导入，提前和后端约定单独导入方式。

### 13.5 上传成功，但 Echo 搜不到新内容

可能原因：

- 上传 job 成功，但 embedding 还没补完。
- 问题关键词和文章标题/正文差距太大。
- 文章属于公众号/公文通里不明显的内容，需要优化 metadata。

处理：

- 先用标题原文搜索。
- 把后端返回的 job id 和文章 URL 发给后端排查。

## 14. 数据质量验收标准

每天自动任务成功后，建议检查：

- 日志最后一行包含 `[完成]`。
- 后端返回 `status=SUCCEEDED`。
- `failed_count=0`。
- Excel 有数据行，且字段名正确。
- 随机抽 3-5 条：
  - `title` 和公文通详情页一致。
  - `url` 可以打开。
  - `content` 覆盖正文主要内容。
  - `department/date/category` 没有明显错位。

如果是首次全量导入，建议额外检查：

- URL 无重复。
- `title/url/content` 为空的行数为 0。
- 发布日期范围符合预期。
- 抽查不同部门、不同分类的文章。

## 15. 双方职责边界

采集同事负责：

- 维护能访问公文通的运行机器。
- 维护 Chrome 登录态。
- 保证定时任务每天运行。
- 保证上传 Excel 字段格式正确。
- 发现抓取失败时提供日志和 Excel。

后端同事负责：

- 提供 `SZU_BOARD_INGEST_TOKEN`。
- 维护上传接口。
- 维护 Excel 解析、清洗、脱敏、入库逻辑。
- 处理导入失败、搜索不到、分类不准等后端问题。

## 16. 安全要求

- 不要把统一认证账号、密码、Cookie 写进代码仓库。
- 不要把 `config.yaml` 提交到 git。
- 不要把 `ingest_token` 发到公开群。
- Chrome 远程调试地址必须绑定 `127.0.0.1`，不要绑定 `0.0.0.0`。
- 日志中不要打印账号、密码、Cookie、完整 token。
- 如果运行机器离职/移交，需要更换后端上传 token。

## 17. 给后端的环境配置

线上后端需要配置：

```bash
SZU_BOARD_INGEST_TOKEN=一个足够长的随机字符串
SZU_BOARD_EXCEL_UPLOAD_MAX_SIZE_BYTES=52428800
KNOWLEDGE_METADATA_BACKFILL_RUN_ON_STARTUP=false
```

如果要在导入后自动补向量，可以由后端单独跑 embedding backfill，不建议采集脚本每次上传时打开 `backfill_embeddings=true`。

## 18. 当前历史数据说明

历史全量 Excel：

```text
szu_board_20250101_20260522.xlsx
```

历史校验结果：

- 数据量：`16032` 条
- 日期范围：`2025-01-02` 到 `2026-05-21`
- URL 重复数：`0`
- 空 URL：`0`
- 空正文：`0`
- 正文提取失败：`0`
- 覆盖发文单位：`87` 个

日常自动任务不需要重复上传这份全量文件，只需要上传最近 2 天的增量 Excel。后端会按 URL 幂等更新。
