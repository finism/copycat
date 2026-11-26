"""Package core : logique métier du cloneur de serveurs Discord.

Ce package contient :
    - config.py         : constantes globales (chemins, thème, intents)
    - models.py          : structures de données typées pour l'export/import
    - logger_bridge.py   : pont thread-safe entre le bot (asyncio) et l'UI (Tk)
    - bot_client.py       : encapsulation du client discord.py dans un thread dédié
    - exporter.py         : export d'un serveur Discord vers un fichier JSON
    - importer.py         : import/reconstruction d'un serveur depuis un JSON
"""
