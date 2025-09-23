#!/usr/bin/env python3
import discord
from discord.ext import commands, tasks
import json, os, requests, asyncio, aiomysql
from datetime import datetime

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
        self.db_pool = None

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Commandes slash synchronisées pour {self.user}")

    async def on_ready(self):
        print(f'{self.user} est connecté!')
        if not self.update_status.is_running():
            self.update_status.start()
        await self.connect_db()
        await self.check_server_status()

    @tasks.loop(minutes=5)
    async def update_status(self):
        await self.check_server_status()

    async def connect_db(self):
        db_conf = config.get('database', {})
        try:
            self.db_pool = await aiomysql.create_pool(
                host=db_conf['host'],
                port=db_conf.get('port', 3306),
                user=db_conf['user'],
                password=db_conf['password'],
                db=db_conf['database'],
                autocommit=True
            )
            print("✅ Connecté à la base de données MySQL")
        except Exception as e:
            print(f"❌ Erreur connexion DB: {e}")

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
        if not self.is_ready():
            return
        info = await self.get_fivem_server_info()
        self.server_online = info['online']
        self.player_count = info['players']
        self.max_players = info['max_players']
        status_text = f"🟢 {self.player_count}/{self.max_players} joueurs" if info['online'] else "🔴 Serveur HORS LIGNE"
        await self.change_presence(
            status=discord.Status.online if info['online'] else discord.Status.idle,
            activity=discord.Activity(type=discord.ActivityType.watching, name=status_text)
        )

    async def get_playtime(self, discord_id: int):
        if not self.db_pool:
            return "0h 0m"
        query = "SELECT playtime FROM users WHERE discord=%s"
        async with self.db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (discord_id,))
                result = await cur.fetchone()
                if result:
                    minutes = result[0]
                    hours = minutes // 60
                    mins = minutes % 60
                    return f"{hours}h {mins}m"
        return "0h 0m"

bot = DTownBot()

# ---------------- COMMANDES ----------------
@bot.tree.command(name="regles", description="Affiche les règles du serveur")
async def regles(interaction: discord.Interaction):
    rules_channel = bot.get_channel(1365802245551161424)
    rules_text = f"Consultez toutes les règles dans {rules_channel.mention}" if rules_channel else "Consultez toutes les règles dans le canal des règles"
    embed = discord.Embed(
        title="📋 Règles D-TOWN ROLEPLAY",
        description=rules_text,
        color=int(config['colors']['info'],16)
    )
    embed.set_footer(text="© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serveur", description="Affiche le statut du serveur FiveM")
async def serveur(interaction: discord.Interaction):
    await interaction.response.defer()
    info = await bot.get_fivem_server_info()
    color = int(config['colors']['success'],16) if info['online'] else int(config['colors']['error'],16)
    embed = discord.Embed(title="🖥️ Statut du Serveur", color=color)
    status = "🟢 EN LIGNE" if info['online'] else "🔴 HORS LIGNE"
    players = f"{info['players']}/{info['max_players']}" if info['online'] else f"0/{info['max_players']}"
    embed.add_field(name="Statut", value=status)
    embed.add_field(name="Joueurs", value=players)
    embed.add_field(name="IP", value=f"`{config['server_info']['fivem_ip']}`")
    embed.set_footer(text="© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="donation", description="Informations pour faire un don")
async def donation(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💵 Donation D-TOWN ROLEPLAY",
        description=f"**Email:** `{config['server_info']['donation_info']}`",
        color=int(config['colors']['primary'],16)
    )
    embed.set_footer(text="© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="f8connect", description="Commande F8 pour rejoindre le serveur")
async def f8connect(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Connexion F8",
        description=f"`connect {config['server_info']['fivem_ip']}`",
        color=int(config['colors']['success'],16)
    )
    embed.set_footer(text="© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="playtime", description="Afficher le temps de jeu d'un joueur (auto Discord)")
async def playtime(interaction: discord.Interaction):
    await interaction.response.defer()
    time_str = await bot.get_playtime(interaction.user.id)
    embed = discord.Embed(
        title=f"🕰️ Temps de Jeu - {interaction.user.display_name}",
        description=f"⏱️ {time_str}",
        color=int(config['colors']['info'],16)
    )
    embed.set_footer(text="© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="annonce", description="Envoyer une annonce @everyone (Admin uniquement)")
async def annonce(interaction: discord.Interaction, message: str):
    member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
    if not member or not member.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
    embed = discord.Embed(title="📢 Annonce Officielle", description=message, color=int(config['colors']['warning'],16))
    embed.set_footer(text=f"© CJ Dev • D-TOWN ROLEPLAY")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(f"@everyone", embed=embed)

# ---------------- MENU INTERACTIF ----------------
class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    @discord.ui.button(label="📋 Règles", style=discord.ButtonStyle.primary, emoji="📋")
    async def rules_button(self, interaction, button):
        rules_channel = bot.get_channel(1365802245551161424)
        desc = f"Consultez toutes les règles dans {rules_channel.mention}" if rules_channel else "Consultez le canal des règles"
        embed = discord.Embed(title="📋 Règles", description=desc, color=int(config['colors']['info'],16))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="🖥️ Serveur", style=discord.ButtonStyle.success, emoji="🖥️")
    async def server_button(self, interaction, button):
        info = await bot.get_fivem_server_info()
        status = f"🟢 {info['players']}/{info['max_players']} joueurs" if info['online'] else "🔴 Hors ligne"
        embed = discord.Embed(title="🖥️ Serveur", description=status, color=int(config['colors']['success'],16) if info['online'] else int(config['colors']['error'],16))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="💵 Donation", style=discord.ButtonStyle.secondary, emoji="💵")
    async def donation_button(self, interaction, button):
        embed = discord.Embed(title="💵 Donation", description=f"Email: `{config['server_info']['donation_info']}`", color=int(config['colors']['primary'],16))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="🕰️ Playtime", style=discord.ButtonStyle.secondary, emoji="🕰️")
    async def playtime_button(self, interaction, button):
        time_str = await bot.get_playtime(interaction.user.id)
        embed = discord.Embed(title="🕰️ Playtime", description=f"{time_str}", color=int(config['colors']['info'],16))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @discord.ui.button(label="🎮 F8 Connect", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def connect_button(self, interaction, button):
        embed = discord.Embed(title="🎮 F8 Connect", description=f"`connect {config['server_info']['fivem_ip']}`", color=int(config['colors']['success'],16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="menu", description="Menu principal du serveur")
async def menu(interaction: discord.Interaction):
    info = await bot.get_fivem_server_info()
    status = f"🟢 {info['players']}/{info['max_players']} joueurs" if info['online'] else "🔴 Hors ligne"
    embed = discord.Embed(title="🏠 D-TOWN ROLEPLAY", description="Bienvenue sur notre serveur !", color=int(config['colors']['primary'],16))
    embed.add_field(name="🎮 Serveur", value=status, inline=True)
    embed.add_field(name="🏆 Type", value="Roleplay", inline=True)
    embed.add_field(name="👥 Communauté", value="Active et bienveillante", inline=True)
    embed.set_footer(text="Utilisez les boutons ci-dessous pour naviguer • © CJ Dev")
    embed.timestamp = datetime.now()
    await interaction.response.send_message(embed=embed, view=MenuView())

# ---------------- RUN ----------------
if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ Token manquant!")
        exit(1)
    bot.run(token)
