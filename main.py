#!/usr/bin/env python3
import discord
from discord.ext import commands, tasks
import json, os, requests, asyncio
from datetime import datetime
from typing import Optional

try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    Error = Exception

# Chargement config
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
except FileNotFoundError:
    print("❌ config.json introuvable")
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
DISABLE_MYSQL = os.getenv("DISABLE_MYSQL", "1") == "1"

# Gestion DB
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
            return False
        try:
            if not all([MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE]):
                return False
            connection = mysql.connector.connect(**self.connection_params)
            if connection.is_connected():
                connection.close()
                return True
        except Error as e:
            print(f"⚠️ Erreur MySQL: {e}")
            return False
        return False

    async def get_player_playtime(self, identifier: str) -> Optional[dict]:
        if DISABLE_MYSQL or not MYSQL_AVAILABLE:
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
                bank_money = result.get('bank_money', '0')
                cash_money = result.get('cash_money', '0')
                last_seen = result.get('last_seen', '')
                if last_seen:
                    try:
                        if isinstance(last_seen, str):
                            last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                            time_diff = datetime.now() - last_seen_dt.replace(tzinfo=None)
                            playtime_text = f"{time_diff.days} jours depuis la dernière connexion"
                        else:
                            playtime_text = "non disponible"
                    except:
                        playtime_text = "invalide"
                else:
                    playtime_text = "jamais connecté"
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
            print(f"Erreur DB: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                connection.close()

db_manager = DatabaseManager()

# Bot principal
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
        print(f"✅ Commandes synchronisées pour {self.user}")

    async def on_ready(self):
        print(f"🚀 {self.user} connecté")
        if not DISABLE_BACKGROUND_TASKS:
            if not self.update_status.is_running():
                self.update_status.start()
            if not self.send_f8_hourly.is_running():
                self.send_f8_hourly.start()
        await self.update_status_once()

    @tasks.loop(minutes=5)
    async def update_status(self):
        if not DISABLE_BACKGROUND_TASKS:
            await self.update_status_once()

    async def update_status_once(self):
        try:
            server_info = await self.get_fivem_server_info()
            self.server_online = server_info['online']
            self.player_count = server_info['players']
            self.max_players = server_info['max_players']

            if server_info['online']:
                status_text = "🟢 Serveur ouvert en Free Access"
                await self.change_presence(
                    status=discord.Status.online,
                    activity=discord.Activity(type=discord.ActivityType.watching, name=status_text)
                )
            else:
                await self.change_presence(
                    status=discord.Status.idle,
                    activity=discord.Activity(type=discord.ActivityType.watching, name="🔶 Serveur OFF")
                )
        except Exception as e:
            print(f"Erreur statut: {e}")
            self.server_online = False

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

    # Tâche automatique F8 toutes les heures
    @tasks.loop(hours=1)
    async def send_f8_hourly(self):
        channel_id = 1365802556957134858
        channel = self.get_channel(channel_id)
        if channel:
            fivem_ip = config['server_info']['fivem_ip']
            embed = discord.Embed(
                title="Connexion F8 - D-TOWN ROLEPLAY",
                description=f"Ouvre FiveM, appuie sur **F8**, et tape :\n\n`connect {fivem_ip}`",
                color=int(config['colors']['success'], 16)
            )
            embed.set_footer(text="Depuis ton client FiveM")
            await channel.send(embed=embed)

bot = DTownBot()

def has_admin_role(interaction: discord.Interaction) -> bool:
    return any(role.id in ADMIN_ROLE_IDS for role in getattr(interaction.user, 'roles', []))

# Commandes
@bot.tree.command(name="f8", description="Connexion auto au serveur")
async def f8(interaction: discord.Interaction):
    fivem_ip = config['server_info']['fivem_ip']
    embed = discord.Embed(
        title="Connexion F8 - D-TOWN ROLEPLAY",
        description=f"Ouvre FiveM, appuie sur **F8**, et tape :\n\n`connect {fivem_ip}`",
        color=int(config['colors']['success'], 16)
    )
    embed.set_footer(text="Depuis ton client FiveM")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="donation", description="Infos donation")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description=f"Soutenez le serveur par virement Interac: `{config['server_info']['donation_info']}`",
        color=int(config['colors']['primary'], 16)
    )
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="annonce", description="[ADMIN] Envoyer une annonce")
async def annonce(interaction: discord.Interaction, titre: str, message: str):
    if not has_admin_role(interaction):
        await interaction.response.send_message("❌ Accès refusé", ephemeral=True)
        return
    embed = discord.Embed(title=f"📢 {titre}", description=message, color=int(config['colors']['primary'], 16))
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

# Lancement
def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ Token Discord manquant")
        exit(1)
    if not RUN_BOT:
        print("ℹ️ Bot désactivé (RUN_BOT=0)")
        return
    bot.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
