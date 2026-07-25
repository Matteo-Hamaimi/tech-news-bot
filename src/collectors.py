"""
Collecteurs de sources. Chaque fonction retourne une liste de dicts normalisés :

    {
        "source": "github|hn|rss:<nom>",
        "url": "...",
        "title": "...",
        "description": "...",  # court, brut, source-fidèle
        "published_at": "ISO-8601",
        "signals": {...},      # stars, points, tags, etc. — libre
    }

Aucune reformulation ici. La normalisation LLM se fait plus loin dans le pipeline.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

# --- Config à personnaliser ---------------------------------------------------

GITHUB_TOPICS = [
    "llm", "rag", "agents", "mlops", "inference",
    "vector-database", "fine-tuning", "prompt-engineering",
]

WATCHLIST_REPOS = [
    "vllm-project/vllm",
    "langchain-ai/langchain",
    "run-llama/llama_index",
    "huggingface/transformers",
    "ollama/ollama",
    "ggerganov/llama.cpp",
    "anthropics/anthropic-sdk-python",
    # Ajoute les tiens
]

RSS_FEEDS = {
    "hn_frontpage": "https://hnrss.org/frontpage?points=150",
    "mit_tech_review": "https://www.technologyreview.com/feed/",
    "ars_technica": "https://feeds.arstechnica.com/arstechnica/index",
    "biorxiv_bioinfo": "http://connect.biorxiv.org/biorxiv_xml.php?subject=bioinformatics",
    "hf_papers": "https://huggingface.co/papers/rss",
}

HN_ALGOLIA_QUERIES = [
    "llm OR agents OR rag",
    "open source AI",
    "biotech",
]

MAX_PER_SOURCE = 25   # Plafond par source, l'IA filtrera derrière
DAYS_LOOKBACK = 7


# --- Utils --------------------------------------------------------------------

def _stable_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _since_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)).strftime("%Y-%m-%d")


# --- GitHub -------------------------------------------------------------------

def collect_github_repos(token: str) -> list[dict[str, Any]]:
    """Repos qui montent sur les topics suivis, sur les 7 derniers jours."""
    items: list[dict[str, Any]] = []
    since = _since_iso()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        for topic in GITHUB_TOPICS:
            q = f"topic:{topic} pushed:>{since}"
            try:
                r = client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": q, "sort": "stars", "order": "desc", "per_page": 10},
                )
                r.raise_for_status()
                for repo in r.json().get("items", []):
                    items.append({
                        "source": "github",
                        "url": repo["html_url"],
                        "title": repo["full_name"],
                        "description": (repo.get("description") or "").strip(),
                        "published_at": repo["pushed_at"],
                        "signals": {
                            "stars": repo["stargazers_count"],
                            "language": repo.get("language"),
                            "topic": topic,
                            "created_at": repo["created_at"],
                        },
                    })
            except httpx.HTTPError as e:
                print(f"[github topic {topic}] {e}")

    return items[:MAX_PER_SOURCE]


def collect_github_releases(token: str) -> list[dict[str, Any]]:
    """Dernières releases des repos de la watchlist."""
    items: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    with httpx.Client(timeout=20.0, headers=headers) as client:
        for repo in WATCHLIST_REPOS:
            try:
                r = client.get(f"https://api.github.com/repos/{repo}/releases", params={"per_page": 3})
                r.raise_for_status()
                for rel in r.json():
                    published = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
                    if published < cutoff:
                        continue
                    body = (rel.get("body") or "").strip()
                    # On tronque le body — il peut être énorme, l'IA n'a pas besoin de tout
                    body_short = body[:800]
                    items.append({
                        "source": "github",
                        "url": rel["html_url"],
                        "title": f"{repo} — release {rel['tag_name']}",
                        "description": body_short,
                        "published_at": rel["published_at"],
                        "signals": {"prerelease": rel.get("prerelease", False), "repo": repo},
                    })
            except httpx.HTTPError as e:
                print(f"[github releases {repo}] {e}")

    return items


# --- Hacker News (Algolia) ----------------------------------------------------

def collect_hn(_token: str) -> list[dict[str, Any]]:
    """Recherche HN via Algolia — gratuit, pas de clé."""
    items: list[dict[str, Any]] = []
    since = int((datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)).timestamp())

    with httpx.Client(timeout=20.0) as client:
        for q in HN_ALGOLIA_QUERIES:
            try:
                r = client.get(
                    "https://hn.algolia.com/api/v1/search",
                    params={
                        "query": q,
                        "tags": "story",
                        "numericFilters": f"created_at_i>{since},points>50",
                        "hitsPerPage": 10,
                    },
                )
                r.raise_for_status()
                for hit in r.json().get("hits", []):
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
                    items.append({
                        "source": "hn",
                        "url": url,
                        "title": hit.get("title", "").strip(),
                        "description": (hit.get("story_text") or "")[:500],
                        "published_at": hit.get("created_at", ""),
                        "signals": {
                            "points": hit.get("points", 0),
                            "num_comments": hit.get("num_comments", 0),
                            "query": q,
                            "hn_id": hit["objectID"],
                        },
                    })
            except httpx.HTTPError as e:
                print(f"[hn {q}] {e}")

    return items[:MAX_PER_SOURCE]


# --- RSS générique ------------------------------------------------------------

def collect_rss() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)

    for name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                # Best-effort sur la date
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub:
                    dt = datetime(*pub[:6], tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                    published_iso = dt.isoformat()
                else:
                    published_iso = ""

                summary = (entry.get("summary", "") or entry.get("description", ""))[:500]
                # Retire le HTML basique
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()

                items.append({
                    "source": f"rss:{name}",
                    "url": entry.get("link", ""),
                    "title": entry.get("title", "").strip(),
                    "description": summary,
                    "published_at": published_iso,
                    "signals": {"feed": name},
                })
        except Exception as e:
            print(f"[rss {name}] {e}")

    return items


# --- Aggrégation --------------------------------------------------------------

def collect_all() -> list[dict[str, Any]]:
    """Rassemble tout, dédup sur URL."""
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if not gh_token:
        print("WARN: GITHUB_TOKEN vide — les appels GitHub seront rate-limités")

    raw: list[dict[str, Any]] = []
    raw.extend(collect_github_repos(gh_token))
    raw.extend(collect_github_releases(gh_token))
    raw.extend(collect_hn(gh_token))
    raw.extend(collect_rss())

    # Dédup par URL canonique
    seen: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not item.get("url"):
            continue
        item["id"] = _stable_id(item["url"])
        # Si doublon, on garde celui qui a le plus de signal
        if item["id"] in seen:
            existing = seen[item["id"]]
            if _signal_score(item) > _signal_score(existing):
                seen[item["id"]] = item
        else:
            seen[item["id"]] = item

    print(f"Collecté : {len(seen)} items uniques depuis {len(raw)} bruts")
    return list(seen.values())


def _signal_score(item: dict[str, Any]) -> int:
    s = item.get("signals", {})
    return s.get("stars", 0) + s.get("points", 0) * 3
