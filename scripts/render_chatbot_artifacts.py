#!/usr/bin/env python3
"""Render chatbot-first markdown/json artifacts into HTML files.

Outputs:
- history/reports/<date>/report.html
- history/reports/<date>/digest_email.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from email_utils.base_template import framework


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_html(md_text: str) -> str:
    lines = md_text.splitlines()
    parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("# "):
            close_list()
            parts.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            close_list()
            parts.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            close_list()
            parts.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(stripped[2:])}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(re.sub(r'^\\d+\\.\\s+', '', stripped))}</li>")
        else:
            close_list()
            parts.append(f"<p>{_inline(stripped)}</p>")
    close_list()
    style = """
    <style>
      body { font-family: Arial, sans-serif; color: #1f2937; }
      h1 { font-size: 30px; margin: 0 0 18px 0; color: #0f172a; }
      h2 { font-size: 22px; margin: 24px 0 12px 0; color: #111827; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }
      h3 { font-size: 18px; margin: 18px 0 10px 0; color: #1f2937; }
      p { line-height: 1.75; margin: 10px 0; }
      ul { margin: 10px 0 10px 22px; padding: 0; }
      li { line-height: 1.75; margin: 8px 0; }
      code { background: #f3f4f6; padding: 1px 5px; border-radius: 4px; }
      .page { max-width: 920px; margin: 0 auto; }
    </style>
    """
    return framework.replace("__CONTENT__", f"{style}<div class='page'>{''.join(parts)}</div>")


def parse_digest_markdown(md_text: str) -> list[dict]:
    items: list[dict] = []
    current: dict | None = None
    for raw in md_text.splitlines():
        line = raw.strip()
        if line.startswith("### "):
            if current:
                items.append(current)
            current = {"title": re.sub(r"^\d+\.\s+", "", line[4:].strip())}
        elif current and line.startswith("- **"):
            m = re.match(r"- \*\*(.+?)\*\*\s*(.*)", line)
            if m:
                key = m.group(1).strip().rstrip(":").lower().replace(" ", "_")
                current[key] = m.group(2).strip()
    if current:
        items.append(current)
    return items


def render_digest_email(date_str: str, source_items: dict[str, list[dict]]) -> str:
    sections: list[str] = [
        f"""
        <div style="font-family:Arial,sans-serif;margin-bottom:26px;">
          <div style="font-size:28px;font-weight:800;color:#0f172a;">Daily Paper Digest</div>
          <div style="margin-top:8px;font-size:15px;line-height:1.7;color:#475569;">
            日期：{html.escape(date_str)} · 模式：chatbot-first
          </div>
        </div>
        """
    ]
    colors = {"huggingface": "#ff6f00", "arxiv": "#b31b1b"}
    labels = {"huggingface": "Hugging Face", "arxiv": "arXiv"}
    for source_name, items in source_items.items():
        color = colors.get(source_name, "#334155")
        label = labels.get(source_name, source_name)
        blocks: list[str] = []
        for item in items[:6]:
            title = html.escape(item.get("title", "Untitled"))
            summary = html.escape(item.get("summary", ""))
            why = html.escape(item.get("why_it_matters", item.get("why_it_matters", "")))
            relevance = html.escape(item.get("relevance", ""))
            signal = html.escape(item.get("signal", ""))
            url = html.escape(item.get("url", ""))
            meta = " · ".join(part for part in [relevance, signal] if part)
            blocks.append(
                f"""
                <div style="padding:18px 20px;border:1px solid #e5e7eb;border-radius:14px;background:#fff;margin:14px 0;">
                  <div style="font-size:17px;font-weight:700;color:#0f172a;">
                    <a href="{url}" style="color:#0f172a;text-decoration:none;">{title}</a>
                  </div>
                  <div style="margin-top:6px;font-size:12px;color:#6b7280;">{meta}</div>
                  <div style="margin-top:10px;font-size:14px;line-height:1.75;color:#334155;">{summary}</div>
                  <div style="margin-top:10px;font-size:14px;line-height:1.75;color:#475569;"><strong>Why it matters:</strong> {why}</div>
                </div>
                """
            )
        sections.append(
            f"""
            <div style="margin-top:22px;">
              <div style="font-size:22px;font-weight:800;color:{color};border-bottom:2px solid {color};padding-bottom:8px;">
                {label}
              </div>
              {''.join(blocks)}
            </div>
            """
        )
    return framework.replace("__CONTENT__", "".join(sections))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    repo_root = REPO_ROOT
    report_md = repo_root / "history" / "reports" / args.date / "report.md"
    report_html = repo_root / "history" / "reports" / args.date / "report.html"
    digest_html = repo_root / "history" / "reports" / args.date / "digest_email.html"

    if report_md.exists():
        _write(report_html, markdown_to_html(_read(report_md)))

    source_items: dict[str, list[dict]] = {}
    for source_name in ("huggingface", "arxiv"):
        path = repo_root / "history" / source_name / args.date / f"{args.date}.md"
        if path.exists():
            source_items[source_name] = parse_digest_markdown(_read(path))

    if source_items:
        _write(digest_html, render_digest_email(args.date, source_items))

    print(f"report_html={report_html.exists()} {report_html}")
    print(f"digest_html={digest_html.exists()} {digest_html}")


if __name__ == "__main__":
    main()
