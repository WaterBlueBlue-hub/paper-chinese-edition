---
name: paper-chinese-edition
description: 把英文论文 PDF 做成中文译本：正文译为中文，公式与插图直接从原版裁切，成品版式（开本、双栏、栏宽字号）与英文原版一致。当用户要求翻译某篇论文、做中译本或对照版，且成品要"看起来还是那篇论文"时使用。不适用于导出 Word/Markdown、只要纯文字翻译、或重排成单栏报告的场景。
metadata:
  short-description: 英文论文 → 版式同原版的中文译本
---

# 论文中译本

把一篇英文论文 PDF 做成「中文为主、公式与插图取自原版、版式同原版」的译本。适用于你有权翻译和处理的论文 PDF。

## 产出

- `paper-edition-work/<paper-slug>/output.pdf` —— 成品
- `paper-edition-work/<paper-slug>/` —— 中间产物，可随时删除重跑
  - `segments.json`：按阅读顺序切好的原文段落
  - `figs/*.png`：公式 / 插图 / 算法列表的 300dpi 裁图
  - `crops.json`：每张裁图的坐标与框内文字（自查用）
  - `out_pages/*.png`：成品逐页渲染，供人工校对
- `paper-edition-work/<paper-slug>/content/` —— 译文与裁图坐标，唯一需要人工编写的部分

## 三段流程

脚本在本 Skill 的 `scripts/` 下。建议为每个任务创建独立虚拟环境，并按照仓库根目录的 `requirements.txt` 安装依赖；扫描版 PDF 还需要 `requirements-ocr.txt`。下面的示例使用 Windows PowerShell，其他平台请替换虚拟环境中的 Python 路径。

```powershell
$skill = "$HOME\.agents\skills\paper-chinese-edition"
$job   = "paper-edition-work/<paper-slug>"
$py    = ".paper-edition-venv\Scripts\python.exe"

# 1. 提取：按阅读顺序切段，重建 dvipdfm 丢失的字间空格
& $py "$skill\scripts\extract_layout.py" "$job\source.pdf" "$job\segments.json" --debug

# 2. 裁图：公式、插图、算法列表；--boxes 指向该论文自己的坐标文件
& $py "$skill\scripts\make_crops.py" "$job\source.pdf" "$job\figs" "$job\crops.json" --boxes "$job\content\crop_boxes.py" --report

# 3. 排版：译文 + 裁图 → 成品 PDF
& $py "$skill\scripts\build_pdf.py" "$job\segments.json" "$job\content" "$job\output.pdf" --figs "$job\figs"
```

只改译文时重跑第 3 步即可。辅助脚本 `dump_segments.py`（打印提取结果）、`inspect_page.py`（看某页原始字块）、`render_pages.py`（成品逐页导 PNG）按需使用。

## 需要人工写的两样东西

**裁图坐标** `$job/content/crop_boxes.py`：每个公式、插图、算法列表在原文里的矩形。从 [assets/crop_boxes_template.py](assets/crop_boxes_template.py) 复制，定位方法见：[references/pitfalls.md](references/pitfalls.md)。矩形只要够大能包住目标即可，脚本会自行收紧到墨迹边界；反过来框小了会悄悄切掉内容，所以脚本会逐张报告余量。

**译文** `$job/content/partNN_*.py`：每个文件一个 `BLOCKS` 列表。英文不要重打，按段落 id 引用 `segments.json`，译文因此始终可回溯到原文；参考文献按惯例整条保留原文。

## 交付前必须自查

1. `build_pdf.py` 末尾三行输出：引用的裁图是否齐全、成品文字回捞与源文对比、字形覆盖是否完整。出现 `MISSING GLYPHS` 必须处理（换记法或走符号字体回退），否则成品里是空白框。
2. 段落覆盖：`segments.json` 里每个正文段落都应被某个 BLOCK 引用。未被引用的应当只有公式碎片、算法行、插图区域和参考文献——它们分别由裁图和原文条目覆盖。有正文段落没被引用就是漏译。
3. 交叉引用：正文里提到的图号、式号、小节号都要真实存在，不要给原文没有的小节编号。
4. 渲染 `out_pages/` 逐页看一遍再交付。

## 细节

提取与排版的坑（跨栏判断、小字号回挂、中英混排断行、缺字形回退、宽插图成图版页）、裁图框怎么定、环境怎么重建，都在 [references/pitfalls.md](references/pitfalls.md)。
