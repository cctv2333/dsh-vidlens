# VidLens for DeepSeek Harness

[![ci](https://github.com/cctv2333/dsh-vidlens/actions/workflows/ci.yml/badge.svg)](https://github.com/cctv2333/dsh-vidlens/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/dsh-vidlens.svg)](https://www.npmjs.com/package/dsh-vidlens)
[![PyPI](https://img.shields.io/pypi/v/vidlens-mcp.svg?cacheSeconds=600)](https://pypi.org/project/vidlens-mcp/)
[![DSH plugin](https://img.shields.io/badge/topic-dsh--plugin-4B5563)](https://github.com/topics/dsh-plugin)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

把 [vidlens](https://github.com/cctv2333/vidlens) 从一个 stdio MCP 外壳变成 **DSH 原生插件**：18 个 `vidlens_*` 工具、图片直接进对话、按工具设超时、外加三个零下载的缓存工具。

工程本体（Python）没有改一行逻辑：插件通过一个常驻桥进程调用 `vl_mcp.py` 里**已经测过**的工具函数，所以 MCP 外壳和插件的行为不会漂移。

- 工程仓库（Python + MCP 服务器）：<https://github.com/cctv2333/vidlens>
- 本仓库（DSH 插件）：<https://github.com/cctv2333/dsh-vidlens>
- 插件要求：`vidlens >= 1.4.0`（`video_soundscape` 起）、Node ≥ 20、DSH `>=0.2.1-rc.2 <0.3.0`

```
用户: 这个视频讲了什么？ <url>
  → vidlens_meta      0 下载：值不值得看
  → vidlens_plan      0 下载：切章节，挑 2–3 段
  → vidlens_window    只下这一窗的音频（或直接读缓存/字幕）
  → vidlens_sheet     只下这 20 秒，拼图带时间码，图直接附在结果里
  → vidlens_brief     平台字幕优先；无字幕才下音频做本地 ASR
  → vidlens_soundscape 台词之外的声音（吃饭/敲击/水声），带概率
```

## 相对 MCP 外壳的增强

| 能力 | MCP 外壳 | 本插件 |
|---|---|---|
| 工具名 | `mcp__vidlens__video_meta` | `vidlens_meta`（短、可读） |
| 超时 | 客户端一个全局 60s | 每个工具自带预算（`vidlens_brief` 15 分钟，`vidlens_scan` 15 分钟） |
| 图片 | 取决于客户端是否支持 MCP image content | 走宿主 `attachments.saveImage`，成为**持久图片附件**，同轮就能看 |
| 缓存意识 | 无 | `vidlens_library`（零网络列缓存）、`vidlens_seek`（零网络查原话） |
| 批量筛选 | 无 | `vidlens_compare`（最多 8 个链接，0 媒体下载） |
| 行为约束 | 只在 MCP instructions 里 | 独立的 system-prompt 小节：先 meta→plan→抽样，绝不下整片 |
| 取消 | 断开连接 | `exec.signal` 取消时重启桥进程，不留下卡死的下载 |
| 整片下载 | `video_full(confirm=true)` 存在 | **故意不提供**：需要画面就用 sheet/frames/scan |

## 安装

**前置：先有一份 vidlens。** 二选一：

```bash
pipx install "vidlens-mcp[all]"          # 推荐：无 checkout，命令叫 vidlens / vidlens-mcp
# 或
git clone https://github.com/cctv2333/vidlens && cd vidlens && install.cmd
```

然后装本插件（三选一）：

```powershell
# A. 本地目录（开发；换成你自己 clone 的位置）
plugin_manager action=install_bundle target=<你的路径>\dsh-vidlens

# B. GitHub 直装（本包无 build/prepare 脚本，不需要 allowBuilds 权限）
#    注意：这条会真的 git clone 本仓库，会被 GitHub 记一次 clone
dsh plugin --profile desktop add github:cctv2333/dsh-vidlens#<sha>

# C. npm（registry，不经过 GitHub）
dsh plugin --profile desktop add dsh-vidlens
```

插件会自动找 Python 工程：`<本包>/../vidlens` → `D:\vidlens\vidlens` → `$VIDLENS_PROJECT`；
找不到时按 `$VIDLENS_PYTHON` / `.venv` / `python` 依次尝试。PyPI 安装的形态下，
把 `projectDir` 指到 `pipx` 的 venv 或直接设 `VIDLENS_PROJECT` 都行（模块名不变）。

安装后这个 bundle 会插入一行 Host 插件：

```yaml
- insert:
    - id: dsh-vidlens
      name: 'dsh-vidlens'
      config: {}
```

想改成别的工程位置（例如换机器）就在 `config` 里写：

```yaml
- insert:
    - id: dsh-vidlens
      name: 'dsh-vidlens'
      config:
        projectDir: D:\path\to\vidlens
        pythonPath: D:\path\to\vidlens\.venv\Scripts\python.exe
        warm: true
```

字段都可省略：`projectDir` 默认依次取 `<本包>/../vidlens`、`D:\vidlens\vidlens`、`$VIDLENS_PROJECT`；`pythonPath` 默认取工程 `.venv` 里的解释器。

## 工具（18 个）

**基础四件（0 下载）**

| 工具 | 用途 |
|---|---|
| `vidlens_meta(url)` | 标题/UP主/时长/播放/平台字幕/平台标注音乐 + 注入风险扫描 |
| `vidlens_plan(url, window=300)` | 按切点/长静音分章节 + 建议顺序 |
| `vidlens_subs(url, lang=zh)` | 平台字幕（人工优先，其次自动/AI） |
| `vidlens_library(limit=20, query='')` | **新增**：本地缓存清单，避免重复下载 |

**读内容**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `vidlens_watch(url, minutes=5, cursor="next")` | 每段该窗音频（或缓存） | **新增**：一段一段看（默认 5 分钟、约 0.5k 字），返回该段要点 + 「已看 X / 共 Y（%）」，并要求先汇报、再问用户要不要继续 |
| `vidlens_window(url, start, end)` | 0（有缓存/字幕）或该窗音频 | 某时间窗的台词与停顿 |
| `vidlens_brief(url, ..., level="digest")` | 平台字幕 0；无字幕才下音频 | **摘要**（默认约 1.5k 字：章节 + 5 句关键台词 + 全文路径）；`level="full"` 才给 6–9k 字完整报告（结构/停顿/低置信词/广告段落/风险） |
| `vidlens_seek(query, url='')` | 0（**新增**） | 在缓存转写里按关键词查原话 → 时间码 |
| `vidlens_audio(url, start, end)` | 该段音频 | SenseVoice 语种/情感/事件 + 节拍与能量 |
| `vidlens_soundscape(url, start, end)` | 该段音频 | **新增**：AudioSet 527 类声音事件（吃饭/敲击/水声/碰撞…）+ 概率 + 时间码 |

**看画面（图片直接进对话）**

| 工具 | 下载量 | 用途 |
|---|---|---|
| `vidlens_sheet(url, start, end, cols, rows)` | 该段（20s≈0.9MB） | 带绝对时间码的拼图 |
| `vidlens_frames(url, at=[...])` | 该段 | 最多 6 张精确帧（读小字用） |
| `vidlens_scan(url, n=24)` | 最低画质整片（7min≈14-21MB，用完即删） | 全片抽样拼图（无音频视频） |
| `vidlens_ocr(url, start, end, n=12)` | 该段最低画质 | **把画面上的字读成文本**（本地 OCR，离线）；无人声、无字幕的视频靠它，输出带时间码 |

`vidlens_ocr` 的引擎是可选依赖（RapidOCR，Apache-2.0，PP-OCRv6 模型随包分发，装完离线）。
**第一次调用不会偷偷下载**：它先告诉你「约 80MB、会装到哪个目录、怎么换目录」，
再调一次并传 `install: true` 才开始下，结果里会写清装到哪。

| 变量 | 作用 | 默认 |
|---|---|---|
| `VIDLENS_OCR_TARGET` | 装到指定目录（自动加入 import 路径，不写系统目录） | 本解释器 `site-packages`（Windows 上通常就是 **C 盘**） |
| `VIDLENS_OCR_AUTO_INSTALL` | `ask` 先问 / `auto` 自动装 / `off` 只给命令 | `ask` |

```
# 想放 D 盘 + 以后自动装（桥进程会读这两个环境变量）：
set VIDLENS_OCR_TARGET=D:\vidlens\ocr
set VIDLENS_OCR_AUTO_INSTALL=auto
```

没装也不会坏：`vidlens_ocr` 返回安装说明，其他工具不受影响。

### 上下文预算（为什么默认给摘要）

一次「看视频」如果按老路子走，实测是这么多字符：

| 调用 | 字符 | 说明 |
|---|---|---|
| `meta` + `plan` | ~730 | 便宜 |
| `window` × 3（各 1 分钟） | ~2,800 | ~0.9k/分钟 |
| `soundscape`（60 秒） | ~1,500 | 12 窗 × 8 标签 |
| `brief`（旧版全量） | **~9,000** | 6–9k 字 ≈ 4–6k tokens |
| 合计 | **~14,200** | 还没算图片 |

关键不在单次有多大，而在于**这些字符之后每一轮都在上下文里**。一个 64k 窗口，
两三个视频 + 正常对话就会顶到上限，于是出现「看完视频就超上下文」。

所以默认改成三档，按需升级：

1. `vidlens_brief` → **摘要**（约 0.7–1.5k 字：标题/时长/语音覆盖/章节/5 句均匀取样的关键台词/全文路径）；
2. `vidlens_window` → 只读某一段（约 0.8k 字/分钟），读细节用它，别用 brief 代；
3. `vidlens_brief(level="full")` → 完整报告（6–9k 字），**只在用户明确要全文时**用一次。

全文始终写在 `out/<id>/brief.md`，不会丢；摘要里直接给路径和下一次该调什么。
`vidlens_window` 另有 80 行上限，超了会明说「还有 N 行，缩小范围」而不是无限倾倒。

**判断 / 长视频 / 自检**

| 工具 | 用途 |
|---|---|
| `vidlens_comments(url, limit=40)` | 评论区互动比、正负面、争议度、高赞评论 + 评论配图 |
| `vidlens_compare(urls=[...])` | **新增**：批量元数据对比（0 媒体下载，最多 8 个） |
| `vidlens_job_start(url, ..., full=False)` | 长视频后台任务，立即返回 `job_id` |
| `vidlens_job(job_id, wait_seconds=20)` | 轮询阶段/百分比，完成返回报告 |
| `vidlens_models(action=list)` | 本地模型目录 + 本机真实路径；`action=download, name=..., confirm=true` 才真下（ced-mini 10MB / whisper 75–484MB） |
| `vidlens_doctor()` | 自检 python/ffmpeg/yt-dlp/依赖/模型/磁盘/网络 |

## 架构

```
DSH Host (index.js)
  ├─ 18 × ctx.tools.register(...)        原生工具 + 每工具 timeoutMs
  ├─ ctx.systemPrompt.section('vidlens') 取样协议（meta→plan→抽样）
  └─ Bridge (常驻)  ──stdin/stdout JSONL──▶  python -u bridge/vidlens_bridge.py
                                                │
                                                ├─ import vl_mcp   （复用工具函数）
                                                ├─ import vidlens_web / _extra / _sanitize
                                                └─ out/<id>/        （缓存，进程重启不丢）
```

**为什么不是直接把 MCP 服务器挂上来**：MCP 客户端只有一个全局工具超时，长视频 ASR 会被误杀；图片是否进模型取决于客户端实现；也拿不到「缓存清单 / 关键词定位」这类只在本地才有答案的能力。桥进程把「已验证的 Python 逻辑」和「宿主的原生能力」接在一起，两边都不用重写。

**协议**（每行一个 JSON）

```jsonc
// 启动
{"op":"ready","ok":true,"pid":1234,"project":"D:\\vidlens\\vidlens","python":"3.12.10","tools":["meta",...]}
// 请求 → 响应
{"id":7,"tool":"sheet","args":{"url":"...","start":"0","end":"20"}}
{"id":7,"ok":true,"text":"...","images":[{"path":"...jpg","mediaType":"image/jpeg","name":"sheet_0_20000.jpg"}]}
{"id":8,"ok":false,"error":"ValueError: ...","trace":"..."}
```

`sys.stdout` 在导入任何库之前就被指向 stderr，所以依赖里的杂散 `print` 不可能污染协议；桥只把帧写进保存下来的真实 stdout。

**多进程安全**：DSH 会话、MCP 服务器、插件桥是**不同进程**，进程内 `threading.Lock` 互相看不见。
工程侧用 `vidlens_web.CrossProcessLock`（进程内 RLock + `out/.media.lock` 文件锁，msvcrt/flock）
把「一个下载口」扩展到整台机器；超时可用 `VIDLENS_LOCK_TIMEOUT`（默认 900s）调整。
实测两个进程同时调 `video_sheet`：第二个的 acq 时间落在第一个 end 之后（串行，不互相踩）。

## 验证

**离线（不联网、不下媒体）**

```powershell
node D:\vidlens\vidlens-mcp-dsh\tools\selftest.mjs
# 96/96 checks passed（工具表 + 桥握手 + library/models/seek + 强制杀进程后自愈）
```

**带真实链路（约 1MB 媒体）**

```powershell
node D:\vidlens\vidlens-mcp-dsh\tools\selftest.mjs --live
# 98/98 checks passed
```

**安装后在 DSH 里的实测**（本机 2026-10-25，全部走原生工具通道）

| 调用 | 结果 |
|---|---|
| `vidlens_library(limit=6)` | 9 个缓存视频，标题/时长/段数/来源/占用/时间齐全（`out/` 里的 `bili/`、`comment_pics/` 等非视频目录已自动排除） |
| `vidlens_doctor()` | 11/11：python 3.12.10、ffmpeg 7.1、yt-dlp 2026.10.21、4 个依赖、whisper 461MB、磁盘 332GB、B站 API 200 |
| `vidlens_meta(BV1PinG6fEPX)` | 真实标题/UP主/139514 播放；正确报出「字幕需要登录」 |
| `vidlens_plan(window=120)` | 3 章节，0 下载 |
| `vidlens_window(02:10–02:25)` | `asr(cached)`，0 下载直接读缓存 |
| `vidlens_seek("宪法")` | 3 条原文 + 时间码（`00:20.460`、`02:17.720`…），0 网络 |
| `vidlens_sheet(60–72s, 3×2)` | 下载 12 秒，产出 1440×540 拼图，**图片作为持久附件进入对话**（时间码 `00:00:59.995 … 00:01:09.594`） |
| `vidlens_frames([63, 68])` | 2 张 960×540 帧，同一条结果里两张图都在 |
| `vidlens_compare(2 个链接)` | 一张 markdown 表，0 媒体下载 |
| `vidlens_job_start` → `vidlens_job` | 起任务拿到 `job_id=6652ac4e`，轮询后返回完整 brief（`asr(cached)`，含低置信词/停顿/广告段） |
| `vidlens_meta(错误 URL)` | 可读错误：`ERROR: meta failed rc=1: ... HTTP Error 404`，工具不崩 |

拼图实测（时间码烧在每格左上角）：

![contact sheet](../vidlens/out/BV1PinG6fEPX/sheet_60_72/sheet_60000_72000.jpg)

## 发布（维护者）

- CI：`.github/workflows/ci.yml` —— 会 checkout 两个仓库（本插件 + `cctv2333/vidlens` 作为兄弟目录），
  装 Python 核心后跑离线自检；另外两个 job 校验 manifest 可发布、tarball 含 `bridge/` 与 `LICENSE`。
- 发版：打 tag 即发布 npm。

```bash
git tag v1.2.0 && git push origin v1.2.0
```

`release.yml` 会 `npm pack`、`npm publish --access public`，走 **Trusted Publishing（OIDC）**——
CI 里没有任何长期 token。npm 的 publisher 只能在包存在后配置，所以**首次发布要在本地做一次**
（`npm stage publish` → `npm stage approve`，全程不需要把 token 交给 CI，见 `RELEASING.md`），之后打 tag 即可。

> 注意：PowerShell 5.1 不支持 `&&`，用 `;` 或分行。

## 实现笔记

- **`output.schema` 不能用 `{type:'json'}`**：宿主对工具输出 schema 做严格校验，只接受
  object/array/string/number/integer/boolean/null。第一版用了 `{type:'json'}`，安装直接
  `application: failed`（`JsonSchemaError: unsupported JSON schema`）。现在写成显式的
  object schema（`text` + `images[]`）。
- **被杀掉的旧进程不能污染新进程**：超时/取消会 `kill()` 工作进程并在同一 tick 重建。旧
  进程的 `exit` 事件是异步到的，必须先判 `this.child !== child` 再清理，否则它会把**新**
  进程上排队的请求全部 reject（这个 bug 是自检里的「强制杀进程后自愈」用例抓到的）。
- **本插件不导出 `Config`**：`Config.listConfigs` 里这一行显示 `status: absent`（没有配置
  schema），但 `config:` 里的 `projectDir` / `pythonPath` / `warm` 仍会原样传给 `apply()`。
  不导出 schema 是刻意的：schema 需要 schemastery，而插件的解析链未必能找到宿主那份
  `@deepseek-ai/schemastery`；宁可少一个设置表单，也不要一个「载入期 import 失败 → 18
  个工具整体消失」的失败模式。
- **图标**：`icon.svg` 是原创矢量图（2042 字节，well-formed XML，256×256，边缘圆角 +
  时间码刻度 + 镜头环 + 播放三角）。结构校验通过；Plugin Manager 里的实际渲染效果
  没有在浏览器里验证（无头浏览器对 `file:` / `data:` 导航超时），这一项留待用户目视确认。


## 路线图

产品级路线图（已做 / 未做 / 验收标准 / 不做清单）在工程仓库：
[vidlens/ROADMAP.md](https://github.com/cctv2333/vidlens/blob/main/ROADMAP.md)。

插件专属待办，按工作量从小到大：

1. `Config` schema（现在 `status: absent`，只能手改 YAML）
2. `/vl <url>` 斜杠命令
3. `present` 交付物卡片（brief.md / 拼图）
4. 右侧栏 Web 面板（缓存列表 + brief 预览 + 时间轴）
5. 设置页（模型路径 / 代理 / cookie）

## 边界与已知限制

- **job 状态在进程内存**：`vidlens_job_start` 起的任务，桥进程重启（超时/取消/宿主重启）后会消失；已下的缓存不丢，重跑即可。
- **取消 = 杀桥进程**：Python 侧没有协作取消，所以被取消/超时的调用会重启工作进程（缓存在磁盘上，代价很小）。
- **需要 cookie 的站点**（抖音、B 站 AI 字幕）默认不碰：按报错提示设 `VIDLENS_COOKIES_FROM_BROWSER=edge` 或 `VIDLENS_COOKIES=path\cookies.txt`。
- **不下整片**：`video_full` 故意没有移植。整片画面需求用 `vidlens_scan`（最低画质、用完即删）。
- **PyPI 形态也能接**：工程装成 wheel 后没有 `vidlens.py` 旁边的 checkout 标记，插件的
  目录嗅探找不到它；把 `config.projectDir` 指到 `pipx` 的 venv 目录（或任意含 `vidlens.py`
  的目录），或设 `VIDLENS_PROJECT` 即可。安装形态下 `out/` 会落在 `%LOCALAPPDATA%\vidlens\out`。
- **Windows 优先**：工程默认路径与 `.venv\Scripts\python.exe` 是 Windows 习惯；Linux/macOS 用 `projectDir` + `pythonPath` 显式指定即可（跨进程锁在 POSIX 用 `flock`）。
- 工程本体仍无 `LICENSE`，公开分发前需项目所有者选定；本包 `license` 标为 `UNLICENSED`。
