# DIVINARVIS PORTAL V11 — Render

Cette archive contient un serveur Flask et une **interface de démonstration** `index.html` pour tester le portail. Si tu possèdes déjà ton vrai `index.html` DIVINARVIS, garde-le : il peut remplacer l'interface de démonstration, à condition d'utiliser les routes API ci-dessous.

## Mise en ligne

1. Décompresse le ZIP et place **tous les fichiers à la racine** d'un dépôt GitHub. Vérifie que `server.py`, `index.html`, `requirements.txt`, `render.yaml` sont côte à côte.
2. Dans Render, clique **New > Web Service** (pas Static Site) et connecte ton dépôt GitHub.
3. Choisis `Python 3` et le plan souhaité, puis renseigne :
   - **Build Command :** `pip install -r requirements.txt`
   - **Start Command :** `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 server:app`
   - **Health Check Path :** `/api/health`
4. Ajoute une variable d'environnement `DIVINARVIS_TOKEN` (mot de passe secret fort). Mets le même jeton dans le champ d'accès du portail sur tes appareils. **Ne mets jamais ce jeton dans GitHub ni dans un fichier public.**
5. Déploie et ouvre `https://NOM-DU-SERVICE.onrender.com` (l'adresse réelle apparaît dans Render). Pour vérifier le backend, ouvre `/api/health` : tu dois recevoir du JSON comme `{"ok":true,"service":"DIVINARVIS","version":"11.0"}`.

> Tu peux aussi créer le service via un Blueprint Render en important `render.yaml` depuis GitHub. La configuration inclut la même commande Python.

## Pourquoi la page était blanche

Un **Static Site** Render sert seulement les fichiers HTML/CSS/JS : il **n'exécute pas** `server.py`. Le message `Empty build command; skipping build` prouve seulement qu'aucune commande de build n'était configurée, pas que Flask a démarré. Si tu vois `false` dans une page Web, ce message peut venir de ton frontend ; il n'est pas expliqué par les logs du déploiement à eux seuls.

## API

- `GET /api/health` — santé du serveur (sans jeton)
- `GET /api/sync` ou `/api/portal/sync` — lit la dernière sauvegarde JSON
- `POST /api/sync` ou `/api/portal/sync` — enregistre un objet JSON et le renvoie
- `GET /api/files` — liste les fichiers audio/vidéo/images
- `POST /api/upload` — formulaire `multipart/form-data` avec champ `file`
- `POST /api/delete` — JSON `{ "file": "nom_du_fichier" }`
- `POST /api/youtube` — JSON `{ "url": "https://www.youtube.com/watch?v=..." }`
- `GET /uploads/<nom>` — accès direct au fichier envoyé

Si `DIVINARVIS_TOKEN` est configuré, les routes de l'API (sauf health) nécessitent un en-tête `Authorization: Bearer JETON`. **Attention : les liens `/uploads/` restent publics** et ne sont pas adaptés à des documents confidentiels.

## Stockage et précautions

- Par défaut, `data/sync.json` et `data/uploads/` sont **temporaires sur Render**. Un redémarrage ou déploiement peut les effacer ; la synchronisation fonctionne entre appareils tant que les données du serveur existent.
- Pour conserver les données, attache un **disque persistant à un Web Service payant** monté par exemple sur `/var/data`, puis ajoute `DIVINARVIS_DATA_DIR=/var/data` dans Render. Ou remplace le stockage local par une base de données + un stockage d'objets externe.
- Les fichiers chargés sont limités par défaut à 100 Mo (`MAX_UPLOAD_MB`). Les téléchargements audio YouTube dépendent de YouTube et ne sont pas garantis sur Render. Aucune conversion MP3 n'est forcée : M4A est privilégié, sinon le format audio d'origine est conservé.
- Le portail de démonstration est un outil personnel et non une application publique avec gestion complète de comptes. N'y mets pas de données sensibles.

## Test en local

```bash
pip install -r requirements.txt
python server.py
```

Puis ouvre `http://localhost:10000` et teste `/api/health`.
