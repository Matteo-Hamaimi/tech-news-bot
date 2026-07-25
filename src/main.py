"""
Point d'entrée hebdomadaire. Le pipeline :

    collect → dédup 30j → normalize (LLM pass 1) → retenir score≥4
           → analyze (LLM pass 2, avec mémoire)
           → template HTML → SMTP → persister mémoire
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import collectors, email_send, llm, memory, template

load_dotenv()

PROFILE_PATH = Path(__file__).parent.parent / "profile.md"
ARCHIVE_DIR = Path(__file__).parent.parent / "archives"


def main(dry_run: bool = False) -> int:
    week = memory.current_week_iso()
    print(f"=== Newsletter tech — semaine {week} ===")

    # 1. Collecte
    raw_items = collectors.collect_all()
    if not raw_items:
        print("Aucun item collecté, abandon.")
        return 1

    # 2. Dédup inter-semaines
    conn = memory.init()
    seen_ids = memory.already_seen(conn, [it["id"] for it in raw_items])
    fresh = [it for it in raw_items if it["id"] not in seen_ids]
    print(f"Après dédup 30j : {len(fresh)} items frais / {len(raw_items)} bruts")

    if not fresh:
        print("Rien de neuf cette semaine, on skip l'envoi.")
        return 0

    # 3. Normalisation LLM
    print("Normalisation LLM…")
    enriched = llm.normalize_items(fresh)
    retained = [it for it in enriched if it.get("retained")]
    print(f"Retenus après filtre IA : {len(retained)}")

    if len(retained) < 5:
        print("Trop peu d'items retenus, on skip l'envoi cette semaine.")
        memory.save_items(conn, enriched, week)  # on garde trace pour la dédup future
        return 0

    # 4. Analyse LLM avec mémoire
    print("Analyse éditoriale…")
    profile_text = PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else ""
    memory_ctx = memory.load_memory_context(conn, weeks_back=12)
    analysis = llm.write_analysis(retained, memory_ctx, profile_text, week)

    # 5. Extraction des thèmes pour mémoire future
    themes = llm.extract_themes(retained, analysis)
    print(f"Thèmes de la semaine : {themes}")

    # 6. Rendu email
    headline = themes[0] if themes else "Ce qui compte cette semaine"
    subject, html = template.render_email(retained, analysis, week, headline)

    # 7. Envoi (ou dry-run)
    if dry_run:
        ARCHIVE_DIR.mkdir(exist_ok=True)
        out = ARCHIVE_DIR / f"preview-{week}.html"
        out.write_text(html, encoding="utf-8")
        print(f"[DRY-RUN] Aperçu écrit dans {out}")
    else:
        email_send.send(subject, html)

    # 8. Persistance mémoire
    memory.save_items(conn, enriched, week)
    memory.save_digest(conn, week, themes, analysis, len(retained))

    # Archive HTML pour référence hors dry-run aussi
    ARCHIVE_DIR.mkdir(exist_ok=True)
    (ARCHIVE_DIR / f"{week}.html").write_text(html, encoding="utf-8")

    print(f"=== Fait ({len(retained)} items, {len(themes)} thèmes) ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Génère la newsletter sans l'envoyer (aperçu dans archives/)")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
