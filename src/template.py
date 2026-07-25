"""Rendu HTML de la newsletter. Deux sections : Faits (haut) + Point de vue IA (bas)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from jinja2 import Template

CATEGORY_LABELS = {
    "ai-ml": "IA & Machine Learning",
    "opensource": "Open Source & Tooling",
    "systems": "Systèmes & Infra",
    "security": "Sécurité",
    "biotech": "Biotech & Sciences",
    "hardware": "Hardware & Chips",
    "other-tech": "Autre",
}

CATEGORY_ORDER = ["ai-ml", "opensource", "systems", "security", "hardware", "biotech", "other-tech"]

HTML = """\
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{{ subject }}</title>
</head>
<body style="margin:0;padding:0;background:#f6f6f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1a1a1a;">
<div style="max-width:640px;margin:0 auto;padding:32px 20px;background:#ffffff;">

  <div style="border-bottom:2px solid #1a1a1a;padding-bottom:12px;margin-bottom:24px;">
    <div style="font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#888;">Newsletter tech · {{ week }}</div>
    <h1 style="font-size:26px;margin:6px 0 0;font-weight:700;">{{ headline }}</h1>
    <div style="font-size:13px;color:#666;margin-top:4px;">{{ item_count }} items retenus · {{ source_count }} sources</div>
  </div>

  <!-- ===================== SECTION FAITS ===================== -->
  <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:8px;">Les faits</div>

  {% for category, items in grouped %}
  <h2 style="font-size:16px;margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #e5e5e5;">{{ category }}</h2>
  {% for item in items %}
  <div style="margin-bottom:16px;">
    <a href="{{ item.url }}" style="color:#1a1a1a;text-decoration:none;font-weight:600;font-size:15px;line-height:1.35;">
      {{ item.title_fr or item.title }}
    </a>
    <div style="font-size:11px;color:#999;margin:2px 0 4px;">
      <span style="font-family:ui-monospace,SFMono-Regular,monospace;background:#f0f0ee;padding:1px 5px;border-radius:3px;">#{{ item.id }}</span>
      · {{ item.source_label }}
    </div>
    {% if item.summary_fr %}
    <div style="font-size:13px;color:#444;line-height:1.5;">{{ item.summary_fr }}</div>
    {% endif %}
  </div>
  {% endfor %}
  {% endfor %}

  <!-- ===================== SECTION ANALYSE ===================== -->
  <div style="margin-top:48px;padding:24px;background:#faf9f5;border-left:3px solid #1a1a1a;">
    <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:12px;">Point de vue IA · mémoire de l'année</div>
    <div style="font-size:14px;line-height:1.65;color:#1a1a1a;">
      {{ analysis_html | safe }}
    </div>
  </div>

  <div style="margin-top:40px;padding-top:20px;border-top:1px solid #e5e5e5;font-size:11px;color:#888;text-align:center;">
    Newsletter générée automatiquement · {{ generated_at }}<br>
    Section « Point de vue IA » = éditorial, opinions marquées. Section « Faits » = 100% sourcée.
  </div>

</div>
</body>
</html>
"""


def _resolve_refs(analysis_md: str, item_index: dict[str, dict[str, Any]]) -> str:
    """Transforme les [#id] en liens vers la source, souligne les orphelins."""
    def replace(m: re.Match) -> str:
        ref_id = m.group(1)
        item = item_index.get(ref_id)
        if item:
            return (f'<a href="{item["url"]}" style="color:#0055aa;text-decoration:none;'
                    f'font-family:ui-monospace,SFMono-Regular,monospace;font-size:12px;">'
                    f'[#{ref_id}]</a>')
        # Orphelin — signale visuellement pour audit
        return (f'<span style="background:#ffe0e0;padding:0 3px;font-family:ui-monospace,monospace;'
                f'font-size:12px;color:#a00;" title="Référence non trouvée">[#{ref_id}?]</span>')

    return re.sub(r"\[#([a-f0-9]+)\]", replace, analysis_md)


def _markdown_to_html(md: str) -> str:
    """Micro-conversion markdown → HTML (paragraphes + gras). Assez pour l'édito."""
    md = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", md)
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    return "\n".join(f"<p style='margin:0 0 14px;'>{p}</p>" for p in paragraphs)


def render_email(items: list[dict[str, Any]], analysis: str,
                 week: str, headline: str) -> tuple[str, str]:
    """Retourne (subject, html)."""
    # Grouper par catégorie
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        cat = it.get("category", "other-tech")
        if cat == "skip":
            continue
        it["source_label"] = _source_label(it["source"])
        by_cat[cat].append(it)

    grouped = []
    for cat in CATEGORY_ORDER:
        if by_cat.get(cat):
            # Tri par score desc dans chaque catégorie
            sorted_items = sorted(by_cat[cat], key=lambda x: x.get("score", 0), reverse=True)
            grouped.append((CATEGORY_LABELS[cat], sorted_items))

    item_index = {it["id"]: it for it in items}
    analysis_with_refs = _resolve_refs(analysis, item_index)
    analysis_html = _markdown_to_html(analysis_with_refs)

    source_count = len({it["source"].split(":")[0] for it in items})

    html = Template(HTML).render(
        subject=f"Newsletter tech — {week} — {headline}",
        headline=headline,
        week=week,
        grouped=grouped,
        item_count=len(items),
        source_count=source_count,
        analysis_html=analysis_html,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    subject = f"[Newsletter tech · {week}] {headline}"
    return subject, html


def _source_label(source: str) -> str:
    if source == "github":
        return "GitHub"
    if source == "hn":
        return "Hacker News"
    if source.startswith("rss:"):
        return source[4:].replace("_", " ").title()
    return source
