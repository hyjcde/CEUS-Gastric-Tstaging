#!/usr/bin/env python3
"""Move bulk figure sections to appendix; keep a small set in project preface."""

from __future__ import annotations

import re
from pathlib import Path

HTML_PATH = Path(__file__).resolve().parents[1] / "docs/mainline/gastric_tstaging_project_logic_white.html"


def extract_section(html: str, section_id: str) -> tuple[str, str]:
    pattern = rf'(      <section id="{re.escape(section_id)}"[^>]*>.*?</section>\n)'
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        raise ValueError(f"section not found: {section_id}")
    return html[: m.start()] + html[m.end() :], m.group(1)


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    if 'id="appendix-figures"' in html:
        print("appendix already present, skip")
        return

    html, results_fig = extract_section(html, "results-figures")
    html, local_results = extract_section(html, "local-results")

    html = re.sub(
        r'\s*<figure>\s*<img src="figures/fig_results_auc_comparison\.png"[\s\S]*?</figure>',
        "",
        html,
        count=1,
    )
    html = html.replace(
        "部分 Poe 示意图尚未生成，本页仅嵌入已有 PNG。",
        "大量病例与示意图见文末附录。",
        1,
    )
    html = html.replace(
        """        </motion>
      </section>""".replace("<motion>", "<div>").replace("</motion>", "</motion>"),
        "",
        1,
    )
    # insert appendix link before end of preface
    html = re.sub(
        r'(id="preface"[^>]*>.*?        </div>\n)(      </section>)',
        r"""\1        <p class="note" style="margin-top:0.75rem;font-size:0.88rem;">
          更多方法示意图、病例面板与完整指标图见文末
          <a href="#appendix-figures">附录 · 结果图库</a>（约 300+ 张，按需浏览）。
        </p>
\2""",
        html,
        count=1,
        flags=re.DOTALL,
    )

    html = re.sub(
        r'        <h3 id="figure-gallery">§7\.2 · 方法学与结果图集.*?</div>\n\n        <div class="card highlight">',
        """        <h3 id="figure-gallery">§7.2 · 方法学与结果图集</h3>
        <p class="note" style="font-size:0.9rem;margin:0 0 1rem;">
          Poe 方法示意图、Workbench 示意与全部病例/指标图已移至文末
          <a href="#appendix-figures">附录 · 结果图库</a>，正文仅保留 §7.1 方法学总图。
        </p>

        <div class="card highlight">""",
        html,
        count=1,
        flags=re.DOTALL,
    )

    html = html.replace(
        """      <a href="#results-figures">结果图专区</a>
      <a href="#local-results">本地结果图库</a>
      <a href="#methodology-fig">方法学架构图</a>
      <a href="#figure-gallery">图集 §7.2</a>""",
        """      <a href="#methodology-fig">方法学架构图</a>
      <hr style="margin:0.75rem 0;border:none;border-top:1px solid var(--border);" />
      <a href="#appendix-figures" style="color:var(--accent);font-weight:600;">附录 · 结果图库</a>
      <a href="#results-figures" style="padding-left:1rem;font-size:0.82rem;">↳ Poe 示意图</a>
      <a href="#local-results" style="padding-left:1rem;font-size:0.82rem;">↳ 病例与指标</a>""",
    )

    results_fig = re.sub(r'<section id="results-figures"', "<section", results_fig, count=1)
    results_fig = results_fig.replace(
        "<h2>结果与方法示意图（Poe · 离线包）</h2>",
        '<h2 id="results-figures">A. 结果与方法示意图（Poe · 离线包）</h2>',
    )
    local_results = re.sub(r'<section id="local-results"', "<section", local_results, count=1)
    local_results = local_results.replace(
        "<h2>本地结果图库（病例示例 + 评估曲线）</h2>",
        '<h2 id="local-results">B. 本地结果图库（病例示例 + 评估曲线）</h2>',
    )

    appendix = f"""      <section id="appendix-figures" class="appendix">
        <h2>附录 · 结果图库</h2>
        <p style="font-size:0.92rem;color:var(--muted);margin-bottom:1.5rem;">
          本附录集中存放 Poe 方法示意图、Agent 病例产物、Grad-CAM、分割对比与 scoreboard 指标图；
          正文「项目说明」与 §7 仅保留少量总览图。目录：
          <code>docs/mainline/figures/results/</code>
        </p>
{results_fig}
{local_results}      </section>

"""

    html = html.replace("      <footer>", appendix + "      <footer>")

    if ".appendix {" not in html:
        css = """
    .appendix {
      margin-top: 3rem;
      padding-top: 2rem;
      border-top: 2px solid var(--border);
    }
    .appendix > h2 {
      font-size: 1.5rem;
      color: var(--text);
      margin-bottom: 0.5rem;
    }
    .appendix section > h2 {
      font-size: 1.15rem;
      color: var(--accent);
      margin: 1.5rem 0 0.75rem;
    }
"""
        html = html.replace(
            "    .exec-summary strong { color: var(--text); }\n  </style>",
            "    .exec-summary strong { color: var(--text); }" + css + "  </style>",
        )

    HTML_PATH.write_text(html, encoding="utf-8")
    print("OK:", HTML_PATH)


if __name__ == "__main__":
    main()
