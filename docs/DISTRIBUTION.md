# 分发：把 vidlens 的 MCP 服务器和 DSH 插件发出去

> 两份东西要分开分发，混在一起发会失败：
> 1. **`vidlens`（Python 工程）** = CLI + MCP stdio 服务器（`vl_mcp.py`）。
> 2. **`vidlens-mcp-dsh`（本包）** = DSH 插件 bundle，**不含** Python 工程，靠 `projectDir` 找它。
>
> 所以插件可以单独发 npm，但用户还得有一份 `vidlens` checkout。这个「两段式安装」必须写进 README 第一屏。

## 0. 公开之前必须解决的（blocker，不是技术问题）

| 项 | 现状 | 必须先做 |
|---|---|---|
| LICENSE | ✅ 两个仓库都已放 **MIT**（`vidlens/LICENSE`、本包 `LICENSE`） | 无需再动；发布时 `package.json` 的 `license` 改成 `"MIT"` |
| 依赖许可 | yt-dlp Unlicense / faster-whisper MIT / sherpa-onnx Apache-2.0 / imageio-ffmpeg BSD-2 / ffmpeg 二进制 LGPL-GPL（**子进程调用、不链接**） | `NOTICE.md` 已登记，保留并在 README 链出 |
| 模型权重 | SenseVoice 937MB、Whisper 461MB、CED-mini 10.4MB —— **都不随包** | README 给出处 + 许可 + 下载命令（`tools/fetch_sound_model.py`）；绝不打包 |
| 用户数据 | `out/`（转写、截图、评论） | `.gitignore` + `files` 白名单双重排除 |
| cookie | `mcp.json`、cookie 库 | 永不入库；只走 `VIDLENS_COOKIES*` 环境变量 |

**许可决定（2026-10-25）**：项目所有者选择 **MIT**，不商用顾虑不存在——
MIT 允许别人商用，但保留版权声明与免责；如果你以后想禁止商用，才需要换 AGPL/自定义许可。
已落地：工程根 `LICENSE`、插件根 `LICENSE`。

## 1. DSH 插件：三条分发路径（都实测过机制）

官方文档：<https://deepseek-harness.github.io/deepseek-harness/develop/basic/publish.md>
（要点：bundle 的 `dsh.bundle.patch`、`engines.dsh`、profile 的 `dsh.profile.bundles`、层叠顺序）

### A. npm 公开发布（推荐，用户最省事）

```bash
# 1) 去掉 "private": true，补 license/repository/keywords
# 2) 确认 files 白名单包含 bridge/vidlens_bridge.py
npm publish --access public
```

用户侧（任选其一）：

```
plugin_manager action=install_bundle target=@you/dsh-vidlens
# 或 CLI
dsh plugin --profile desktop add @you/dsh-vidlens
```

注意：注册表安装会用 `saveExact: true` 钉版本；`engines.dsh` 不满足会在**下载前**被拒。

### B. 直接从 GitHub 装（不用发 npm）

```bash
dsh plugin --profile desktop add github:you/vidlens-mcp-dsh
# 想锁死内容就钉 commit：
dsh plugin --profile desktop add github:you/vidlens-mcp-dsh#<sha>
```

**本包的特殊优势**：它是纯 ESM JS，`package.json` 里**没有任何 `scripts`**（无 build / 无 prepare）。
官方文档里那个「git 安装只拿源码、要用户 `allowBuilds` 才能跑 `prepare`」的坑，本包**不踩**。
这也是为什么不要把 `index.js` 改成 TypeScript 源码分发——一旦引入 `prepare`，每个用户都要开一次
「允许执行安装脚本」的权限。

### C. 离线 tarball（内网 / U 盘 / 评审）

```bash
pnpm pack                      # 产出 dsh-vidlens-1.0.0.tgz
dsh plugin --profile desktop add ./dsh-vidlens-1.0.0.tgz
```

### 仓库结构：两个仓库，还是一个？

**结论：两个仓库（推荐）。** 理由不是审美，是依赖方向与发布节奏：

| | `vidlens`（Python / MCP） | `dsh-vidlens`（DSH 插件） |
|---|---|---|
| 语言/工具链 | Python + pip/uv + pytest | Node ESM + pnpm/npm |
| 发布渠道 | PyPI（`pipx install vidlens-mcp`） | npm（`dsh plugin add …`）/ GitHub / tgz |
| 版本节奏 | 跟视频/ASR 能力走 | 跟 DSH API 走（pre-1.0，minor 会动） |
| 依赖方向 | 不依赖插件 | **单向依赖** vidlens 的 Python 函数 |
| 安装体积 | 含 `.venv` 与模型（模型不随包） | 只有几十 KB 胶水 |

一个仓库也不是不行（monorepo + pnpm workspace + `packages/`），但你会立刻遇到两件事：
npm 发布要按子包 `files` 白名单、Python 打包要在同一个仓库里再配一套 CI。
**除非你打算再发 2–3 个 DSH 插件，否则不值得。**

命名与发布前要改的三处（`@local` 不是可发布的 scope）：

```text
1) package.json: "name": "dsh-vidlens"        # 或 "@yourname/dsh-vidlens"
2) package.json: 删除 "private": true          # npm 拒绝发布 private 包
3) package.json: "license": "MIT"
4) cordis.patch.yml 与 README 里的 dsh-vidlens 同步改名
5) 重新安装一次（旧的 link 仍指向老包名）：
   plugin_manager action=set_bundle enabled=false target=dsh-vidlens
   plugin_manager action=install_bundle target=D:\vidlens\vidlens-mcp-dsh
```

插件仓库结构：

```
dsh-vidlens/
├── package.json          # dsh.bundle + engines.dsh + files 白名单 + MIT
├── cordis.patch.yml
├── index.js
├── bridge/vidlens_bridge.py   ← 必须在 files 里，npm 默认会漏
├── locale/{en,zh}.json
├── icon.svg
├── LICENSE
├── README.md             # 两段式安装写第一屏
├── docs/
└── tools/
    ├── selftest.mjs
    └── fetch_sound_model.py   # 10.4MB 声音事件模型（不随包）
```

### 发布前自查（照着敲）

```powershell
node tools/selftest.mjs            # 101 项离线自检
node tools/selftest.mjs --live     # 105 项，含真实下载 + 出图 + 声音事件
npm pack --dry-run                 # 看包里到底有什么（python 桥在不在）
```

`npm pack --dry-run` 的输出里必须能看到 `bridge/vidlens_bridge.py` 与 `LICENSE`，
且**看不到** `out/`、`.venv/`、`bin/`、`__pycache__/`、模型文件。

## 2. MCP 服务器：怎么发

### A. PyPI 包（**已实现**，`vidlens/pyproject.toml`）

```
vidlens/
  pyproject.toml      # [project.scripts] vidlens + vidlens-mcp；extras: sensevoice/whisper/audioevents/all
  LICENSE             # MIT
```

- 用户：`pipx install "vidlens-mcp[all]"`，MCP 配置写 `{"command": "vidlens-mcp"}`，
  不再依赖绝对路径。
- 已验证：`uv build --wheel` → `vidlens_mcp-1.4.0-py3-none-any.whl`，含 10 个模块 +
  `LICENSE`/`NOTICE.md` + 两个 console script；装到临时目录后从空 cwd 导入，
  `out_root` / `ffmpeg_dir` 落到 `%LOCALAPPDATA%\vidlens`，16 个 MCP 工具可加载。
- **打包时踩过的坑**：`out/` 与 `bin/` 原来跟着模块目录走，装进 site-packages 后等于往
  代码目录写数据。已改为 `vidlens.project_root()`：检测到 checkout 标记（`install.cmd` /
  `requirements.txt` / `HARDCODE_AUDIT.md`）就用工程目录，否则用用户数据目录。
- `vl_mcp.main()` 是 stdio 服务器，包内不能有任何 import-time `print`；
  `tests/test_mcp.py` 做真实 stdio 握手。
- 发布命令：`uv build && uv publish`（或 `python -m build && twine upload dist/*`）。

### B. GitHub Release + zip

`dist/vidlens-src-YYYYMMDD.zip` 已经在做，LICENSE 已就位；Release notes 写清
「Windows 自动装最顺，Linux/macOS 需手动装 ffmpeg」并附 `SHA256SUMS.txt`。

### C. MCP 注册表 / 商店（可选，需再核实）

MCP 生态有官方 registry 与若干第三方目录，通常要求仓库里放 `server.json`
并用发布 CLI 推一次。**这一条我没有在你机器上验证过，属于可选加分项**，
优先级低于 A：用户真正痛的是「装 Python 依赖」，不是「找不到」。

## 3. 版本与兼容策略

- 插件 `engines.dsh: ">=0.2.1-rc.2 <0.3.0"`：DSH 还是 pre-1.0，minor 之间 API 会动；
  显式声明比装上了再崩更好。
- 插件与 Python 工程的**耦合点只有 17 个函数名 + 参数名**（`vl_mcp.py`）。
  建议在插件 README 写「兼容 vidlens ≥ 1.3.0」，并在 `vidlens_doctor` 里加一条版本检查。
- 发版：`CHANGELOG.md` + GitHub Releases；插件语义化版本，工程独立版本，互不绑定。

## 4. 我可以直接帮你做的

1. `LICENSE` + `package.json` 的 license/repository/keywords/engines 字段（你选许可，我落地）；
2. `scripts/pack.mjs`：打 tgz 并断言「bridge 在包里、out/ 不在包里」；
3. GitHub Actions：tag → `npm publish` + `pnpm pack` 上传 Release，跑 selftest 作为门禁；
4. 单包 repo → monorepo 的迁移（如果打算发多个插件）。
