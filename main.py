#!/usr/bin/env python3
"""
Bot Discord D-TOWN ROLEPLAY
"""

import discord
from discord.ext import commands, tasks
import json
import os
import requests
import asyncio
from datetime import datetime

# Charger la configuration de manière sûre
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

class DTownBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        super().__init__(
            command_prefix=config['bot_settings']['prefix'],
            intents=intents,
            description=config['bot_settings']['description']
        )

        self.server_online = False
        self.player_count = 0
        self.max_players = 64

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Commandes slash synchronisées pour {self.user}")

    async def on_ready(self):
        print(f'{self.user} est connecté!')
        print(f'ID: {self.user.id if self.user else "Inconnu"}')
        print('------')

        if not self.update_status.is_running():
            self.update_status.start()

        await self.check_server_status()

    @tasks.loop(minutes=5)
    async def update_status(self):
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
                    activity=discord.Activity(type=discord.ActivityType.watching, name="🔴 Serveur HORS LIGNE")
                )

        except Exception as e:
            print(f"Erreur lors de la vérification du serveur: {e}")
            self.server_online = False
            try:
                if self.is_ready():
                    await self.change_presence(
                        status=discord.Status.idle,
                        activity=discord.Activity(type=discord.ActivityType.watching, name="🔴 Statut inconnu")
                    )
            except:
                pass

# ===================== BOT =====================
bot = DTownBot()

# ===================== COMMANDES SLASH =====================

# /regles
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
            rules_text = f"Consultez toutes les règles détaillées dans {rules_channel.mention}"
        else:
            rules_text = "Consultez toutes les règles détaillées dans le canal des règles"
        embed.add_field(name="📍 Canal des Règles", value=rules_text, inline=False)
        embed.add_field(name="⚠️ Important", value="Le respect des règles est obligatoire pour tous les membres du serveur.", inline=False)
        embed.set_footer(text="D-TOWN ROLEPLAY • Serveur Communautaire")
        embed.timestamp = datetime.now()
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# /serveur
@bot.tree.command(name="serveur", description="Affiche le statut du serveur FiveM")
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
            embed.add_field(name="🎮 Connexion", value="Utilisez `/f8connect` pour vous connecter", inline=False)
        else:
            embed.add_field(name="🔴 Statut", value="**HORS LIGNE**", inline=True)
            embed.add_field(name="👥 Joueurs", value="**0/64**", inline=True)
            embed.add_field(name="📍 IP", value=f"`{config['server_info']['fivem_ip']}`", inline=True)
            embed.add_field(name="⏰ Info", value="Le serveur sera bientôt de retour", inline=False)
        embed.set_footer(text="Mise à jour automatique toutes les 5 minutes")
        embed.timestamp = datetime.now()
        await interaction.followup.send(embed=embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Erreur",
            description=f"Impossible de vérifier le serveur: {e}",
            color=int(config['colors']['error'], 16)
        )
        await interaction.followup.send(embed=error_embed)

# /donation
@bot.tree.command(name="donation", description="Informations pour faire un don par virement Interac")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description="Soutenez le serveur par virement Interac !",
        color=int(config['colors']['primary'], 16)
    )
    embed.add_field(
        name="💳 Virement Interac",
        value=f"**Email:** `{config['server_info']['donation_info']}`",
        inline=False
    )
    embed.add_field(
        name="📝 Instructions",
        value="1. Ouvrez votre app bancaire\n2. Sélectionnez 'Virement Interac'\n3. Utilisez l'email ci-dessus\n4. Ajoutez votre pseudonyme Discord en note",
        inline=False
    )
    embed.set_footer(text="Merci de soutenir D-TOWN ROLEPLAY !")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

# /f8connect
@bot.tree.command(name="f8connect", description="Informations de connexion F8 pour le serveur")
async def f8connect(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Connexion F8 - D-TOWN ROLEPLAY",
        description="Utilisez cette commande pour vous connecter directement au serveur :",
        color=int(config['colors']['success'], 16)
    )
    embed.add_field(
        name="💻 Commande F8",
        value=f"`connect {config['server_info']['fivem_ip']}`",
        inline=False
    )
    embed.set_footer(text="Bon jeu sur D-TOWN ROLEPLAY !")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

# /playtime
@bot.tree.command(name="playtime", description="Afficher le temps de jeu d'un joueur sur le serveur")
async def playtime(interaction: discord.Interaction, joueur: str = ""):
    await interaction.response.defer()
    if not joueur:
        joueur = interaction.user.display_name
    try:
        server_info = await bot.get_fivem_server_info()
        embed = discord.Embed(
            title=f"🕰️ Temps de Jeu - {joueur}",
            color=int(config['colors']['info'], 16)
        )
        if server_info['online']:
            embed.add_field(
                name="📊 Statistiques",
                value="```\n🔍 Recherche en cours...\n⚠️ Cette fonctionnalité nécessite la base de données du serveur.```",
                inline=False
            )
            embed.add_field(name="🎮 Serveur Actuel", value=f"🟢 **En ligne** - {server_info['players']}/{server_info['max_players']} joueurs", inline=False)
        else:
            embed.add_field(name="⚠️ Serveur Hors Ligne", value="Le serveur FiveM n'est pas accessible actuellement.", inline=False)
        embed.set_footer(text=f"Demande par {interaction.user.display_name} • D-TOWN ROLEPLAY")
        embed.timestamp = datetime.now()
        await interaction.followup.send(embed=embed)
    except:
        error_embed = discord.Embed(title="❌ Erreur", description="Impossible de récupérer les informations de temps de jeu.", color=int(config['colors']['error'], 16))
        await interaction.followup.send(embed=error_embed)

# ===================== MENU BOUTONS =====================
class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="📋 Règles", style=discord.ButtonStyle.primary, emoji="📋")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        rules_channel = bot.get_channel(int(config['server_info']['rules_channel_id']))
        description_text = f"Consultez toutes les règles dans {rules_channel.mention}" if rules_channel else "Consultez toutes les règles dans le canal des règles"
        embed = discord.Embed(title="📋 Règles du Serveur", description=description_text, color=int(config['colors']['info'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🖥️ Serveur", style=discord.ButtonStyle.success, emoji="🖥️")
    async def server_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        server_info = await bot.get_fivem_server_info()
        if server_info['online']:
            status = "🟢 EN LIGNE"
            color = int(config['colors']['success'], 16)
            description = f"**{status}**\n👥 {server_info['players']}/{server_info['max_players']} joueurs\n📍 `{config['server_info']['fivem_ip']}`"
        else:
            status = "🔴 HORS LIGNE"
            color = int(config['colors']['error'], 16)
            description = f"**{status}**\n👥 0/{server_info['max_players']}\n📍 `{config['server_info']['fivem_ip']}`"
        embed = discord.Embed(title="🖥️ Statut du Serveur", description=description, color=color)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="💵 Donation", style=discord.ButtonStyle.secondary, emoji="💵")
    async def donation_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="💵 Donation",
            description=f"**Email:** `{config['server_info']['donation_info']}`\nInstructions: Virement Interac + pseudo Discord",
            color=int(config['colors']['primary'], 16)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🕰️ Playtime", style=discord.ButtonStyle.secondary, emoji="🕰️")
    async def playtime_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🕰️ Temps de Jeu", description="Utilisez `/playtime` pour vos stats de jeu.", color=int(config['colors']['info'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎮 F8 Connect", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def connect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎮 Connexion F8", description=f"`connect {config['server_info']['fivem_ip']}`", color=int(config['colors']['success'], 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="menu", description="Menu principal du serveur")
async def menu(interaction: discord.Interaction):
    server_info = await bot.get_fivem_server_info()
    status_text = f"🟢 {server_info['players']}/{server_info['max_players']} joueurs" if server_info['online'] else "🔴 Hors ligne"
    embed = discord.Embed(
        title="🏠 D-TOWN ROLEPLAY",
        description="**\nBienvenue sur notre serveur !",
        color=int(config['colors']['primary'], 16)
    )
    embed.add_field(name="🎮 Serveur FiveM", value=status_text, inline=True)
    embed.add_field(name="🏆 Type", value="Roleplay", inline=True)
    embed.add_field(name="👥 Communauté", value="Active et bienveillante", inline=True)
    embed.set_footer(text="Utilisez les boutons ci-dessous pour naviguer")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed, view=MenuView())

# ===================== RUN BOT =====================
if __name__ == "__main__":
    token = os.getenv 'MTQxOTcwMDgxNjAyMTAyODkwNg.Giffhc._TN7QVbaoO7VZS7p1DJh7zWIGVvcjhNRTgTVd8'
    if not token:
        print("❌ ERREUR: Token Discord manquant! Définir DISCORD_BOT_TOKEN")
        exit(1)
    try:
        print("🚀 Démarrage du bot D-TOWN ROLEPLAY...")
        bot.run(token)
    except Exception as e:
        print(f"❌ Erreur lors du démarrage: {e}")
