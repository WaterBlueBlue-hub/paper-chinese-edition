# 论文中译本

一个用于 Codex 的论文翻译 Skill：将英文论文 PDF 转成中文译本，同时保留原版的公式、插图与版面比例。

## 它解决什么问题

普通 PDF 翻译通常会把双栏论文重排成单栏，破坏公式位置、图表编号和阅读路径。这个 Skill 采用“原文段落 + 裁切公式/插图 + 原版版式重建”的方式：

- 按双栏阅读顺序提取正文段落。
- 公式、插图和算法列表直接从原 PDF 裁切，不重新绘制。
- 译文通过段落 ID 回溯原文，方便校对和避免漏译。
- 用 ReportLab 重建接近原版的页宽、栏宽、字号和页数。
- 内置缺字形检测、段落覆盖和逐页渲染检查。

> 本项目只处理你有权翻译的文档，不附带或分发第三方论文全文。

## 安装

### 作为 Codex Skill

推荐安装到用户级目录：

```powershell
git clone https://github.com/WaterBlueBlue-hub/paper-chinese-edition.git "$HOME\.agents\skills\paper-chinese-edition"
```

安装后重启 Codex，即可通过 `$paper-chinese-edition` 调用。

### Python 环境

每个翻译任务使用单独的虚拟环境：

```powershell
python -m venv ".paper-edition-venv"
& ".paper-edition-venv\Scripts\python.exe" -m pip install -r requirements.txt
```

扫描版 PDF 的 OCR 流程还需要：

```powershell
& ".paper-edition-venv\Scripts\python.exe" -m pip install -r requirements-ocr.txt
```

## 工作流

建议在目标仓库中使用以下目录：

```text
paper-edition-work/<paper-slug>/
  source.pdf
  segments.json
  figs/
  content/
    crop_boxes.py
    part01_*.py
  output.pdf
```

命令示例：

```powershell
$skill = "$HOME\.agents\skills\paper-chinese-edition"
$job = "paper-edition-work/my-paper"
$py = ".paper-edition-venv\Scripts\python.exe"

& $py "$skill\scripts\extract_layout.py" "$job\source.pdf" "$job\segments.json" --debug

& $py "$skill\scripts\make_crops.py" "$job\source.pdf" "$job\figs" "$job\crops.json" --boxes "$job\content\crop_boxes.py" --report

& $py "$skill\scripts\build_pdf.py" "$job\segments.json" "$job\content" "$job\output.pdf" --figs "$job\figs"
```

裁图坐标和译文的编写方式见 `SKILL.md`。更细的双栏判断、字体回退、图版页和数值验收方法见 `references/pitfalls.md`。

## 平台说明

当前排版脚本默认使用 Windows 自带字体：

- `simsun.ttc`
- `simhei.ttf`
- `seguisym.ttf`

在 Linux/macOS 上运行时，需要修改 `scripts/build_pdf.py` 顶部的字体路径，并确保所选字体包含中文和数学符号。

## 目录

```text
SKILL.md                    Codex 工作流说明
agents/openai.yaml          Skill 展示信息
assets/crop_boxes_template.py
references/pitfalls.md      实现细节与已知问题
scripts/                    PDF 提取、裁图、排版和 OCR 工具
```

## 验证

```powershell
python -m py_compile scripts/*.py
```

实际交付前仍需运行 `build_pdf.py` 的字体与裁图检查，并逐页查看 `out_pages/`。
