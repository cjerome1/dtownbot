#!/usr/bin/env python3
"""Bot Discord D-TOWN ROLEPLAY - Railway Ready"""

import discord
from discord.ext import commands, tasks
import json
import os
import requests
import asyncio
from datetime import datetime
from typing import Optional

# Import MySQL seulement si nécessaire
try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    Error = Exception

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
except FileNotFoundError:
    print("❌ ERREUR: Fichier config.json introuvable!")
    exit(1)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))

ADMIN_ROLE_IDS = [
    1342882966686404628, 1342883276066652223, 1372313750224376008,
    1411835985666244688, 1370558513180311582, 1413711444096061510
]

RUN_BOT = os.getenv("RUN_BOT", "0") == "1"
DISABLE_BACKGROUND_TASKS = os.getenv("DISABLE_BACKGROUND_TASKS", "0") == "1"
DISABLE_MYSQL = os.getenv("DISABLE_MYSQL", "1") == "1"  # Temporairement désactivé

class DatabaseManager:
    def __init__(self):
        self.connection_params = {
            'host': MYSQL_HOST,
            'user': MYSQL_USER,
            'password': MYSQL_PASSWORD,
            'database': MYSQL_DATABASE,
            'port': MYSQL_PORT,
            'autocommit': True,
            'charset': 'utf8mb4'
        }

    async def initialize(self):
        if DISABLE_MYSQL or not MYSQL_AVAILABLE:
            if DISABLE_MYSQL:
                print("ℹ️ MySQL désactivé temporairement")
            else:
                print("ℹ️ MySQL non installé")
            return False

        try:
            if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
                print("⚠️ Configuration MySQL incomplète")
                return False

            connection = mysql.connector.connect(**self.connection_params)
            if connection.is_connected():
                print("✅ MySQL connecté")
                connection.close()
                return True
        except Error as e:
            print(f"⚠️ MySQL erreur: {e}")
            return False
        return False

    async def get_player_playtime(self, identifier: str) -> Optional[dict]:
        if DISABLE_MYSQL or not MYSQL_AVAILABLE:
            return None

        if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
            return None

        connection = None
        try:
            connection = mysql.connector.connect(**self.connection_params)
            cursor = connection.cursor(dictionary=True)

            query = """
            SELECT 
                IFNULL(JSON_UNQUOTE(JSON_EXTRACT(accounts, '$.bank')), 0) as bank_money,
                IFNULL(JSON_UNQUOTE(JSON_EXTRACT(accounts, '$.money')), 0) as cash_money,
                last_seen
            FROM users 
            WHERE identifier = %s OR LOWER(name) = LOWER(%s)
            LIMIT 1
            """

            cursor.execute(query, (identifier, identifier))
            result = cursor.fetchone()

            if result:
                bank_money = result['bank_money'] if 'bank_money' in result else '0'
                cash_money = result['cash_money'] if 'cash_money' in result else '0'
                last_seen = result['last_seen'] if 'last_seen' in result else ''

                if last_seen:
                    try:
                        if isinstance(last_seen, str):
                            last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                            time_diff = datetime.now() - last_seen_dt.replace(tzinfo=None)
                            playtime_text = f"{time_diff.days} jours depuis la dernière connexion"
                        else:
                            playtime_text = "Données de temps non disponibles"
                    except ValueError:
                        playtime_text = "Format de date invalide"
                else:
                    playtime_text = "Jamais connecté"

                return {
                    'found': True,
                    'player_name': identifier,
                    'bank_money': str(bank_money),
                    'cash_money': str(cash_money),
                    'last_seen': str(last_seen),
                    'estimated_playtime': playtime_text
                }

            return {'found': False}

        except Error as e:
            print(f"Erreur DB playtime: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                connection.close()

db_manager = DatabaseManager()

class DTownBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix=config['bot_settings']['prefix'],
            intents=intents,
            description=config['bot_settings']['description']
        )

        self.server_online = False
        self.player_count = 0
        self.max_players = 64
        self.db_available = False

    async def setup_hook(self):
        self.db_available = await db_manager.initialize()
        await self.tree.sync()
        print(f"Commandes synchronisées pour {self.user}")

    async def on_ready(self):
        print(f'✅ {self.user} connecté!')
        if DISABLE_MYSQL:
            print('🗄️ MySQL: Temporairement désactivé')
        else:
            print(f'Base de données: {"✅ OK" if self.db_available else "❌ Non disponible"}')

        if not DISABLE_BACKGROUND_TASKS and not self.update_status.is_running():
            self.update_status.start()

        await self.check_server_status()

    @tasks.loop(minutes=5)
    async def update_status(self):
        if not DISABLE_BACKGROUND_TASKS:
            await self.check_server_status()

    async def get_fivem_server_info(self):
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(f"http://{config['server_info']['fivem_ip']}:30120/info.json", timeout=5)
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'online': True,
                    'players': data.get('clients', 0),
                    'max_players': data.get('sv_maxclients', 64),
                    'server_name': data.get('hostname', 'D-TOWN ROLEPLAY')
                }
        except:
            pass

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(config['server_info']['fivem_ip'], 30120),
                timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
            return {'online': True, 'players': 0, 'max_players': 64, 'server_name': 'D-TOWN ROLEPLAY'}
        except:
            return {'online': False, 'players': 0, 'max_players': 64, 'server_name': 'D-TOWN ROLEPLAY'}

    async def check_server_status(self):
        try:
            if not self.is_ready():
                return

            server_info = await self.get_fivem_server_info()
            self.server_online = server_info['online']
            self.player_count = server_info['players']
            self.max_players = server_info['max_players']

            if server_info['online']:
                status_text = f"🟢 {self.player_count}/{self.max_players} joueurs en ville"
                await self.change_presence(
                    status=discord.Status.online,
                    activity=discord.Activity(type=discord.ActivityType.watching, name=status_text)
                )
            else:
                # Description OFF
                status_text = "🔴 OFF"
                await self.change_presence(
                    status=discord.Status.idle,
                    activity=discord.Activity(type=discord.ActivityType.watching, name=status_text)
                )
        except Exception as e:
            print(f"Erreur statut serveur: {e}")
            self.server_online = False

bot = DTownBot()

# … le reste du code (commandes, menu, etc.) reste inchangé
# Copie-colle tes commandes existantes ici, elles fonctionneront avec la desc OFF

def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ Token Discord manquant!")
        print("🔧 Définissez DISCORD_BOT_TOKEN")
        exit(1)

    if not RUN_BOT:
        print("ℹ️ Bot non démarré (RUN_BOT=0)")
        print("🔧 Pour démarrer: RUN_BOT=1")
        return

    try:
        print("🚀 Démarrage D-TOWN ROLEPLAY...")
        print(f"🔒 Tâches fond: {'OFF' if DISABLE_BACKGROUND_TASKS else 'ON'}")
        if DISABLE_MYSQL:
            print("🗄️ MySQL: Temporairement désactivé")
        else:
            print(f"🗄️ MySQL: {'Configuré' if all([MYSQL_HOST, MYSQL_USER]) else 'Non configuré'}")
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"❌ Erreur démarrage: {e}")

if __name__ == "__main__":
