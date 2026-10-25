# 问题清单（bug / 边界 / 编码 / 并发）

> 只写**能指出证据**的条目。状态：`[OPEN]`／`[FIXED]`／`[BY DESIGN]`。
> 编号规则：I-序号；与工程本体的 `BUG_LEDGER.md`（B-xxx）互相独立。

| # | 状态 | 问题 | 证据 | 处置 |
|---|---|---|---|---|
| I-001 | `[FIXED]` 1.0.1 | 取消/超时只杀 Python 工作进程，`yt-dlp` / `ffmpeg` 是孙进程会变孤儿，继续往 `out/` 写 | `Bridge.kill()` 原先只有 `child.kill()` | Windows 改 `taskkill /PID <pid> /T /F`（杀整棵树）；POSIX 仍是 SIGKILL，可能留孤儿（已在代码注释与 README 说明） |
| I-002 | `[FIXED]` 1.0.0 | 被替换掉的旧工作进程，其 `exit` 事件会把**新**进程上排队的请求全部 reject | 自检「强制杀进程后自愈」用例复现：`vidlens 桥已退出（code=null signal=SIGTERM）` | `exit`/`error` 回调先判 `this.child !== child` |
| I-003 | `[FIXED]` 1.0.0 | 工具输出 schema 用 `{type:'json'}` 被宿主拒绝，整行 `application: failed` | 安装回执：`JsonSchemaError: unsupported JSON schema: schema.type must be one of …` | 改成显式 object schema（`text` + `images[]`） |
| I-004 | `[OPEN]` | **跨进程并发**：每个 DSH 会话、以及 MCP 服务器，各起一个 Python 进程；`_MEDIA_LOCK` 是进程内的 `threading.Lock`，两个进程同时处理同一个视频会争 `out/<id>/`（临时目录、`sheet_*`、`transcript.jsonl`） | `vl_mcp.py` 的锁是模块级 `threading.Lock`；插件按会话起桥 | 建议：`out/<id>/.lock` 文件锁（带 PID + 过期），或每个来源用独立 `VIDLENS_OUT`。属于工程本体改动，未做 |
| I-005 | `[OPEN]` | `vidlens_brief` 在 MCP/插件通道按 9000 字截断，模型可能不知道内容被截断 | `vl_mcp.py`：`brief[:MAX_BRIEF_CHARS] + extra` | 桥里加了显式提示（见 I-005 修复）；根治要在工程里返回结构化 `truncated:true` |
| I-006 | `[FIXED]` 1.0.1 | 长 brief 被截断时不提示 | 同上 | 桥对 `brief` 结果长度 ≥ `MAX_BRIEF_CHARS` 时追加「已截断，全文见 brief.md」 |
| I-007 | `[BY DESIGN]` | 插件没有 `Config` schema：`Config.listConfigs` 显示 `status: absent` | 本会话实测 | `config:` 里的 `projectDir/pythonPath/warm` 仍原样传给 `apply()`；不引入 schemastery 以避免「import 失败 → 17 个工具整体消失」 |
| I-008 | `[OPEN]` | 控制台编码假报警：PowerShell 5.1 的 `Get-Content` 默认按 ANSI 解码 UTF-8，`locale/zh.json` 看起来像坏文件 | 本次 `ConvertFrom-Json` 报「未终止的字符串」，而 `read`/`node` 读同一文件完全正常 | 文档化：校验 UTF-8 用 `Get-Content -Encoding utf8` 或 node/python；不是数据损坏 |
| I-009 | `[OPEN]` | `vidlens_library` 只按目录/文件存在性统计，不校验媒体完整性；半截下载的 mp4 也会显示 | `tool_library` 只 `stat` 汇总体积 | 可加「媒体文件存在但无 `transcript.jsonl`」标记；工程本体有 `media_duration` 校验，插件没调用 |
| I-010 | `[OPEN]` | `out/` 无自动清理入口 | 插件没有 clean 工具；CLI 有 `vl clean` | 可加 `vidlens_clean(days, dry_run=true)`（默认 dry-run） |
| I-011 | `[OPEN]` | `vidlens_compare` 串行 `fetch_meta`，8 个链接最坏几十秒 | `tool_compare` 里是 `for` 循环 | 可并发（`ThreadPoolExecutor` 4 并发）；注意 yt-dlp 礼貌限速，不宜太高 |
| I-012 | `[OPEN]` | `vidlens_seek` 每次全量扫描所有 `transcript.jsonl`；缓存上千后变慢 | `tool_seek` 遍历 `_cache_dirs()` | 可建 `out/.index.jsonl`（id/时间/文本倒排），或先按 `query` 过滤目录名 |
| I-013 | `[BY DESIGN]` | 桥是**单线程串行**：一个 15 分钟的 `vidlens_brief` 会挡住同一会话里的 `vidlens_library` | `for line in sys.stdin` 顺序处理 | 与工程「一个下载口」的串行策略一致；要并行就起工作进程池（代价是内存 × N） |
| I-014 | `[OPEN]` | 非 ASCII / 含空格工程路径未实测（`.venv` python、ffmpeg shim 复制、cookie 文件路径） | 本机全 ASCII 路径 | 协议层已强制 UTF-8（`reconfigure` + `PYTHONIOENCODING`），参数走 JSONL 不经 argv；仍需一次中文路径实测 |
| I-015 | `[OPEN]` | Linux/macOS 只有代码分支，未实测 | `resolvePython` 有 `.venv/bin/python`；`kill` 无进程树 | 分发前至少在 WSL 跑一遍 selftest（离线部分） |
| I-016 | `[OPEN]` | `engines.dsh` 刚声明为 `>=0.2.1-rc.2 <0.3.0`，没有跨版本验证矩阵 | 官方文档要求声明，但 DSH 是 pre-1.0 | 每次 DSH 升级后重跑 `selftest.mjs` + 一次真实工具调用 |
| I-017 | `[BY DESIGN]` | `vidlens_job_start` 的任务状态在桥进程内存，重启即丢 | `extra.JOBS` 是模块级 dict | 缓存不丢，重跑即可；已在工具描述与 README 写明 |
| I-018 | `[BY DESIGN]` | 不提供整片下载（MCP 壳里的 `video_full` 未移植） | `TOOLS` 里没有对应条目 | 与工程「默认不下整片」一致；要画面用 sheet/frames/scan |
| I-019 | `[OPEN]` | `attachments` 服务缺失时图片会被跳过（有备注但不报错） | `attachImages` 返回 notes | 属于宿主环境问题；备注已写进结果文本 |
| I-020 | `[OPEN]` | 模型权重路径是「本机兜底」（`D:\dev\models\...`），换机要靠环境变量 | 工程 `HARDCODE_AUDIT.md` 已登记 | 分发 README 必须写 `VIDLENS_MODEL_DIR` / `VIDLENS_SENSEVOICE_*` / `VIDLENS_TAGGING_*` |
| I-021 | `[BY DESIGN]` | 声音事件概率整体偏低（0.15–0.5 常见），`>0.3` 才值得当真 | 实测：真实视频 `Speech 0.86 / Music 0.87` 很稳，但敲击类只有 0.17–0.23 | AudioSet 527 类多标签本身如此；输出保留概率、不转成布尔断言，`min_prob` 可调 |
| I-022 | `[BY DESIGN]` | 喝水/吞咽识别不了 | AudioSet 标签表逐条核对：无 Drink/Sip/Gulp 类 | 只能靠 `Water`/`Water tap` + 画面推断；要准需 CLAP 零样本或自训（Tier 2/3） |
| I-023 | `[FIXED]` 1.1.0 | 相邻窗口同名标签被拆成两段（如 `Speech synthesizer` 出现两次） | 合并阈值原为固定 0.51s，hop=5s 时接不上 | 改为 `gap = hop × 1.2`，传 hop 进 `_segments` |
| I-024 | `[OPEN]` | `AudioTagging` 实例非线程安全 | sherpa-onnx 的 C++ 对象无可重入保证 | 模块内一把 `threading.Lock` 串行化；桥本身也单线程 |
| I-025 | `[OPEN]` | 声音事件没有进 `brief.md`（只有独立工具） | `build_brief` 未调用 `ae.scan` | 需要时再按 `soundscape=true` 增量加，避免每个视频平白多算 CPU |
| I-026 | `[FIXED]` 1.2.x | Linux 上拼图整张失败：本机 ffmpeg 无 `drawtext` | GitHub CI（ubuntu）抓到的真实失败：`No such filter: 'drawtext'` | 工程侧 `has_drawtext()` 探测后跳过烧字，照样出图；插件无需改动 |

## 编码相关的三条硬规则（给以后的人）

1. **不要用 argv 传中文**：工程 README 已警告（Windows 代码页）。插件把参数放在 **UTF-8 JSONL** 里，
   天然规避；桥启动时 `sys.stdin/stdout.reconfigure(encoding='utf-8')`。
2. **stdout 只放协议帧**：桥在 import 任何库之前就把 `sys.stdout` 指向 stderr，帧写向保存下来的真 stdout。
   依赖里任何 `print` 都不会破坏协议。
3. **`.cmd` 必须 CRLF、读文件显式指定编码**：工程已知坑；Python 侧统一 `encoding='utf-8'`。
