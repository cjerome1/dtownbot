#!/usr/bin/env python3
"""Bot Discord D-TOWN ROLEPLAY - Railway Ready"""

import discord
from discord.ext import commands, tasks
import json
import os
import mysql.connector
from mysql.connector import Error
import requests
import asyncio
from datetime import datetime
from typing import Optional

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
        if DISABLE_MYSQL:
            print("ℹ️ MySQL désactivé temporairement")
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
        if DISABLE_MYSQL:
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
                await self.change_presence(
                    status=discord.Status.idle,
                    activity=discord.Activity(type=discord.ActivityType.watching, name="🔶 Serveur en développement - Ouverture bientôt")
                )
        except Exception as e:
            print(f"Erreur statut serveur: {e}")
            self.server_online = False

bot = DTownBot()

def has_admin_role(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    if not interaction.user.roles:
        return False
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in ADMIN_ROLE_IDS for role_id in user_role_ids)

@bot.tree.command(name="regles", description="Affiche les règles du serveur")
async def regles(interaction: discord.Interaction):
    try:
        rules_channel = bot.get_channel(int(config['server_info']['rules_channel_id']))
        embed = discord.Embed(
            title="📋 Règles du Serveur D-TOWN ROLEPLAY",
            description="Voici les règles officielles de notre serveur :",
            color=int(config['colors']['info'], 16)
        )
        if rules_channel and isinstance(rules_channel, discord.TextChannel):
            rules_text = f"Consultez toutes les règles dans {rules_channel.mention}"
        else:
            rules_text = "Consultez toutes les règles dans le canal des règles"
        embed.add_field(name="📍 Canal des Règles", value=rules_text, inline=False)
        embed.add_field(name="⚠️ Important", value="Le respect des règles est obligatoire.", inline=False)
        embed.set_footer(text="D-TOWN ROLEPLAY")
        embed.timestamp = datetime.now()
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@bot.tree.command(name="serveur", description="Statut du serveur FiveM")
async def serveur(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        server_info = await bot.get_fivem_server_info()
        result = 0 if server_info['online'] else 1
        embed = discord.Embed(
            title="🖥️ Statut du Serveur D-TOWN ROLEPLAY",
            color=int(config['colors']['success'], 16) if result == 0 else int(config['colors']['error'], 16)
        )
        if result == 0:
            embed.add_field(name="🟢 Statut", value="**EN LIGNE**", inline=True)
            embed.add_field(name="👥 Joueurs", value=f"**{server_info['players']}/{server_info['max_players']}**", inline=True)
            embed.add_field(name="📍 IP", value=f"`{config['server_info']['fivem_ip']}`", inline=True)
            embed.add_field(name="🎮 Connexion", value="Utilisez `/f8connect`", inline=False)
        else:
            embed.add_field(name="🔶 Statut", value="**EN DÉVELOPPEMENT**", inline=True)
            embed.add_field(name="👥 Joueurs", value="**0/64**", inline=True)
            embed.add_field(name="📍 IP", value=f"`{config['server_info']['fivem_ip']}`", inline=True)
            embed.add_field(name="📅 Ouverture", value="**Bientôt disponible**", inline=False)
        embed.set_footer(text="Mise à jour toutes les 5 minutes")
        embed.timestamp = datetime.now()
        await interaction.followup.send(embed=embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur",
            description=f"Impossible de vérifier le serveur: {e}",
            color=int(config['colors']['error'], 16)
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="donation", description="Informations pour faire un don")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description="Soutenez le serveur par virement Interac",
        color=int(config['colors']['primary'], 16)
    )
    embed.add_field(
        name="Virement Interac",
        value=f"**Email:** `{config['server_info']['donation_info']}`",
        inline=False
    )
    embed.add_field(
        name="Instructions",
        value="1. App bancaire\n2. Virement Interac\n3. Email ci-dessus\n4. Pseudo Discord en note",
        inline=False
    )
    embed.set_footer(text="Merci de soutenir D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="f8connect", description="Informations de connexion F8")
async def f8connect(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Connexion F8 - D-TOWN ROLEPLAY",
        description="Commande pour vous connecter :",
        color=int(config['colors']['success'], 16)
    )
    embed.add_field(
        name="Commande F8",
        value=f"`connect {config['server_info']['fivem_ip']}`",
        inline=False
    )
    embed.set_footer(text="Bon jeu sur D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="playtime", description="Temps de jeu d'un joueur")
async def playtime(interaction: discord.Interaction, joueur: str = ""):
    await interaction.response.defer()
    
    if not joueur:
        joueur = interaction.user.display_name
    
    try:
        embed = discord.Embed(
            title=f"Temps de Jeu - {joueur}",
            color=int(config['colors']['info'], 16)
        )
        
        if DISABLE_MYSQL:
            embed.add_field(
                name="Fonctionnalité en Développement",
                value="```\nLe système de playtime sera disponible\nlors de l'ouverture du serveur.\n\nRestez connectés pour plus d'infos !\n```",
                inline=False
            )
        elif bot.db_available:
            player_data = await db_manager.get_player_playtime(joueur)
            
            if player_data and player_data.get('found'):
                embed.add_field(
                    name="Statistiques Joueur",
                    value=f"```\nBanque: ${player_data['bank_money']}\nLiquide: ${player_data['cash_money']}\nTemps: {player_data['estimated_playtime']}\n```",
                    inline=False
                )
                embed.add_field(
                    name="Dernière Connexion", 
                    value=f"`{player_data['last_seen']}`",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Joueur Introuvable",
                    value="Aucun joueur trouvé avec ce nom.",
                    inline=False
                )
        else:
            embed.add_field(
                name="Base de Données Indisponible",
                value="```\nConnexion MySQL requise\n```",
                inline=False
            )
        
        server_info = await bot.get_fivem_server_info()
        if server_info['online']:
            embed.add_field(
                name="Serveur", 
                value=f"En ligne - {server_info['players']}/{server_info['max_players']} joueurs", 
                inline=False
            )
        else:
            embed.add_field(
                name="Serveur Hors Ligne", 
                value="Le serveur FiveM n'est pas accessible.", 
                inline=False
            )
            
        embed.set_footer(text=f"Demande par {interaction.user.display_name}")
        embed.timestamp = datetime.now()
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur", 
            description=f"Impossible de récupérer les informations: {e}", 
            color=int(config['colors']['error'], 16)
        )
        await interaction.followup.send(embed=error_embed)

@bot.tree.command(name="annonce", description="[ADMIN] Envoyer une annonce")
async def annonce(
    interaction: discord.Interaction, 
    titre: str, 
    message: str, 
    canal: Optional[discord.TextChannel] = None
):
    if not has_admin_role(interaction):
        embed = discord.Embed(
            title="❌ Accès Refusé",
            description="Commande réservée aux administrateurs.",
            color=int(config['colors']['error'], 16)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if canal is None:
        if isinstance(interaction.channel, discord.TextChannel):
            canal = interaction.channel
        else:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Utilisez cette commande dans un canal textuel ou spécifiez un canal.",
                color=int(config['colors']['error'], 16)
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
    try:
        announcement_embed = discord.Embed(
            title=f"📢 {titre}",
            description=message,
            color=int(config['colors']['primary'], 16)
        )
        announcement_embed.set_footer(
            text=f"Annonce par {interaction.user.display_name}"
        )
        announcement_embed.timestamp = datetime.now()
        
        await canal.send(embed=announcement_embed)
        
        canal_name = getattr(canal, 'mention', f"#{getattr(canal, 'name', 'canal')}")
        success_embed = discord.Embed(
            title="✅ Annonce Envoyée",
            description=f"L'annonce **{titre}** a été envoyée dans {canal_name}",
            color=int(config['colors']['success'], 16)
        )
        await interaction.response.send_message(embed=success_embed, ephemeral=True)
        
        print(f"📢 Annonce: {interaction.user.display_name} -> #{canal.name}: {titre}")
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur",
            description=f"Impossible d'envoyer l'annonce: {e}",
            color=int(config['colors']['error'], 16)
        )
        await interaction.response.send_message(embed=error_embed, ephemeral=True)

class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Règles", style=discord.ButtonStyle.primary)
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules_channel = bot.get_channel(int(config['server_info']['rules_channel_id']))
        description_text = f"Consultez les règles dans {rules_channel.mention}" if rules_channel else "Consultez les règles"
        embed = discord.Embed(title="Règles du Serveur", description=description_text, color=int(config['colors']['info'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Serveur", style=discord.ButtonStyle.success)
    async def server_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_info = await bot.get_fivem_server_info()
        if server_info['online']:
            status = "EN LIGNE"
            color = int(config['colors']['success'], 16)
            description = f"**{status}**\n{server_info['players']}/{server_info['max_players']} joueurs\nIP: `{config['server_info']['fivem_ip']}`"
        else:
            status = "EN DÉVELOPPEMENT"
            color = int(config['colors']['warning'], 16)
            description = f"**{status}**\n0/{server_info['max_players']}\nIP: `{config['server_info']['fivem_ip']}`\nOuverture bientôt"
        embed = discord.Embed(title="Statut du Serveur", description=description, color=color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Donation", style=discord.ButtonStyle.secondary)
    async def donation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Donation",
            description=f"**Email:** `{config['server_info']['donation_info']}`\nVirement Interac + pseudo Discord",
            color=int(config['colors']['primary'], 16)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Playtime", style=discord.ButtonStyle.secondary)
    async def playtime_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Temps de Jeu", description="Utilisez `/playtime` pour vos stats.", color=int(config['colors']['info'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="F8 Connect", style=discord.ButtonStyle.secondary)
    async def connect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Connexion F8", description=f"`connect {config['server_info']['fivem_ip']}`", color=int(config['colors']['success'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="menu", description="Menu principal du serveur")
async def menu(interaction: discord.Interaction):
    server_info = await bot.get_fivem_server_info()
    status_text = f"🟢 {server_info['players']}/{server_info['max_players']} joueurs" if server_info['online'] else "🔴 Hors ligne"
    embed = discord.Embed(
        title="🏠 D-TOWN ROLEPLAY",
        description="Bienvenue sur notre serveur !",
        color=int(config['colors']['primary'], 16)
    )
    embed.add_field(name="🎮 Serveur FiveM", value=status_text, inline=True)
    embed.add_field(name="🏆 Type", value="Roleplay", inline=True)
    embed.add_field(name="👥 Communauté", value="Active", inline=True)
    embed.set_footer(text="Utilisez les boutons ci-dessous")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed, view=MenuView())

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
    main()
