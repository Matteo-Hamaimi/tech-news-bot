"""
Client Anthropic — deux passes :

1. `normalize_items` : passe rapide sur Haiku 4.5, batch de tous les items.
   Reformule en français, catégorise, score, décide de rétention. Contraintes
   strictes anti-hallucination.

2. `write_analysis` : passe éditoriale sur Sonnet 4.6, reçoit les items retenus
   + la mémoire longue (12 dernières semaines). Produit l'édito de bas de page
   avec grounding obligatoire (chaque claim → [#id]).
"""

from __future__ import annotations

import json
import os
from typing import Any

from anthropic import Anthropic

from .prompts import (
    NORMALIZE_SYSTEM,
    build_normalize_user,
    ANALYSIS_SYSTEM,
    build_analysis_user,
    THEMES_SYSTEM,
    build_themes_user,
)

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL_NORMALIZE = "claude-haiku-4-5"
MODEL_ANALYZE = "claude-sonnet-4-6"


def _extract_json(text: str) -> Any:
    """Nettoie les ```json fences éventuels et parse."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.rsplit("```", 1)[0]
    return json.loads(t.strip())


def normalize_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Renvoie les items enrichis avec : category, title_fr, summary_fr, score,
    retained. Ne modifie jamais url/source/id.
    """
    if not items:
        return []

    # On batche par paquets de 20 pour rester dans un contexte confortable
    result: list[dict[str, Any]] = []
    for i in range(0, len(items), 20):
        batch = items[i : i + 20]
        user = build_normalize_user(batch)
        resp = client.messages.create(
            model=MODEL_NORMALIZE,
            max_tokens=4000,
            temperature=0,
            system=NORMALIZE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            enriched = _extract_json(text)
        except json.JSONDecodeError as e:
            print(f"[normalize] JSON invalide, batch skipped: {e}")
            continue

        # Merge par index (le prompt garantit l'ordre)
        by_id = {e["id"]: e for e in enriched if "id" in e}
        for original in batch:
            enrich = by_id.get(original["id"], {})
            merged = {**original, **enrich}
            result.append(merged)

    return result


def write_analysis(retained_items: list[dict[str, Any]], memory_context: str,
                   profile: str, week: str) -> str:
    """Retourne le texte markdown de l'édito de bas de page."""
    user = build_analysis_user(retained_items, memory_context, profile, week)
    resp = client.messages.create(
        model=MODEL_ANALYZE,
        max_tokens=2000,
        temperature=0.4,
        system=ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def extract_themes(retained_items: list[dict[str, Any]], analysis: str) -> list[str]:
    """
    Extrait 3-5 thèmes clés de la semaine, stockés en mémoire pour alimenter
    le contexte des prochaines éditions.
    """
    user = build_themes_user(retained_items, analysis)
    resp = client.messages.create(
        model=MODEL_NORMALIZE,
        max_tokens=500,
        temperature=0,
        system=THEMES_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        data = _extract_json(text)
        return data.get("themes", [])[:5]
    except json.JSONDecodeError:
        return []
