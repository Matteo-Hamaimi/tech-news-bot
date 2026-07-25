# Tech News Bot

Newsletter tech hebdomadaire personnelle. Tourne une fois par semaine via GitHub Actions, agrège plusieurs sources (GitHub, Hacker News, RSS), et t'envoie par email :

- **Section Faits** : les items retenus, reformulés en français, catégorisés, avec lien source obligatoire à chaque ligne. Zéro invention garantie.
- **Section Point de vue IA** (en bas) : édito de 2-3 paragraphes qui croise l'actu de la semaine avec la mémoire des 12 dernières semaines. Chaque affirmation renvoie explicitement à un item de la section Faits (`[#3]`), pas de fait orphelin.

Une base SQLite versionnée dans le repo mémorise les thèmes et items de chaque semaine, alimente le contexte de l'édito et se cross-référence entre éditions.

## Setup (5 min)

### 1. Fork ou clone

```bash
git clone <ce-repo> tech-news-bot
cd tech-news-bot
```

### 2. Personnalise `profile.md`

Édite ce fichier avec tes projets en cours, intérêts et questions techniques ouvertes. L'IA le lit à chaque run pour connecter l'actu à tes problèmes concrets. C'est ce qui transforme la newsletter en assistant de veille personnalisé.

### 3. Configure les secrets GitHub

Dans **Settings → Secrets and variables → Actions**, ajoute :

| Nom | Valeur |
|---|---|
| `ANTHROPIC_API_KEY` | Clé depuis console.anthropic.com |
| `GMAIL_USER` | Ton adresse Gmail d'envoi (ex: `matteo.newsletter@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Mot de passe d'application (voir ci-dessous) |
| `NEWSLETTER_TO` | Adresse destinataire |
| `GITHUB_TOKEN` | Déjà présent automatiquement dans Actions, rien à faire |

**Gmail App Password** : Compte Google → Sécurité → Validation en 2 étapes activée → Mots de passe d'application → Générer un mot de passe pour "Mail". C'est 16 caractères sans espace.

### 4. Personnalise les topics GitHub

Dans `src/collectors.py`, ajuste la liste `GITHUB_TOPICS` (topics suivis pour les repos qui montent) et `WATCHLIST_REPOS` (repos dont tu veux suivre les releases).

### 5. Test local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # remplis les valeurs
python -m src.main --dry-run  # génère sans envoyer
python -m src.main  # envoie pour de vrai
```

### 6. Planning GitHub Actions

Par défaut : chaque lundi à 8h Paris (07:00 UTC). Modifiable dans `.github/workflows/weekly.yml` (cron standard).

## Coût attendu

Sur Claude Haiku 4.5 (utilisé pour la reformulation) + Sonnet pour l'analyse : entre $0.10 et $0.50 par édition selon volume. GitHub Actions gratuit sur repo public, ~2 min de compute par run sur repo privé (bien en dessous des 2000 min gratuites/mois).

## Structure

```
tech-news-bot/
├── profile.md              # Ton profil et intérêts (l'IA le lit)
├── memory.db               # SQLite persistée (créée au 1er run)
├── src/
│   ├── main.py             # Orchestrateur
│   ├── collectors.py       # GitHub + HN + RSS
│   ├── memory.py           # Persistance SQLite
│   ├── llm.py              # Client Anthropic
│   ├── prompts.py          # Templates de prompts
│   ├── email_send.py       # SMTP Gmail
│   └── template.py         # Rendu HTML de la newsletter
└── .github/workflows/weekly.yml
```

## Itérer sur la personnalité de l'IA

Le prompt de l'édito est dans `src/prompts.py`, fonction `ANALYSIS_SYSTEM`. C'est là que tu calibres le ton, le niveau d'opinion, le style. Les premières éditions sont l'occasion de le raffiner : si l'analyse est trop molle, durcis le ton dans le prompt ; si elle invente, resserre les contraintes de grounding.

La mémoire SQLite (`memory.db`) est committée à chaque run par l'Action GitHub — donc les fils rouges s'accumulent proprement d'une semaine à l'autre.
