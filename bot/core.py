import textwrap

from discord.ext import commands
from discord import app_commands, Interaction
import discord
import logging

log = logging.getLogger(__name__)
APP_COMMANDS_GUILDS = (
    discord.Object(id=734183623707721874),
    discord.Object(id=911755182889648128),
)


class CoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='help', description="See the commands that this bot has to offer")
    async def help_cmd(self, itx: Interaction):
        title = "Bot Help Commands"

        description = textwrap.dedent(
            """For further help, use /cmd and see the hints that discord provides

            **Available Commands**
            /connect   -- Set your connection settings
            /connections @user -- View someone's connections
        """)
        embed = discord.Embed(title=title, description=description)

        await itx.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name='sync')
    @commands.is_owner()
    async def sync_text(self, ctx: commands.Context):
        await self.bot.tree.sync()
        for o in APP_COMMANDS_GUILDS:
            log.debug(f"Copying Global App Commands to Guild id={o.id}")
            self.bot.tree.copy_global_to(guild=o)
            await self.bot.tree.sync(guild=o)
        await ctx.send("Commands synced", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))