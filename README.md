# Copycat — Discord Server Cloner

Application Windows (Python 3.12 + CustomTkinter) permettant de cloner
intégralement un serveur Discord vers un autre à l'aide d'un bot.

## Télécharger

**[DiscordServerCloner.exe](https://github.com/finism/copycat/releases/latest)** : application Windows prête à lancer, rien à installer. Windows peut afficher un avertissement SmartScreen (exécutable non signé) : « Informations complémentaires » puis « Exécuter quand même ».

Pour lancer depuis le code source, voir [Installation](#installation).

## ⚠️ Prérequis important

Le bot doit être **invité sur les deux serveurs** (source et cible) avec la
permission **Administrateur** (ou au minimum : gérer les rôles, gérer les
salons, gérer les émojis). Sans ces droits, l'export/import échouera
partiellement.

Créez un bot sur https://discord.com/developers/applications, activez
l'intent **Server Members Intent**, et copiez le token dans l'application.

## Installation

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Vider un serveur déjà configuré

La commande « vider la cible » (colonne de gauche, en rouge) supprime **tous** les rôles (hors `@everyone` et rôles
gérés par une intégration/bot), tous les salons/catégories, et tous les
émojis du serveur sélectionné comme cible — pratique pour réutiliser un
serveur existant sans avoir à en recréer un vide à chaque test.

Cette action est **irréversible** : elle demande une confirmation, puis de
retaper exactement le nom du serveur cible pour valider, afin d'éviter un
clic malheureux sur le mauvais serveur.

## Se souvenir du token

Cochez « se souvenir du token » avant de vous connecter :
il sera réutilisé automatiquement au prochain lancement. Il est stocké **en
clair** dans un fichier `.copycat_token` à la racine du projet — ne le
partagez jamais et ne le committez pas dans un dépôt Git. Décochez la case
et reconnectez-vous pour l'oublier.

## Lancement

```bash
python app.py
```

## Utilisation

1. Collez le token du bot et cliquez sur **connecter** (ou Entrée). Les
   serveurs du bot sont listés automatiquement ; **actualiser la liste**
   les recharge. Le même bouton sert ensuite à **déconnecter**.
2. Choisissez le serveur **source** puis **exporter la source** :
   un fichier JSON est enregistré (par défaut dans `backups/`).
3. Choisissez le serveur **cible**, **importer vers la cible**, sélectionnez
   le JSON exporté, confirmez.
4. Suivez la progression et les erreurs dans le journal (boutons
   **copier** / **effacer** en haut à droite).

## Ce qui est exporté / importé

- Nom du serveur
- Icône du serveur
- Bannière du serveur (nécessite un niveau de boost suffisant côté cible pour être appliquée)
- Rôles (nom, couleur, permissions, hiérarchie, hoist, mentionable)
- Catégories (position, overwrites de permissions par rôle)
- Salons texte (topic, slowmode, NSFW, position, overwrites)
- Salons vocaux (bitrate, limite d'utilisateurs, position, overwrites)
- Forums (topic, NSFW, slowmode par défaut)
- Salons de conférence / Stages (topic)
- Émojis personnalisés (image encodée en base64)

**Non inclus** (volontairement, car non pertinent pour un clonage) : les
messages, membres, invitations, webhooks, et les overwrites de permissions
spécifiques à un membre (seuls les overwrites par rôle sont conservés).

## Compilation en .exe (PyInstaller)

```bash
pip install pyinstaller
pyinstaller build.spec
```

L'exécutable est généré dans `dist/DiscordServerCloner.exe`. L'icône
`assets/icon.ico` est embarquée automatiquement.

## Architecture

```
app.py                 # Point d'entrée
core/
  config.py             # Constantes (chemins, version, throttle)
  models.py              # Structures de données typées (export/import)
  logger_bridge.py       # Pont thread-safe bot <-> UI
  bot_client.py           # Client discord.py dans un thread dédié
  exporter.py             # Export serveur -> JSON
  importer.py             # Import JSON -> serveur
  cleaner.py              # Vidage complet d'un serveur
  token_store.py          # Sauvegarde locale du token
ui/
  theme.py                # Palette console (vert phosphore) + styles de widgets
  main_window.py           # Fenêtre principale CustomTkinter
assets/                    # Icônes / ressources statiques
assets_backup/             # Ancienne icône violette (non embarquée)
backups/                   # Exports JSON par défaut
build.spec                  # Configuration PyInstaller
requirements.txt
```

## Limitations connues

- Les rate limits Discord peuvent ralentir les imports sur de gros serveurs
  (un délai est appliqué entre chaque création d'objet).
- Les overwrites de permissions liés à des **membres** spécifiques ne sont
  pas conservés (seuls les rôles le sont).
- Les tags de forums, threads existants et messages ne sont pas clonés.
