# Daily Tech & AI Brief (Python)

Génère et envoie une newsletter HTML avec les actus Tech/IA depuis des flux RSS, sans service externe.

## Setup rapide
1. Créer un repo public sur GitHub et pousser ces fichiers.
2. Aller dans Settings → Secrets and variables → Actions et créer deux secrets :
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
3. Onglet Actions → lancer le workflow manuellement (Run workflow) pour tester.
4. Le cron s'exécutera ensuite tous les jours.

## Personnalisation
- Modifie `feeds.yaml` pour tes sources.
- `LOOKBACK_HOURS` et `MAX_ITEMS` via `.env` (optionnel).
- Template HTML dans `templates/email_template.html`.

## Local (optionnel)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.env .env
# activer TELEGRAM et renseigner token/chat_id
python main.py
```
