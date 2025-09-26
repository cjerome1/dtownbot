#!/usr/bin/env python3
"""Bot Discord D-TOWN ROLEPLAY - Railway Ready"""

import discord
from discord.ext import commands, tasks
import json
import os
import requests
import asyncio
import re
import random
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

GIVEAWAY_ROLE_ID = 1365805440109117530  # Rôle qui peut participer
GIVEAWAY_CHANNEL_ID = 1421094996899266582  # Panel de giveaway

RUN_BOT = os.getenv("RUN_BOT", "0") == "1"
DISABLE_BACKGROUND_TASKS = os.getenv("DISABLE_BACKGROUND_TASKS", "0") == "1"
DISABLE_MYSQL = os.getenv("DISABLE_MYSQL", "1")  # Temporairement désactivé

# ---------------- DATABASE MANAGER ----------------
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

# ---------------- BOT INIT ----------------
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
                status_text = f"Dev en cours... Ouverture bientôt !"
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
            print(f"Erreur statut serveur: {e}")
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

bot = DTownBot()

def has_admin_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    if not interaction.user.roles:
        return False
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in ADMIN_ROLE_IDS for role_id in user_role_ids)

# ---------------- GIVEAWAY ----------------
active_giveaways = {}  # message_id : asyncio.Task
participants_giveaways = {}  # message_id : list of discord.Member

def parse_duration(duration_str: str) -> int:
    match = re.match(r"^(\d+)([smhd])$", duration_str)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    elif unit == "d":
        return value * 86400
    return None

def format_time(seconds: int) -> str:
    if seconds >= 3600:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}h {m}m {s}s"
    elif seconds >= 60:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s"
    else:
        return f"{seconds}s"

class GiveawayView(discord.ui.View):
    def __init__(self, message_id: int, prix: str):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.prix = prix

    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.success)
    async def participate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if GIVEAWAY_ROLE_ID not in [role.id for role in member.roles]:
            await interaction.response.send_message("❌ Vous n'avez pas le rôle requis pour participer.", ephemeral=True)
            return
        if self.message_id not in participants_giveaways:
            participants_giveaways[self.message_id] = []
        if member in participants_giveaways[self.message_id]:
            await interaction.response.send_message("❌ Vous participez déjà.", ephemeral=True)
            return
        participants_giveaways[self.message_id].append(member)
        await interaction.response.send_message(f"✅ {member.display_name} participe au giveaway !", ephemeral=True)

    @discord.ui.button(label="👥 Participants", style=discord.ButtonStyle.secondary)
    async def participants_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        participants = participants_giveaways.get(self.message_id, [])
        if not participants:
            text = "Aucun participant pour le moment."
        else:
            text = "\n".join([p.display_name for p in participants])
        await interaction.response.send_message(f"**Participants:**\n{text}", ephemeral=True)

async def run_giveaway(canal: discord.TextChannel, prix: str, total_seconds: int):
    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"Réagissez avec le bouton pour participer!\n\n**Lot:** {prix}\n**Temps restant:** {format_time(total_seconds)}",
        color=int(config['colors']['primary'], 16)
    )
    embed.set_footer(text=f"Giveaway lancé par {bot.user.name}")
    message = await canal.send(embed=embed, view=GiveawayView(message_id=0, prix=prix))
    participants_giveaways[message.id] = []

    remaining = total_seconds
    while remaining > 0:
        try:
            msg = await canal.fetch_message(message.id)
            embed = msg.embeds[0]
            embed.description = f"Réagissez avec le bouton pour participer!\n\n**Lot:** {prix}\n**Temps restant:** {format_time(remaining)}"
            await msg.edit(embed=embed)
        except Exception:
            pass
        await asyncio.sleep(5)
        remaining -= 5

    # Fin du giveaway
    msg = await canal.fetch_message(message.id)
    participants = participants_giveaways.get(msg.id, [])
    if not participants:
        await canal.send("❌ Personne n'a participé au giveaway.")
    else:
        winner = random.choice(participants)
        await canal.send(f"🎉 Félicitations {winner.mention} ! Tu as gagné **{prix}** 🎁")

    embed = msg.embeds[0]
    embed.description += "\n\n⏰ Giveaway terminé"
    await msg.edit(embed=embed)
    participants_giveaways.pop(msg.id, None)
    active_giveaways.pop(msg.id, None)

@bot.tree.command(name="giveaway", description="[ADMIN] Lancer un giveaway")
async def giveaway(interaction: discord.Interaction, prix: str, duree: str):
    if not has_admin_role(interaction):
        await interaction.response.send_message(
            embed=discord.Embed(
                title="❌ Accès Refusé",
                description="Commande réservée aux administrateurs.",
                color=int(config['colors']['error'], 16)
            ), ephemeral=True
        )
        return

    total_seconds = parse_duration(duree)
    if total_seconds is None:
        await interaction.response.send_message(
            "❌ Durée invalide. Utilise `1s`, `1m`, `1h` ou `1d`.",
            ephemeral=True
        )
        return

    canal = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if canal is None:
        await interaction.response.send_message("❌ Canal de giveaway introuvable.", ephemeral=True)
        return

    task = asyncio.create_task(run_giveaway(canal, prix, total_seconds))
    active_giveaways[prix] = task

    await interaction.response.send_message(
        embed=discord.Embed(
            title="✅ Giveaway lancé",
            description=f"Giveaway **{prix}** lancé dans {canal.mention} pour `{duree}`.",
            color=int(config['colors']['success'], 16)
        ),
        ephemeral=True
    )

# ---------------- COMMAND /F8 ----------------
@bot.tree.command(name="f8", description="Se connecter directement au serveur FiveM")
async def f8(interaction: discord.Interaction):
    server_ip = "148.113.219.113"
    embed = discord.Embed(
        title="Connexion au serveur",
        description=f"Clique ici pour rejoindre directement le serveur : [Se connecter](fivem://connect/{server_ip})",
        color=int(config['colors']['primary'], 16)
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- FIN BOT ----------------
def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ Token Discord manquant!")
        exit(1)
    
    if not RUN_BOT:
        print("ℹ️ Bot non démarré (RUN_BOT=0)")
        return
    
    try:
        print("🚀 Démarrage D-TOWN ROLEPLAY...")
        print(f"🔒 Tâches fond: {'OFF' if DISABLE_BACKGROUND_TASKS else 'ON'}")
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"❌ Erreur démarrage: {e}")

if __name__ == "__main__":
    main()
