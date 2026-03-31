#!/usr/bin/env python3

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = ROOT / "docs" / "医学人工智能系统设计-更新版.md"
OUTPUT_DIR = ROOT / "output" / "pdf"
ASSET_DIR = OUTPUT_DIR / "assets"
OUTPUT_TEX = OUTPUT_DIR / "medical-ai-course-design.tex"
COVER_WORDMARK_SOURCE = ROOT / "scripts" / "assets" / "zju-wordmark.png"
COVER_WORDMARK_TARGET = ASSET_DIR / "zju-wordmark.png"
COVER_SEAL_SOURCE = ROOT / "scripts" / "assets" / "zju-seal.png"
COVER_SEAL_TARGET = ASSET_DIR / "zju-seal.png"

BODY_TITLE = "《医学人工智能系统设计》课程项目设计说明"
REPORT_DATE = "2026 年 3 月 31 日"

INLINE_MARKDOWN = MarkdownIt("commonmark")

SVG_FALLBACKS = {
    "system-architecture.svg": "docs/pdf/assets/system-architecture.png",
    "interaction-flow.svg": "docs/pdf/assets/interaction-flow.png",
}


def ensure_output_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    if COVER_WORDMARK_SOURCE.exists():
        shutil.copy2(COVER_WORDMARK_SOURCE, COVER_WORDMARK_TARGET)
    if COVER_SEAL_SOURCE.exists():
        shutil.copy2(COVER_SEAL_SOURCE, COVER_SEAL_TARGET)


def escape_latex_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def escape_url(url: str) -> str:
    return url.replace("\\", "/").replace("%", r"\%").replace("#", r"\#")


def render_inline(text: str) -> str:
    html = INLINE_MARKDOWN.renderInline(preprocess_inline_markdown(text)).strip()
    soup = BeautifulSoup(f"<div>{html}</div>", "html.parser")
    return "".join(render_inline_node(node) for node in soup.div.contents)


def render_inline_node(node: NavigableString | Tag) -> str:
    if isinstance(node, NavigableString):
        return escape_latex_text(str(node))

    children = "".join(render_inline_node(child) for child in node.contents)

    if node.name in {"strong", "b"}:
        return rf"\textbf{{{children}}}"
    if node.name in {"em", "i"}:
        return rf"\emph{{{children}}}"
    if node.name == "code":
        return rf"\inlinecode{{{node.get_text()}}}"
    if node.name == "a":
        href = escape_url(node.get("href", ""))
        return rf"\href{{{href}}}{{{children}}}"
    if node.name == "br":
        return r"\\"

    return children


def sanitize_stem(text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return stem or "asset"


def preprocess_inline_markdown(text: str) -> str:
    placeholders: dict[str, str] = {}

    def protect(pattern: str, content: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = f"@@PLACEHOLDER{len(placeholders)}@@"
            placeholders[key] = match.group(0)
            return key

        return re.sub(pattern, repl, content)

    processed = protect(r"`[^`]+`", text)
    processed = protect(r"\[[^\]]+\]\([^)]+\)", processed)
    processed = re.sub(r"(https?://[^\s]+)", r'<a href="\1">\1</a>', processed)
    processed = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", processed)
    processed = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<em>\1</em>", processed)

    for key, value in placeholders.items():
        processed = processed.replace(key, value)

    return processed


class AssetManager:
    def __init__(self) -> None:
        self._mapping: dict[str, str] = {}
        self._counter = 1

    def prepare_asset(self, src: str) -> str:
        if src in self._mapping:
            return self._mapping[src]

        source = Path(src)
        if not source.is_absolute():
            source = (INPUT_MD.parent / src).resolve()

        if source.suffix.lower() == ".svg":
            rel_git_path = SVG_FALLBACKS.get(source.name)
            if rel_git_path is None:
                raise FileNotFoundError(f"No PNG fallback configured for SVG: {src}")
            data = subprocess.check_output(["git", "show", f"HEAD:{rel_git_path}"], cwd=ROOT)
            suffix = ".png"
            stem = sanitize_stem(source.stem)
        else:
            if not source.exists():
                raise FileNotFoundError(f"Image not found: {src}")
            data = source.read_bytes()
            suffix = source.suffix.lower() or ".png"
            stem = sanitize_stem(source.stem)

        target_name = f"{self._counter:02d}-{stem}{suffix}"
        self._counter += 1
        target = ASSET_DIR / target_name
        target.write_bytes(data)
        rel_path = target.relative_to(OUTPUT_DIR).as_posix()
        self._mapping[src] = rel_path
        return rel_path


def width_ratio(value: str | None) -> str:
    if not value:
        return "0.9"
    value = value.strip()
    if value.endswith("%"):
        return f"{float(value[:-1]) / 100:.2f}"
    return value


def render_image_block(html: str, asset_manager: AssetManager) -> str:
    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")
    if not images:
        return ""

    lines = [r"\begin{figure}[H]", r"\centering"]

    if len(images) == 1:
        image = images[0]
        rel = asset_manager.prepare_asset(image.get("src", ""))
        ratio = width_ratio(image.get("width"))
        lines.append(
            rf"\includegraphics[width={ratio}\linewidth,height=0.78\textheight,keepaspectratio]{{{rel}}}"
        )
    else:
        chunks: list[str] = []
        for image in images:
            rel = asset_manager.prepare_asset(image.get("src", ""))
            ratio = width_ratio(image.get("width"))
            chunks.append(
                "\n".join(
                    [
                        rf"\begin{{minipage}}[t]{{{ratio}\linewidth}}",
                        r"\centering",
                        rf"\includegraphics[width=\linewidth,height=0.78\textheight,keepaspectratio]{{{rel}}}",
                        r"\end{minipage}",
                    ]
                )
            )
        lines.append("\n\\hfill\n".join(chunks))

    lines.extend([r"\end{figure}", ""])
    return "\n".join(lines)


def strip_outer_bold(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**") and stripped.endswith("**") and len(stripped) >= 4:
        return stripped[2:-2].strip()
    return stripped


def heading_command(raw_text: str, markdown_level: int) -> str:
    text = strip_outer_bold(raw_text)
    plain = re.sub(r"[*_`]+", "", text).strip()

    if re.match(r"^\d+\.\d+\.\d+\b", plain):
        command = "subsubsection"
    elif re.match(r"^\d+\.\d+\b", plain):
        command = "subsection"
    elif re.match(r"^\d+\.\s*", plain):
        command = "section"
    else:
        command = {2: "section", 3: "subsection", 4: "subsubsection"}.get(markdown_level, "section")

    return rf"\{command}{{{render_inline(text)}}}"


def render_list(lines: list[str], ordered: bool) -> str:
    env = "enumerate" if ordered else "itemize"
    pattern = r"^\d+\.\s+(.*)$" if ordered else r"^-\s+(.*)$"

    if not ordered and len(lines) == 1:
        match = re.match(pattern, lines[0].strip())
        if match:
            text = match.group(1).strip()
            if text.startswith("项目 GitHub 仓库地址："):
                return render_paragraph([text])

    rendered = [rf"\begin{{{env}}}"]
    for line in lines:
        match = re.match(pattern, line.strip())
        if not match:
            continue
        rendered.append(rf"\item {render_inline(match.group(1).strip())}")
    rendered.extend([rf"\end{{{env}}}", ""])
    return "\n".join(rendered)


def render_ordered_list(items: list[dict[str, list[str] | str]]) -> str:
    rendered = [r"\begin{enumerate}"]
    for item in items:
        rendered.append(rf"\item {render_inline(str(item['text']))}")
        subitems = item["subitems"]
        if subitems:
            rendered.append(r"\begin{itemize}")
            for subitem in subitems:
                rendered.append(rf"\item {render_inline(subitem)}")
            rendered.append(r"\end{itemize}")
    rendered.extend([r"\end{enumerate}", ""])
    return "\n".join(rendered)


def render_paragraph(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return render_inline(text) + "\n"


def next_nonempty_index(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def markdown_to_latex(markdown: str, asset_manager: AssetManager) -> tuple[str, str]:
    lines = markdown.splitlines()
    blocks: list[str] = []
    page_title = BODY_TITLE
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if level == 1:
                page_title = strip_outer_bold(title)
            else:
                blocks.append(heading_command(title, level))
                blocks.append("")
            index += 1
            continue

        if re.fullmatch(r"-{4,}", stripped):
            blocks.extend(
                [
                    r"\vspace{0.4em}",
                    r"\begin{center}\rule{0.35\linewidth}{0.4pt}\end{center}",
                    r"\vspace{0.2em}",
                    "",
                ]
            )
            index += 1
            continue

        if stripped.startswith("<p") and "align=\"center\"" in stripped:
            html_lines = [line]
            index += 1
            while index < len(lines):
                html_lines.append(lines[index])
                if "</p>" in lines[index]:
                    index += 1
                    break
                index += 1
            blocks.append(render_image_block("\n".join(html_lines), asset_manager))
            continue

        if re.match(r"^-\s+", stripped):
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^-\s+(.*)$", current)
                if not match:
                    break

                item_text = match.group(1).strip()
                index += 1

                while index < len(lines):
                    nested = lines[index]
                    nested_stripped = nested.strip()
                    if not nested_stripped:
                        lookahead = next_nonempty_index(lines, index)
                        if lookahead < len(lines) and re.match(r"^-\s+", lines[lookahead].strip()):
                            index = lookahead
                        break
                    if re.match(r"^-\s+", nested_stripped):
                        break
                    if re.match(r"^\d+\.\s+", nested_stripped):
                        break
                    if nested.startswith("  ") or nested.startswith("\t"):
                        item_text += " " + nested_stripped
                        index += 1
                        continue
                    break

                items.append(f"- {item_text}")

                lookahead = next_nonempty_index(lines, index)
                if lookahead < len(lines) and re.match(r"^-\s+", lines[lookahead].strip()):
                    index = lookahead
                    continue
                break

            blocks.append(render_list(items, ordered=False))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            items: list[dict[str, list[str] | str]] = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^\d+\.\s+(.*)$", current)
                if not match:
                    break

                item_text = match.group(1).strip()
                index += 1
                subitems: list[str] = []

                while index < len(lines):
                    nested = lines[index]
                    nested_stripped = nested.strip()
                    if not nested_stripped:
                        break
                    if re.match(r"^\d+\.\s+", nested_stripped):
                        break
                    if re.match(r"^-\s+", nested_stripped):
                        subitems.append(re.sub(r"^-\s+", "", nested_stripped))
                        index += 1
                        continue
                    if nested.startswith("  ") or nested.startswith("\t"):
                        item_text += " " + nested_stripped
                        index += 1
                        continue
                    break

                items.append({"text": item_text, "subitems": subitems})

            blocks.append(render_ordered_list(items))
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            candidate_stripped = candidate.strip()
            if not candidate_stripped:
                break
            if re.match(r"^(#{1,6})\s+", candidate_stripped):
                break
            if re.fullmatch(r"-{4,}", candidate_stripped):
                break
            if candidate_stripped.startswith("<p") and "align=\"center\"" in candidate_stripped:
                break
            if re.match(r"^-\s+", candidate_stripped):
                break
            if re.match(r"^\d+\.\s+", candidate_stripped):
                break
            paragraph_lines.append(candidate)
            index += 1

        blocks.append(render_paragraph(paragraph_lines))

    body = "\n".join(block for block in blocks if block is not None).strip() + "\n"
    return page_title, body


def build_document(page_title: str, body: str) -> str:
    return rf"""\documentclass[UTF8,a4paper,12pt,fontset=none]{{ctexart}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\usepackage{{geometry}}
\usepackage{{graphicx}}
\usepackage{{float}}
\usepackage{{array}}
\usepackage{{enumitem}}
\usepackage{{fancyhdr}}
\usepackage{{titlesec}}
\usepackage{{setspace}}
\usepackage{{caption}}
\usepackage{{hyperref}}
\usepackage{{tikz}}
\IfFileExists{{xurl.sty}}{{\usepackage{{xurl}}}}{{}}

\IfFontExistsTF{{Songti SC}}{{\setCJKmainfont[AutoFakeSlant=0.2]{{Songti SC}}}}{{\setCJKmainfont[AutoFakeSlant=0.2]{{FandolSong-Regular}}}}
\IfFontExistsTF{{PingFang SC}}{{\setCJKsansfont{{PingFang SC}}}}{{\setCJKsansfont{{FandolHei-Regular}}}}
\IfFontExistsTF{{PingFang SC}}{{\setCJKmonofont{{PingFang SC}}}}{{\setCJKmonofont{{FandolFang-Regular}}}}
\IfFontExistsTF{{Menlo}}{{\setmonofont{{Menlo}}}}{{\setmonofont{{Latin Modern Mono}}}}
\IfFontExistsTF{{TeX Gyre Termes}}{{\setmainfont{{TeX Gyre Termes}}}}{{}}

\geometry{{left=2.50cm,right=2.50cm,top=2.40cm,bottom=2.50cm}}
\setlength{{\parindent}}{{2em}}
\setlength{{\parskip}}{{0pt}}
\setstretch{{1.32}}
\setcounter{{secnumdepth}}{{0}}
\setlist[itemize]{{leftmargin=2.4em,itemsep=0.35em,topsep=0.45em,parsep=0pt}}
\setlist[enumerate]{{leftmargin=2.8em,itemsep=0.35em,topsep=0.45em,parsep=0pt}}
\captionsetup{{font=small}}
\graphicspath{{{{assets/}}}}
\raggedbottom
\emergencystretch=2em
\urlstyle{{same}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyfoot[C]{{\thepage}}
\renewcommand{{\headrulewidth}}{{0pt}}
\renewcommand{{\footrulewidth}}{{0pt}}

\titleformat{{\section}}{{\bfseries\zihao{{-3}}}}{{}}{{0pt}}{{}}
\titleformat{{\subsection}}{{\bfseries\zihao{{4}}}}{{}}{{0pt}}{{}}
\titleformat{{\subsubsection}}{{\bfseries\zihao{{-4}}}}{{}}{{0pt}}{{}}
\titlespacing*{{\section}}{{0pt}}{{1.0em}}{{0.55em}}
\titlespacing*{{\subsection}}{{0pt}}{{0.85em}}{{0.4em}}
\titlespacing*{{\subsubsection}}{{0pt}}{{0.75em}}{{0.35em}}

\hypersetup{{
  colorlinks=true,
  linkcolor=black,
  urlcolor=blue,
  pdftitle={{医学人工智能课程设计}},
  pdfauthor={{苏易文, 张崇洋, 廖晨皓}}
}}

\newcommand{{\inlinecode}}[1]{{\texttt{{\detokenize{{#1}}}}}}
\newcommand{{\coverfield}}[1]{{\underline{{\makebox[7.8cm][c]{{#1}}}}}}

\begin{{document}}
\thispagestyle{{empty}}
\null
\begin{{tikzpicture}}[remember picture,overlay]
\node[anchor=north] at ([yshift=-2.85cm]current page.north)
  {{\includegraphics[width=11.2cm]{{assets/zju-wordmark.png}}}};
\node[anchor=north] at ([yshift=-8.38cm]current page.north)
  {{\includegraphics[width=6.4cm]{{assets/zju-seal.png}}}};
\node[anchor=north,font=\fontsize{{38pt}}{{48pt}}\selectfont\bfseries]
  at ([yshift=-15.95cm]current page.north) {{医学人工智能课程设计}};
\node[anchor=north] at ([yshift=-18.95cm]current page.north) {{
  \fontsize{{15.6pt}}{{18.8pt}}\selectfont
  \renewcommand{{\arraystretch}}{{1.85}}
  \begin{{tabular}}{{>{{\raggedleft\arraybackslash}}p{{3.2cm}}>{{\centering\arraybackslash}}p{{8.5cm}}}}
  课程名称： & \coverfield{{医学人工智能}} \\
  姓\hspace{{1em}}名： & \coverfield{{苏易文、张崇洋、廖晨皓}} \\
  学\hspace{{1em}}院： & \coverfield{{计算机科学与技术学院}} \\
  指导教师： & \coverfield{{黄正新}} \\
  报告日期： & \coverfield{{{REPORT_DATE}}} \\
  \end{{tabular}}
}};
\end{{tikzpicture}}

\newpage
\setcounter{{page}}{{2}}
\pagestyle{{fancy}}

\begin{{center}}
{{\bfseries\zihao{{-2}} {escape_latex_text(page_title)}\par}}
\end{{center}}
\vspace{{1.0em}}

{body}
\end{{document}}
"""


def main() -> None:
    ensure_output_dirs()
    markdown = INPUT_MD.read_text(encoding="utf-8")
    asset_manager = AssetManager()
    page_title, body = markdown_to_latex(markdown, asset_manager)
    tex = build_document(page_title, body)
    OUTPUT_TEX.write_text(tex, encoding="utf-8")
    print(OUTPUT_TEX)


if __name__ == "__main__":
    main()
