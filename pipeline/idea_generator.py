"""Generate research ideas from daily recommendations and researcher profile."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from sources.base import BaseSource
from core.config import CommonConfig, EmailConfig, LLMConfig, PROJECT_ROOT
from email_utils.idea_template import render_ideas_email
from llm.GPT import GPT
from llm.Ollama import Ollama

IDEA_EMAIL_TITLE = "Daily Research Ideas"
PUBLICATIONS_SECTION_HEADER = "## Publications"
SCHOLAR_BASE_URL = "https://scholar.google.com"


def fetch_scholar_publications(
    scholar_url: str,
    max_items: int = 20,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    """Fetch publication metadata from a public Google Scholar profile."""
    if not scholar_url:
        raise ValueError("scholar_url is required")

    parsed = urlparse(scholar_url)
    query = parse_qs(parsed.query)
    user_ids = query.get("user", [])
    if not user_ids:
        raise ValueError("Google Scholar URL must include a 'user' query parameter")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        }
    )

    publications: list[dict[str, Any]] = []
    user_id = user_ids[0]
    start = 0

    while len(publications) < max_items:
        page_size = min(100, max_items - len(publications))
        response = session.get(
            f"{SCHOLAR_BASE_URL}/citations",
            params={
                "user": user_id,
                "hl": "en",
                "cstart": start,
                "pagesize": page_size,
            },
            timeout=timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("tr.gsc_a_tr")
        if not rows:
            break

        for row in rows:
            title_node = row.select_one(".gsc_a_at")
            if not title_node:
                continue

            authors_and_venue = row.select(".gs_gray")
            authors = authors_and_venue[0].get_text(" ", strip=True) if authors_and_venue else ""
            venue = authors_and_venue[1].get_text(" ", strip=True) if len(authors_and_venue) > 1 else ""
            year = row.select_one(".gsc_a_y span")
            citation = row.select_one(".gsc_a_c a")
            relative_url = title_node.get("href", "")

            publications.append(
                {
                    "title": title_node.get_text(" ", strip=True),
                    "authors": authors,
                    "venue": venue,
                    "year": year.get_text(strip=True) if year else "",
                    "citations": citation.get_text(strip=True) if citation else "0",
                    "url": urljoin(SCHOLAR_BASE_URL, relative_url) if relative_url else "",
                }
            )
            if len(publications) >= max_items:
                break

        start += len(rows)

    return publications


def update_profile_publications(
    profile_path: str,
    scholar_url: str | list[str],
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Replace the Publications section in the researcher profile markdown file.

    ``scholar_url`` can be a single URL string or a list of URLs.  When
    multiple URLs are provided, publications from all profiles are merged
    (duplicates removed by title) and sorted by citation count.
    """
    urls = scholar_url if isinstance(scholar_url, list) else [scholar_url]
    urls = [u.strip() for u in urls if u and u.strip()]

    all_publications: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for url in urls:
        try:
            pubs = fetch_scholar_publications(url, max_items=max_items)
        except Exception as e:
            print(f"[update_profile_publications] Failed for {url}: {e}")
            continue
        for pub in pubs:
            key = pub.get("title", "").strip().lower()
            if key and key not in seen_titles:
                seen_titles.add(key)
                all_publications.append(pub)

    # Sort merged list by citation count descending
    def _cite_key(p: dict) -> int:
        try:
            return int(p.get("citations", "0"))
        except (TypeError, ValueError):
            return 0

    all_publications.sort(key=_cite_key, reverse=True)
    all_publications = all_publications[:max_items]

    with open(profile_path, "r", encoding="utf-8") as f:
        profile_text = f.read()

    section_lines = [
        PUBLICATIONS_SECTION_HEADER,
        "",
    ]
    for url in urls:
        section_lines.append(f"- **Google Scholar**: {url}")
    section_lines.extend([
        f"- **Last Updated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
    ])
    if all_publications:
        for publication in all_publications:
            meta = " · ".join(
                part
                for part in (
                    publication.get("authors", ""),
                    publication.get("venue", ""),
                    publication.get("year", ""),
                    f"Cited by {publication.get('citations', '0')}",
                )
                if part
            )
            title = publication.get("title", "Untitled")
            url = publication.get("url", "")
            if url:
                section_lines.append(f"- [{title}]({url})")
            else:
                section_lines.append(f"- {title}")
            if meta:
                section_lines.append(f"  - {meta}")
    else:
        section_lines.append("- No publications found from the provided Scholar profile(s).")

    section_text = "\n".join(section_lines).strip() + "\n"
    pattern = rf"{re.escape(PUBLICATIONS_SECTION_HEADER)}.*?(?=\n## |\Z)"
    if not re.search(pattern, profile_text, flags=re.DOTALL):
        raise ValueError(f"Could not find '{PUBLICATIONS_SECTION_HEADER}' in {profile_path}")

    updated_profile = re.sub(pattern, section_text, profile_text, flags=re.DOTALL)
    with open(profile_path, "w", encoding="utf-8") as f:
        f.write(updated_profile)

    return all_publications


class IdeaGenerator:
    def __init__(
        self,
        all_recs: dict[str, list[dict]],
        profile_path: str,
        llm_config: LLMConfig,
        common_config: CommonConfig,
        min_score: float = 7,
        max_items: int = 15,
        idea_count: int = 5,
    ):
        self.all_recs = all_recs
        self.profile_path = profile_path
        self.llm_config = llm_config
        self.common_config = common_config
        self.min_score = min_score
        self.max_items = max_items
        self.idea_count = idea_count

        self.run_datetime = datetime.now(timezone.utc)
        self.run_date = self.run_datetime.strftime("%Y-%m-%d")

        if not os.path.exists(profile_path):
            raise FileNotFoundError(f"Researcher profile not found: {profile_path}")
        with open(profile_path, "r", encoding="utf-8") as f:
            self.profile = f.read()

        self.model = self._build_model(llm_config)

        base_dir = str(PROJECT_ROOT)
        self.save_dir = os.path.join(base_dir, common_config.save_dir, "ideas", self.run_date)
        self.email_cache_path = os.path.join(self.save_dir, "ideas_email.html")
        if common_config.save:
            os.makedirs(self.save_dir, exist_ok=True)

    @staticmethod
    def _build_model(llm_config: LLMConfig):
        provider = llm_config.provider.lower()
        if provider == "ollama":
            return Ollama(llm_config.model)
        if provider in ("openai", "siliconflow"):
            return GPT(llm_config.model, llm_config.base_url, llm_config.api_key)
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _filter_items(self, all_recs: dict[str, list[dict]]) -> list[dict]:
        """Filter high-score items while keeping source diversity."""
        filtered: list[dict] = []
        for source_name, recs in all_recs.items():
            source_items = []
            for rec in recs:
                try:
                    score = float(rec.get("score", 0))
                except (TypeError, ValueError):
                    score = 0
                if score >= self.min_score:
                    source_items.append({**rec, "_source": source_name, "score": score})

            source_items.sort(key=lambda item: item.get("score", 0), reverse=True)
            filtered.extend(source_items)

        if not filtered:
            return []

        by_source: dict[str, list[dict]] = {}
        for item in filtered:
            by_source.setdefault(item["_source"], []).append(item)

        diverse: list[dict] = []
        source_names = sorted(by_source.keys(), key=lambda name: by_source[name][0].get("score", 0), reverse=True)
        index_by_source = {name: 0 for name in source_names}

        while len(diverse) < self.max_items:
            added_any = False
            for source_name in source_names:
                source_index = index_by_source[source_name]
                source_items = by_source[source_name]
                if source_index >= len(source_items):
                    continue
                diverse.append(source_items[source_index])
                index_by_source[source_name] += 1
                added_any = True
                if len(diverse) >= self.max_items:
                    break
            if not added_any:
                break

        return diverse

    def _format_item_for_prompt(self, item: dict) -> str:
        source = item.get("_source", "unknown")
        title = item.get("title", "Untitled")
        summary = item.get("summary", "")
        url = item.get("url", "")
        score = item.get("score", 0)

        detail_parts = []
        for key in ("stars", "stars_today", "upvotes", "likes", "downloads", "retweets"):
            if key in item:
                detail_parts.append(f"{key}={item.get(key)}")
        details = ", ".join(detail_parts)

        if len(summary) > 320:
            summary = summary[:317] + "..."

        line = f"- [{source}] {title} (score={score})"
        if details:
            line += f" [{details}]"
        line += f" — {summary} | URL: {url}"
        return line

    def _build_prompt(self, filtered_items: list[dict]) -> str:
        items_text = "\n".join(self._format_item_for_prompt(item) for item in filtered_items)
        source_names = sorted({item.get("_source", "unknown") for item in filtered_items})
        cross_source_requirement = (
            "每个 idea 至少融合 2 个不同来源。"
            if len(source_names) >= 2
            else "当前只有 1 个来源可用；请尽量在该来源内部做非平庸组合。"
        )

        return f"""你是一位顶级 AI 研究顾问。请基于今日推荐和研究者画像，生成 {self.idea_count} 个可以直接送入 auto-research 流程的研究 idea。

## Part 1: 今日高分推荐内容

{items_text}

## Part 2: 研究者画像

{self.profile}

## 生成要求

1. {cross_source_requirement}
2. 不要写成简单的 “apply X to Y”。每个 idea 都要有明确 hypothesis、最小实验和 novelty estimate。
3. 尽量把 idea 挂钩到研究者已有项目或长期研究方向。
4. 兼顾新颖性、可做性、与研究兴趣的匹配度，排序时用 composite_score 体现。
5. 邮件面向中文阅读，因此 title / hypothesis / min_experiment 用中文；research_direction / hypothesis_en 用英文。
6. research_direction 必须是一句简洁英文，可直接粘贴给 /idea-creator、/idea-discovery 或 /research-pipeline。

## 输出格式

严格输出 JSON 数组，不要加 Markdown 代码块，不要加解释：

[
  {{
    "id": "idea-{self.run_date}-001",
    "title": "中文标题",
    "title_en": "English title",
    "research_direction": "One-line English research direction",
    "hypothesis": "中文假设",
    "hypothesis_en": "English hypothesis",
    "inspired_by": [
      {{"title": "item title", "source": "github", "url": "https://..."}}
    ],
    "connects_to_project": "AI Agents / Open-Source Models / Agent Skills / MCP Servers / none",
    "interest_area": "AI Agents / Open-Source Models / Agent Skills / MCP Servers",
    "novelty_estimate": "HIGH / MEDIUM / LOW",
    "feasibility": "HIGH / MEDIUM / LOW",
    "composite_score": 8.5,
    "min_experiment": "中文最小实验"
  }}
]

请输出 {self.idea_count} 个 idea，按 composite_score 从高到低排列。"""

    @staticmethod
    def _clean_llm_json(raw: str) -> str:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        first_bracket = cleaned.find("[")
        last_bracket = cleaned.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            cleaned = cleaned[first_bracket:last_bracket + 1]

        return cleaned.strip()

    def _normalize_idea(self, idea: dict[str, Any], index: int, filtered_items: list[dict]) -> dict[str, Any]:
        fallback_inspired_by = [
            {
                "title": item.get("title", ""),
                "source": item.get("_source", ""),
                "url": item.get("url", ""),
            }
            for item in filtered_items[:2]
        ]

        inspired_by = []
        for source in idea.get("inspired_by") or []:
            if not isinstance(source, dict):
                continue
            inspired_by.append(
                {
                    "title": str(source.get("title", "")),
                    "source": str(source.get("source", "")),
                    "url": str(source.get("url", "")),
                }
            )

        try:
            composite_score = float(idea.get("composite_score", 0))
        except (TypeError, ValueError):
            composite_score = 0.0

        return {
            "id": idea.get("id") or f"idea-{self.run_date}-{index:03d}",
            "title": str(idea.get("title", f"Research Idea {index}")),
            "title_en": str(idea.get("title_en", "")),
            "research_direction": str(idea.get("research_direction", "")).strip(),
            "hypothesis": str(idea.get("hypothesis", "")).strip(),
            "hypothesis_en": str(idea.get("hypothesis_en", "")).strip(),
            "inspired_by": inspired_by or fallback_inspired_by,
            "connects_to_project": str(idea.get("connects_to_project", "none")),
            "interest_area": str(idea.get("interest_area", "")),
            "novelty_estimate": str(idea.get("novelty_estimate", "MEDIUM")).upper(),
            "feasibility": str(idea.get("feasibility", "MEDIUM")).upper(),
            "composite_score": round(composite_score, 2),
            "min_experiment": str(idea.get("min_experiment", "")).strip(),
        }

    def generate(self) -> list[dict]:
        filtered = self._filter_items(self.all_recs)
        if not filtered:
            print("[IdeaGenerator] No items passed the score filter.")
            return []

        print(f"[IdeaGenerator] {len(filtered)} items passed filter (min_score={self.min_score})")
        prompt = self._build_prompt(filtered)

        print("[IdeaGenerator] Generating research ideas with LLM...")
        raw = self.model.inference(prompt, temperature=self.llm_config.temperature)
        cleaned = self._clean_llm_json(raw)

        try:
            ideas = json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"[IdeaGenerator] Failed to parse LLM response as JSON: {e}")
            print(f"[IdeaGenerator] Raw response (first 500 chars): {cleaned[:500]}")
            return []

        if isinstance(ideas, dict):
            ideas = ideas.get("ideas", [])
        if not isinstance(ideas, list):
            print("[IdeaGenerator] LLM response is not a list.")
            return []

        normalized_ideas = [
            self._normalize_idea(idea, index, filtered)
            for index, idea in enumerate(ideas, 1)
            if isinstance(idea, dict)
        ]
        normalized_ideas.sort(key=lambda item: item.get("composite_score", 0), reverse=True)
        normalized_ideas = normalized_ideas[: self.idea_count]
        print(f"[IdeaGenerator] Generated {len(normalized_ideas)} research ideas.")
        return normalized_ideas

    def render_email(self, ideas: list[dict]) -> str:
        html = render_ideas_email(ideas, self.run_date)
        if self.common_config.save:
            os.makedirs(self.save_dir, exist_ok=True)
            with open(self.email_cache_path, "w", encoding="utf-8") as f:
                f.write(html)
        return html

    def save(self, ideas: list[dict]):
        if not self.common_config.save:
            print("[IdeaGenerator] Save disabled, skipping.")
            return

        os.makedirs(self.save_dir, exist_ok=True)

        json_path = os.path.join(self.save_dir, "ideas.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(ideas, f, ensure_ascii=False, indent=2)
        print(f"[IdeaGenerator] Ideas saved to {json_path}")

        md_path = os.path.join(self.save_dir, "ideas.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Daily Research Ideas\n")
            f.write(f"## Date: {self.run_date}\n\n")
            for index, idea in enumerate(ideas, 1):
                f.write(f"### Idea {index}: {idea.get('title', 'Untitled')}\n")
                f.write(f"- **English Title**: {idea.get('title_en', '')}\n")
                f.write(f"- **Research Direction**: {idea.get('research_direction', '')}\n")
                f.write(f"- **Hypothesis**: {idea.get('hypothesis', '')}\n")
                f.write(f"- **Project**: {idea.get('connects_to_project', 'N/A')}\n")
                f.write(f"- **Area**: {idea.get('interest_area', '')}\n")
                f.write(
                    f"- **Novelty**: {idea.get('novelty_estimate', '')} | "
                    f"**Feasibility**: {idea.get('feasibility', '')}\n"
                )
                f.write(f"- **Composite Score**: {idea.get('composite_score', 0)}\n")
                f.write(f"- **Min Experiment**: {idea.get('min_experiment', '')}\n")
                inspired_by = idea.get("inspired_by", [])
                if inspired_by:
                    f.write("- **Inspired By**:\n")
                    for source in inspired_by:
                        f.write(
                            f"  - [{source.get('source', '')}] "
                            f"[{source.get('title', '')}]({source.get('url', '')})\n"
                        )
                f.write("\n")
        print(f"[IdeaGenerator] Markdown saved to {md_path}")

    def send_email(self, ideas: list[dict], email_config: EmailConfig):
        if not ideas:
            print("[IdeaGenerator] No ideas to send.")
            return

        html = self.render_email(ideas)
        BaseSource._send_email_html(html, email_config, IDEA_EMAIL_TITLE, self.run_datetime)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Idea generator utilities")
    parser.add_argument(
        "--update_profile_publications",
        type=str,
        help="Path to the researcher profile markdown file to update",
    )
    parser.add_argument(
        "--scholar_url",
        type=str,
        nargs="+",
        help="Google Scholar profile URL(s) used to refresh the Publications section",
    )
    parser.add_argument(
        "--max_publications",
        type=int,
        default=20,
        help="Max number of publications to write into the profile",
    )
    return parser


def _main():
    parser = _build_cli_parser()
    args = parser.parse_args()

    if not args.update_profile_publications:
        parser.error("No action specified.")
    if not args.scholar_url:
        parser.error("--scholar_url is required when updating publications.")

    publications = update_profile_publications(
        profile_path=args.update_profile_publications,
        scholar_url=args.scholar_url,
        max_items=args.max_publications,
    )
    print(
        f"Updated {args.update_profile_publications} with "
        f"{len(publications)} publications from Google Scholar."
    )


if __name__ == "__main__":
    _main()
