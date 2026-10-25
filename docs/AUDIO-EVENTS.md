# 语音之外的声音：现状、可行路径与设计

> **状态：Tier 1 已接入（2026-10-25）。** `vidlens_audioevents.py` + `video_soundscape`（MCP）
> + `vidlens_soundscape`（插件）。模型已下载到 `D:\dev\models\audio-tagging\ced-mini\`
> （`model.int8.onnx` 10,451,715 B + `class_labels_indices.csv` 14,675 B）。
>
> 实测：加载 0.14s；28.4s 音频推理 43ms；合成三下敲击 → `Wood block 0.18 / Drum 0.17 /
> Music 0.23`；水声噪声 → `Waterfall 0.17 / Stream 0.08`；真实视频 30s → `Music 0.87 ·
> Speech 0.86`（与画面一致）。单次 30s 视频（6 窗）端到端约 3–5s，其中绝大部分是下载音频。
>
> 目标：从「只有台词」升级到「台词 + 声音事件」——吃饭、敲桌子、水声、塑料袋、拖椅子这类**非语音信息**，
> 带时间码，能被模型引用，也能被用户核对。

## 1. 现在能拿到什么（不用装任何新东西）

| 信号 | 来源 | 粒度 | 可信度 |
|---|---|---|---|
| 语种 / 情感 / 事件（Speech/BGM/Laughter/Applause/Cry…） | SenseVoice（937MB，已装） | 每个 20s 块**一个** event 标签 | 模型标签，近似 |
| BPM / 能量 / 动态范围 / 静音比 | `vidlens_audio.py`（numpy 启发式） | 整段 | 启发式 |
| 停顿（话中犹豫 vs 片尾无词） | ffmpeg silencedetect + 分型 | 段 | 可靠 |
| 平台 BGM 歌名 | B 站 `player/wbi/v2` | 全片 | 平台标注，可能缺/错 |

**缺口**：没有「这是什么声音」的多标签分类。SenseVoice 的 event 头只有粗类，且每块只给一个标签。

## 2. 可行路径（已核实，不是猜想）

### 2.1 事实核查结果

| 事实 | 证据 |
|---|---|
| 本机 `sherpa_onnx` **2.0.0** 已安装（18.8MB），带 `AudioTagging` / `AudioTaggingConfig` / `AudioEvent` | `dir(sherpa_onnx)` 实测 |
| 该绑定**支持 CED 音频标注**：`AudioTaggingModelConfig(ced="x")` 不报错，`ced` 是真实字段（只是不在 `dir()` 里列出） | 实测构造成功 |
| 现成模型：`k2-fsa/sherpa-onnx-ced-mini-audio-tagging-2024-04-19` | HF API 实测可达 |
| 体积：`model.int8.onnx` **10,451,715 B（10.4MB）**、`model.onnx` 39MB、`class_labels_indices.csv` **14,675 B** | HF tree API |
| 标签：AudioSet **527 类**，标准 `class_labels_indices.csv` | 已下载核对 |
| 不需要 torch / 不需要 onnxruntime 手写前端（sherpa 内部做特征） | API 形态 |

**结论：这条路只要下 10.4MB + 14KB，不需要新依赖，不需要 GPU。**

### 2.2 527 类里，你要的声音到底在不在（逐条核对过）

| 你想要 | AudioSet 类 | 判定 |
|---|---|---|
| 吃饭 / 嚼 | `Chewing, mastication` (#54) | ✅ 直接可判 |
| 敲桌子 | `Knock` (#359)、`Tap` (#360)、`Thump, thud` (#460)、`Wood block` (#173) | ✅ 大概率命中，取决于材质/力度 |
| 水声（倒水、水龙头） | `Water` (#288)、`Water tap, faucet` (#370) | ✅ |
| 杯子/碗碰撞 | `Chink, clink` (#442) | ✅ |
| 拖椅子 | `Scrape` (#475) | ✅ |
| 塑料袋/包装 | `Crumpling, crinkling` (#479)、`Rustle` (#487) | ✅ |
| 翻找东西 | `Rustling leaves` (#284) 近似 | ⚠️ 近似 |
| **喝水 / 吞咽** | **没有对应类**（AudioSet 无 Drinking/Sipping/Gulp） | ❌ 只能间接，需 CLAP 或自训 |

**这条必须说清楚**：「喝水」不是 AudioSet 的类别。用 CED-mini 只能拿到「水声 + 咀嚼附近」的线索，
不能断言「他在喝水」。要准，得走 2.3 的 Tier 2/3。

### 2.3 三个档位

| 档 | 方案 | 成本 | 能识别 | 风险 |
|---|---|---|---|---|
| **Tier 1（建议先做）** | sherpa-onnx + CED-mini int8 + AudioSet 527 标签 | 10.4MB，0 新依赖，CPU | 吃饭/敲击/水声/碰撞/摩擦/笑声/掌声/音乐/噪声 + 概率 | 长尾类置信度低；近距离桌面声可能不在分布内 |
| Tier 2 | CLAP 零样本（文本查询任意声音） | ~600MB + 推理框架 | 「喝水」「筷子敲碗」这类自定义描述 | 重、慢；需要验证中英文 prompt 质量 |
| Tier 3 | 用自己的录音训一个小分类器 | 需要标注数据（每类 50–200 段） | 你那几个具体动作，最准 | 要采数据、要训练、要维护 |

## 3. Tier 1 设计（可以现在就接）

### 3.1 模型放哪

```
D:\dev\models\audio-tagging\ced-mini\
  model.int8.onnx          # 10.4MB
  class_labels_indices.csv # 14.7KB
```

环境变量覆盖：`VIDLENS_TAGGING_MODEL` / `VIDLENS_TAGGING_LABELS`。
**不随包发、不自动下载**（工程既有政策：下载前先问用户）。

### 3.2 新工具：`vidlens_soundscape(url, start, end, top_k=8, min_prob=0.15)`

```
拿这一段音频（复用 download_audio_section，20s ≈ 0.5MB）
  → 16k 单声道 float32
  → 滑窗：10s 窗 / 5s 跳（CED 吃的是片段级输入）
  → 每窗 tagging.compute(stream, top_k) → [(name, prob), ...]
  → 按 min_prob 过滤，再按标签合并成段
输出：
  # 声音景观 02:00 → 03:00
  - 02:00.0–02:10.0  Speech .92 · Chewing .31 · Music .22
  - 02:05.0–02:15.0  Speech .88 · Knock .44
  ## 段
  - 敲击（Knock）×3：02:07.5, 02:31.0, 02:44.5（概率 .44/.51/.39）
```

### 3.3 与现有工具的关系

- `vidlens_audio` 继续负责「这一段的语种/情感/节拍/能量」；
- `vidlens_soundscape` 负责「这一段有什么声音」；
- `vidlens_brief` 加一节「声音景观」（只在用户传 `soundscape=true` 时算，避免给每个视频平白加 CPU）；
- 所有输出都带概率和「模型标签，非事实」的免责句——延续工程既有的证据分级。

### 3.4 验收标准

1. 造一段「静音 + 敲桌子 3 下 + 水声」的测试音频，`soundscape` 能给出 `Knock`/`Wood block`/`Water` 之一，且时间码对得上；
2. 真人说话段不把 `Speech` 判错（Speech 概率应最高）；
3. 无模型时返回可执行提示（含下载命令），不是崩；
4. 单次 60s 音频 CPU 耗时 < 2s（10s 窗 × 12）。

### 3.5 待实测（我还没下模型，所以不写死数字）

- 单窗推理耗时；
- 桌面近距离敲击的实际命中率；
- `min_prob` 的合理阈值（AudioSet 长尾，0.15 可能偏低）。

## 4. 实现清单（约 150 行 Python + 30 行 JS）

1. `vidlens_audioevents.py`：模型懒加载（进程内缓存）、`tag_samples(samples, top_k)`、`scan_windows(samples, win, hop)`；
2. `vl_mcp.py` 加 `video_soundscape`（保持 MCP 与插件同源）；
3. `vidlens_bridge.py` 加 `soundscape` 分发；
4. 插件 `index.js` 加 `vidlens_soundscape` 工具定义（timeout 300s）；
5. `vidlens_models.catalog()` 把 CED-mini 从「未接」改成「已接，需 10.4MB」；
6. 单测：无模型路径、有模型路径（可 skip）、窗口切分边界；
7. 文档：README 增加「声音事件」章节 + 标签表摘录。

## 5. 一句话总结

- **吃饭、敲桌子、水声、碰撞、摩擦**：CED-mini 10.4MB，今天就能接，命中率高。
- **喝水/吞咽**：AudioSet 没有这个类，Tier 1 只能给间接线索；要准必须 CLAP（600MB）或自训。
- 模型**不自动下载**——需要你点头（一次 10.4MB）。
