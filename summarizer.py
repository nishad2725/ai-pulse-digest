"""
summarizer.py — LLM-powered categorization and editorial summarization.

Makes a single OpenAI Chat Completions API call (no web search) to:
- Cluster articles into 6 categories
- Write 3-sentence editorial summaries per category
- Identify Top 5 must-read stories with "why it matters" one-liners

Tone: concise, technically sharp, no hype — written for senior AI/ML engineers.
"""

import json
import logging
import os
import re
from datetime import datetime

from openai import OpenAI

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Model Releases",
    "Product Updates",
    "Research & Papers",
    "Funding & Business",
    "Tools & Frameworks",
    "Policy & Safety",
]

SYSTEM_PROMPT = """You are a technical news editor writing a daily digest for senior AI/ML engineers and researchers.

Editorial standards:
- Tone: concise, technically sharp, no marketing fluff, no hype
- Use precise terminology naturally (transformer, RLHF, MoE, LoRA, RAG, etc.)
- Be appropriately skeptical of capability claims — note when benchmarks are cherry-picked
- 3-sentence category summaries must cover: (1) what happened, (2) technical significance, (3) industry impact
- "Why it matters" must be one crisp sentence a staff ML engineer would appreciate
- Do not repeat the same information across different sections
- Return ONLY valid JSON — no prose, no markdown fences, no explanation text"""


def build_digest(articles: list[dict]) -> dict:
    """
    Categorize and summarize articles using GPT-4o.
    Returns a fully populated digest dict ready for email rendering.
    """
    if not articles:
        logger.warning("No articles to summarize — returning empty digest")
        return _empty_digest()

    logger.info(f"Summarizing {len(articles)} articles")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    user_prompt = _build_prompt(articles)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        logger.error(f"OpenAI API error during summarization: {e}")
        raise

    raw_text = response.choices[0].message.content or ""
    structured = _parse_summary_json(raw_text)

    if not structured:
        logger.error("Failed to parse summarizer response — using fallback")
        return _fallback_digest(articles)

    digest = _assemble_digest(articles, structured)
    logger.info(
        f"Digest built: {len(digest['categories'])} categories, "
        f"{len(digest['top_5'])} top stories"
    )
    return digest


def _build_prompt(articles: list[dict]) -> str:
    articles_json = json.dumps(articles, indent=2, ensure_ascii=False)
    categories_list = "\n".join(f"- {c}" for c in CATEGORIES)

    return f"""Here are today's AI news articles (JSON array, 0-based indices):

{articles_json}

Analyze these articles and return a JSON object with this exact structure:
{{
  "categories": [
    {{
      "name": "Category Name",
      "summary": "3-sentence editorial summary covering what happened, technical significance, and industry impact.",
      "article_indices": [0, 3, 7]
    }}
  ],
  "top_5": [
    {{
      "article_index": 0,
      "why_it_matters": "One precise sentence explaining significance for AI/ML engineers."
    }}
  ]
}}

Category names to use (only include a category if at least 1 article belongs to it):
{categories_list}

Rules:
- article_indices are 0-based indices into the input array above
- Each article may appear in at most one category
- top_5 must have exactly 5 entries (or fewer if fewer than 5 articles total)
- top_5 articles must be the most technically significant stories of the day
- top_5 articles may overlap with category article lists
- Return raw JSON only — output will be parsed with json.loads()"""


def _parse_summary_json(raw: str) -> dict | None:
    """Parse JSON from the model's response, stripping any markdown fences."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "categories" in data and "top_5" in data:
            return data
        logger.warning(f"Unexpected summary JSON structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse summary JSON: {e}")
        logger.debug(f"Raw summary text: {text[:500]}")
        return None


def _assemble_digest(articles: list[dict], structured: dict) -> dict:
    """Dereference article indices and assemble the final digest dict."""
    date_str = datetime.now().strftime("%B %-d, %Y")

    categories = []
    for cat in structured.get("categories", []):
        indices = cat.get("article_indices", [])
        cat_articles = []
        for idx in indices:
            if 0 <= idx < len(articles):
                cat_articles.append(articles[idx])
            else:
                logger.warning(f"Category '{cat.get('name')}' has out-of-range index {idx}")
        if cat_articles:
            categories.append({
                "name": cat.get("name", "Uncategorized"),
                "summary": cat.get("summary", ""),
                "articles": cat_articles,
            })

    top_5 = []
    for entry in structured.get("top_5", [])[:5]:
        idx = entry.get("article_index", -1)
        if 0 <= idx < len(articles):
            article = articles[idx].copy()
            article["why_it_matters"] = entry.get("why_it_matters", "")
            top_5.append(article)
        else:
            logger.warning(f"top_5 entry has out-of-range index {idx}")

    return {
        "date": date_str,
        "article_count": len(articles),
        "categories": categories,
        "top_5": top_5,
    }


def _empty_digest() -> dict:
    return {
        "date": datetime.now().strftime("%B %-d, %Y"),
        "article_count": 0,
        "categories": [],
        "top_5": [],
    }


def _fallback_digest(articles: list[dict]) -> dict:
    """Fallback when LLM summarization fails — still sends an email."""
    logger.warning("Using fallback digest — no LLM summarization")
    return {
        "date": datetime.now().strftime("%B %-d, %Y"),
        "article_count": len(articles),
        "categories": [
            {
                "name": "Today's AI News",
                "summary": (
                    f"Today's digest contains {len(articles)} articles covering "
                    "recent developments in AI and machine learning. "
                    "Automated summarization was unavailable for this run."
                ),
                "articles": articles,
            }
        ],
        "top_5": [
            {**a, "why_it_matters": "See article for details."}
            for a in articles[:5]
        ],
    }
