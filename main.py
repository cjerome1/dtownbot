#!/usr/bin/env python3
import discord
from discord.ext import commands, tasks
import json, os, requests, asyncio, aiomysql
from datetime import datetime

# ---------------- CONFIG ----------------
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

# ---------------- BOT ----------------
class DTownBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
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
        print(f"✅ Commandes slash synchronisées pour {self.user}")

    async def on_ready(self):
        print(f"🚀 {self.user} connecté ! ID: {self.user.id}")
        if not self.update_status.is_running():
            self.update_status.start()
        await self.check_server_status()

    @tasks.loop(minutes=5)
    async def update_status(self):
        await self.check_server_status()

    async def get_fivem_server_info(self):
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(f"http://{config['server_info']['fivem_ip']}:30120/info.json", timeout=5)
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'online': True,
                    'players': data.get('clients', 0),
                    'max_players': data.get('sv_maxclients', 64),
                    'server_name': data.get('hostname', 'D-TOWN ROLEPLAY')
                }
        except:
            pass
        # fallback
        try:
            reader, writer = await asyncio.open_connection(config['server_info']['fivem_ip'], 30120)
            writer.close()
            await writer.wait_closed()
            return {'online': True, 'players': 0, 'max_players': 64, 'server_name': 'D-TOWN ROLEPLAY'}
        except:
            return {'online': False, 'players': 0, 'max_players': 64, 'server_name': 'D-TOWN ROLEPLAY'}

    async def check_server_status(self):
        if not self.is_ready():
            return
        info = await self.get_fivem_server_info()
        self.server_online = info['online']
        self.player_count = info['players']
        self.max_players = info['max_players']
        status_text = f"🟢 {self.player_count}/{self.max_players} joueurs" if info['online'] else "🔴 Serveur HORS LIGNE"
        try:
            await self.change_presence(
                status=discord.Status.online if info['online'] else discord.Status.idle,
                activity=discord.Activity(type=discord.ActivityType.watching, name=status_text)
            )
        except:
            pass

# ---------------- INIT BOT ----------------
bot = DTownBot()

# ---------------- COMMANDES ----------------

@bot.tree.command(name="regles", description="Affiche les règles")
async def regles(interaction: discord.Interaction):
    rules_channel = bot.get_channel(int(config['server_info']['rules_channel_id']))
    text = f"Consultez toutes les règles dans {rules_channel.mention}" if rules_channel else "Consultez le canal des règles"
    embed = discord.Embed(title="📋 Règles D-TOWN ROLEPLAY", description=text, color=int(config['colors']['info'],16))
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serveur", description="Statut serveur FiveM")
async def serveur(interaction: discord.Interaction):
    await interaction.response.defer()
    info = await bot.get_fivem_server_info()
    online = info['online']
    embed = discord.Embed(
        title="🖥️ Statut du Serveur",
        color=int(config['colors']['success'],16) if online else int(config['colors']['error'],16)
    )
    if online:
        embed.add_field(name="Statut", value="🟢 EN LIGNE")
        embed.add_field(name="Joueurs", value=f"{info['players']}/{info['max_players']}")
        embed.add_field(name="IP", value=f"`{config['server_info']['fivem_ip']}`")
    else:
        embed.add_field(name="Statut", value="🔴 HORS LIGNE")
        embed.add_field(name="Joueurs", value=f"0/{info['max_players']}")
        embed.add_field(name="IP", value=f"`{config['server_info']['fivem_ip']}`")
    embed.timestamp = datetime.now()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="donation", description="Faites un don")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description=f"Email: `{config['server_info']['donation_info']}`",
        color=int(config['colors']['primary'],16)
    )
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="f8connect", description="Commande F8")
async def f8connect(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Connexion F8",
        description=f"`connect {config['server_info']['fivem_ip']}`",
        color=int(config['colors']['success'],16)
    )
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="playtime", description="Temps de jeu d'un joueur")
async def playtime(interaction: discord.Interaction, joueur: str = None):
    await interaction.response.defer()
    joueur = joueur or interaction.user.display_name
    try:
        db = await aiomysql.connect(
            host=config['database']['host'],
            user=config['database']['user'],
            password=config['database']['password'],
            db=config['database']['db'],
            port=int(config['database']['port'])
        )
        async with db.cursor() as cur:
            await cur.execute("SELECT playtime FROM users WHERE identifier=%s LIMIT 1", (joueur,))
            res = await cur.fetchone()
        db.close()
        embed = discord.Embed(
            title=f"🕰️ Playtime - {joueur}",
            description=f"{res[0]} minutes de jeu" if res else "Aucune donnée trouvée",
            color=int(config['colors']['info'],16)
        )
        embed.timestamp = datetime.now()
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Erreur", description=str(e), color=int(config['colors']['error'],16))
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="annonce", description="Annonce pour admins")
async def annonce(interaction: discord.Interaction, message: str):
    member = interaction.guild.get_member(interaction.user.id)
    if not member.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Pas la permission", ephemeral=True)
    embed = discord.Embed(title="📢 Annonce", description=message, color=int(config['colors']['warning'],16))
    embed.timestamp = datetime.now()
    await interaction.response.send_message(f"@everyone", embed=embed)

# ---------------- MENU ----------------
class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    @discord.ui.button(label="📋 Règles", style=discord.ButtonStyle.primary, emoji="📋")
    async def rules(self, interaction, button):
        await regles(interaction)
    @discord.ui.button(label="🖥️ Serveur", style=discord.ButtonStyle.success, emoji="🖥️")
    async def server(self, interaction, button):
        await serveur(interaction)
    @discord.ui.button(label="💵 Donation", style=discord.ButtonStyle.secondary, emoji="💵")
    async def donation_btn(self, interaction, button):
        await donation(interaction)
    @discord.ui.button(label="🕰️ Playtime", style=discord.ButtonStyle.secondary, emoji="🕰️")
    async def playtime_btn(self, interaction, button):
        await playtime(interaction)
    @discord.ui.button(label="🎮 F8 Connect", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def f8_btn(self, interaction, button):
        await f8connect(interaction)

@bot.tree.command(name="menu", description="Menu principal")
async def menu(interaction: discord.Interaction):
    info = await bot.get_fivem_server_info()
    status = f"🟢 {info['players']}/{info['max_players']} joueurs" if info['online'] else "🔴 Hors ligne"
    embed = discord.Embed(title="🏠 D-TOWN ROLEPLAY", description=status, color=int(config['colors']['primary'],16))
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed, view=MenuView())

# ---------------- RUN ----------------
if __name__=="__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token: exit("❌ Token manquant !")
    bot.run(token)
