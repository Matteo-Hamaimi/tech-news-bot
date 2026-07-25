"""
Couche mémoire SQLite. Persiste :
- Les items retenus par édition (pour dédup inter-semaines et cross-reference)
- Les digests hebdo générés par l'IA (thèmes, fils rouges, prédictions)

La base memory.db est committée par l'Action GitHub à chaque run, donc la
mémoire s'accumule proprement d'une semaine à l'autre.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "memory.db"


def init() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT,
            title_fr TEXT,
            summary_fr TEXT,
            score REAL,
            signals_json TEXT,
            week TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            retained INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_digests (
            week TEXT PRIMARY KEY,
            themes_json TEXT NOT NULL,
            analysis_text TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_week ON items(week)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_retained ON items(retained)")
    conn.commit()
    return conn


def current_week_iso() -> str:
    """Utilise le format ISO année-semaine pour un tri lexical propre."""
    today = datetime.now(timezone.utc).date()
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


def already_seen(conn: sqlite3.Connection, item_ids: list[str]) -> set[str]:
    """Retourne l'ensemble des IDs déjà vus dans les 30 derniers jours (dédup inter-semaines)."""
    if not item_ids:
        return set()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    placeholders = ",".join("?" * len(item_ids))
    cur = conn.execute(
        f"SELECT id FROM items WHERE id IN ({placeholders}) AND first_seen > ?",
        [*item_ids, cutoff],
    )
    return {row[0] for row in cur.fetchall()}


def save_items(conn: sqlite3.Connection, items: list[dict[str, Any]], week: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        conn.execute("""
            INSERT OR IGNORE INTO items
                (id, url, title, source, category, title_fr, summary_fr, score,
                 signals_json, week, first_seen, retained)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["id"], item["url"], item["title"], item["source"],
            item.get("category"), item.get("title_fr"), item.get("summary_fr"),
            item.get("score", 0.0), json.dumps(item.get("signals", {})),
            week, now, 1 if item.get("retained") else 0,
        ))
    conn.commit()


def save_digest(conn: sqlite3.Connection, week: str, themes: list[str],
                analysis: str, item_count: int) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO weekly_digests
            (week, themes_json, analysis_text, item_count, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (week, json.dumps(themes), analysis, item_count,
          datetime.now(timezone.utc).isoformat()))
    conn.commit()


def load_memory_context(conn: sqlite3.Connection, weeks_back: int = 12) -> str:
    """
    Retourne un condensé texte des N dernières semaines pour injection dans le
    prompt de l'analyse. Format markdown, chronologique inverse.
    """
    cur = conn.execute("""
        SELECT week, themes_json, analysis_text, item_count
        FROM weekly_digests
        ORDER BY week DESC
        LIMIT ?
    """, (weeks_back,))
    rows = cur.fetchall()

    if not rows:
        return "_(Aucune édition précédente — c'est la première.)_"

    lines = []
    for week, themes_json, analysis, count in rows:
        themes = json.loads(themes_json)
        lines.append(f"### Semaine {week} ({count} items)")
        lines.append(f"**Thèmes** : {', '.join(themes)}")
        # On garde l'analyse mais on peut la tronquer si trop longue
        lines.append(analysis[:600] + ("…" if len(analysis) > 600 else ""))
        lines.append("")

    return "\n".join(lines)
