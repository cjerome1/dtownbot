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
import random
import re

# MySQL (optionnel)
try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    Error = Exception

# ------------------ CONFIG ------------------
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

GIVEAWAY_ROLE_ID = 1365805440109117530  # whitelist
GIVEAWAY_CHANNEL_ID = 1421094996899266582

RUN_BOT = os.getenv("RUN_BOT", "0") == "1"
DISABLE_BACKGROUND_TASKS = os.getenv("DISABLE_BACKGROUND_TASKS", "0") == "1"
DISABLE_MYSQL = os.getenv("DISABLE_MYSQL", "1") == "1"

# ------------------ DATABASE ------------------
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
            print("ℹ️ MySQL désactivé ou non installé")
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
            print(f"⚠️ Erreur MySQL: {e}")
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
                            playtime_text = "Données de temps non disponibles"
                    except:
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

# ------------------ BOT ------------------
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
                status_text = "Dev en cours... Ouverture bientôt !"
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
    return any(role.id in ADMIN_ROLE_IDS for role in getattr(interaction.user, 'roles', []))

# ------------------ SLASH COMMANDS ------------------

# /f8 - Bouton cliquable (fix thinking…)
@bot.tree.command(name="f8", description="Connexion automatique au serveur")
async def f8(interaction: discord.Interaction):
    from discord import ui
    fivem_url = f"fivem://connect/{config['server_info']['fivem_ip']}"
    view = ui.View()
    view.add_item(ui.Button(label="▶️ Cliquer pour rejoindre", url=fivem_url))
    embed = discord.Embed(
        title="Connexion F8 - D-TOWN ROLEPLAY",
        description="Clique sur le bouton pour rejoindre automatiquement le serveur !",
        color=int(config['colors']['success'], 16)
    )
    await interaction.response.send_message(embed=embed, view=view)  # envoi direct, pas de defer

# /donation
@bot.tree.command(name="donation", description="Informations pour faire un don")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description=f"Soutenez le serveur par virement Interac: `{config['server_info']['donation_info']}`",
        color=int(config['colors']['primary'], 16)
    )
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

# /playtime
@bot.tree.command(name="playtime", description="Temps de jeu d'un joueur")
async def playtime(interaction: discord.Interaction, joueur: str = ""):
    await interaction.response.defer()
    if not joueur:
        joueur = interaction.user.display_name
    embed = discord.Embed(title=f"Temps de Jeu - {joueur}", color=int(config['colors']['info'], 16))
    if DISABLE_MYSQL:
        embed.add_field(name="Fonctionnalité en Développement", value="Sera disponible à l'ouverture du serveur", inline=False)
    elif bot.db_available:
        player_data = await db_manager.get_player_playtime(joueur)
        if player_data and player_data.get('found'):
            embed.add_field(name="Stats", value=f"Banque: ${player_data['bank_money']}\nLiquide: ${player_data['cash_money']}\nTemps: {player_data['estimated_playtime']}", inline=False)
        else:
            embed.add_field(name="Joueur Introuvable", value="Aucun joueur trouvé avec ce nom", inline=False)
    embed.timestamp = datetime.now()
    await interaction.followup.send(embed=embed)

# /annonce
@bot.tree.command(name="annonce", description="[ADMIN] Envoyer une annonce")
async def annonce(interaction: discord.Interaction, titre: str, message: str):
    if not has_admin_role(interaction):
        await interaction.response.send_message("❌ Accès refusé", ephemeral=True)
        return
    embed = discord.Embed(title=f"📢 {titre}", description=message, color=int(config['colors']['primary'], 16))
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

# /giveaway avec bouton interactif
@bot.tree.command(name="giveaway", description="[ADMIN] Lancer un giveaway")
async def giveaway(interaction: discord.Interaction, prix: str, duree: str):
    if not has_admin_role(interaction):
        await interaction.response.send_message("❌ Accès refusé", ephemeral=True)
        return

    match = re.match(r"^(\d+)([smhd])$", duree)
    if not match:
        await interaction.response.send_message("❌ Durée invalide (ex: 1m, 1h)", ephemeral=True)
        return

    total_seconds = int(match.group(1)) * {'s':1,'m':60,'h':3600,'d':86400}[match.group(2)]
    canal = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if canal is None:
        await interaction.response.send_message("❌ Canal giveaway introuvable", ephemeral=True)
        return

    participants = set()
    from discord import ui, ButtonStyle, Interaction

    class GiveawayButton(ui.View):
        @ui.button(label="🎉 Participer", style=ButtonStyle.primary)
        async def participate(self, button: ui.Button, btn_interaction: Interaction):
            if GIVEAWAY_ROLE_ID not in [r.id for r in btn_interaction.user.roles]:
                await btn_interaction.response.send_message("❌ Tu n'as pas le rôle nécessaire pour participer.", ephemeral=True)
                return
            if btn_interaction.user.id in participants:
                await btn_interaction.response.send_message("✅ Tu es déjà inscrit au giveaway!", ephemeral=True)
                return
            participants.add(btn_interaction.user.id)
            await btn_interaction.response.send_message(f"✅ {btn_interaction.user.display_name}, tu participes au giveaway!", ephemeral=True)

    view = GiveawayButton()
    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"**Lot:** {prix}\n**Durée:** {duree}\nClique sur le bouton pour participer !",
        color=int(config['colors']['primary'], 16)
    )
    giveaway_message = await canal.send(embed=embed, view=view)
    await interaction.response.send_message(f"✅ Giveaway lancé pour {prix} dans {canal.mention}", ephemeral=True)

    await asyncio.sleep(total_seconds)

    if not participants:
        await canal.send("❌ Personne n'a participé au giveaway.")
        return

    winner_id = random.choice(list(participants))
    winner = canal.guild.get_member(winner_id)
    await canal.send(f"🎉 Félicitations {winner.mention}, tu as gagné **{prix}** !")

# ------------------ RUN ------------------
def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ Token Discord manquant!")
        exit(1)
    if not RUN_BOT:
        print("ℹ️ Bot non démarré (RUN_BOT=0)")
        return
    print("🚀 Démarrage D-TOWN ROLEPLAY...")
    bot.run(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    main()
