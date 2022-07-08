import asyncio
from copy import copy
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Optional, Callable, Any, Dict, List

import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui

from bot.social.provider_cog import ProviderCog, Provider, ProviderTaskService
import logging

from mixins.config import ConfigMixin
from services import establish_member_config, string_timedelta

log = logging.getLogger(__name__)

class SubscriberCog(ConfigMixin, commands.GroupCog, name='subscriber-display'):
    autocomplete_func = None

    def __init__(self, bot: commands.Bot, provider_cog: ProviderCog):
        self.bot = bot
        self.provider_cog = provider_cog
        self.channel: Optional[discord.TextChannel] = None
        self.tasks: Dict[str, asyncio.Task] = {}  # Composite key guild_id + member_id + provider_name
        self.provider_choices = [pd.name
            for pd in self.provider_cog.provider_definitions
        ]
        self.autocomplete_func = self.provider_name_autocomplete

        super(SubscriberCog, self).__init__()
        self.first_run = True
        #self.start_services()

    @commands.Cog.listener()
    async def on_ready(self):
        if self.first_run:
            self.start_services()
            self.first_run = False

    def find_task_key(self, task: asyncio.Task):
        for key, t in self.tasks.items():
            if t == task:
                return key

    def provider_factory(self, member: discord.Member, name: str):
        return self.provider_cog.find_provider_instance_by_member_and_name(member, name)
    def start_services(self):
        for guild_str in self.config_settings.keys():
            guild = self.bot.get_guild(int(guild_str))
            if guild is None:
                continue
            for member_str in self.config_settings[guild_str].keys():
                member = guild.get_member(int(member_str))
                if member is None:
                    continue
                provider_names = self.config_settings[guild_str][member_str]['provider_settings'].keys()
                for name in list(provider_names)[:2]:
                    interval = string_timedelta(self.config_settings[guild_str][member_str]['provider_settings'][name]['interval'])
                    provider = self.provider_cog.find_provider_instance_by_member_and_name(member, name)
                    factory = partial(self.provider_factory, member=member, name=name)
                    if provider is not None:
                        self.start_provider_service(guild_str, member_str, name, factory, interval)

    def start_provider_service(self, guild_id: str, member_id: str, name: str, factory: Callable, interval: timedelta):
        composite_key = f"{guild_id}{member_id}{name}"
        if composite_key in self.tasks:
            task = self.tasks[composite_key]
            if task is not None:
                log.debug("Cancelling Task")
                task.cancel()
        pts = ProviderTaskService(name, factory, self.task_callback, interval)
        task = pts.start()
        self.tasks[composite_key] = task
        log.debug(f"Provider Service Task started for {member_id}")


    def establish_config(self, guild_id: str, member_id: str):
        establish_member_config(self.config_settings, guild_id, member_id)
        if len(self.config_settings[guild_id][member_id].keys()) == 0:
            self.config_settings[guild_id][member_id]['provider_settings'] = {}

    async def provider_name_autocomplete(self, itx: Interaction, current: str) -> List[app_commands.Choice[str]]:
        choices = [
            app_commands.Choice(name=name, value=name)
            for name in self.provider_choices
            if current.lower() in name.lower()
        ]

        return choices

    @app_commands.command()
    async def config(self, itx: Interaction, provider_name: str):
        try:

            current_config = self.config_settings[str(itx.guild_id)][str(itx.user.id)]['provider_settings'][provider_name]
        except KeyError:
            current_config = {}
        await itx.response.send_modal(SubscriberConfigModal(provider_name, self.modal_callback, current_config))

    def make_embed(self, count: int, settings) -> discord.Embed:
        embed = discord.Embed(description=settings['text'].format(count=count))
        embed.set_image(url=settings['banner_url'])
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    async def update_embed(self, member: discord.Member, embed:  discord.Embed, settings):
        channel_id = int(settings['channel_id'])
        message_id = settings['message_id'] and int(settings['message_id'])
        channel = member.guild.get_channel(channel_id)
        new_message = False
        message = None
        if channel is None:
            log.warning(f"{channel_id} on Guild {member.guild.name} No longer available")
            return
        try:

            if message_id is not None:
                log.debug(f"Editing partial message for {settings['message_id']}")
                partial_message = channel.get_partial_message(message_id)
                message = await partial_message.edit(embed=embed)
            else:
                log.debug("Sending new message")
                message = await channel.send(embed=embed)
                new_message = True
        except discord.NotFound:
            message = await channel.send(embed=embed)
            new_message = True
        except discord.Forbidden as e:
            log.error(f"Coud not send message to {channel.name} in Guild {member.guild.name} No Permissions {e}")

        return message, new_message

    async def task_callback(self, provider_name: str, provider: Provider):
        log.debug(f"In task callback for {provider_name}")
        for guild_str in self.config_settings.keys():
            guild = self.bot.get_guild(int(guild_str))
            if guild is None:
                continue
            for member_str in self.config_settings[guild_str].keys():
                member = guild.get_member(int(member_str))
                if member is None:
                    continue
                log.debug(f"Found member {member}")
                settings = self.config_settings[guild_str][member_str]['provider_settings'].get(provider_name)
                if settings is not None:
                    try:
                        count = await provider.subscriber_count()
                        embed = self.make_embed(count, settings)
                        message, new_message = await self.update_embed(member, embed, settings)
                        if message is not None and new_message:
                            settings = self.config_settings[guild_str][member_str]['provider_settings'][provider_name]['message_id'] = message.id
                            self.save_settings()
                    except KeyError as e:
                        log.error(f"KeyError on subscription settings: {settings}: {e}")
        log.debug("Task callback finished")

    async def modal_callback(self, itx: Interaction, provider_name: str, payload: Dict[str, Any]):
        guild_str = str(itx.guild_id)
        member_str = str(itx.user.id)
        log.debug(payload)
        channel = itx.guild.get_channel(int(payload['channel_id']))
        interval = string_timedelta(payload['interval'])
        if interval is None:
            await itx.followup.send("Interval not valid format. ex: 1d2h3m4s. Changes not saved.", ephemeral=True)
            return
        if channel is None:
            await itx.followup.send("Channel not found. Changes not saved.", ephemeral=True)
            return

        self.establish_config(guild_str, member_str)
        if provider_name not in self.config_settings[guild_str][member_str]['provider_settings'].keys():
            self.config_settings[guild_str][member_str]['provider_settings'][provider_name] = {}
        if len(self.config_settings[guild_str][member_str]['provider_settings'][provider_name].keys()) >= 1:
            self.config_settings[guild_str][member_str]['provider_settings'][provider_name].update(payload)
        else:
            payload.update({'message_id': None})
            self.config_settings[guild_str][member_str]['provider_settings'][provider_name] = payload
        self.save_settings()
        provider = self.provider_cog.find_provider_instance_by_member_and_name(itx.user, provider_name)
        if provider is not None:

            self.start_provider_service(guild_str, member_str, provider_name, provider, interval)
        else:
            log.error(f"Could not start provider service {provider_name} for {itx.user.name} in {itx.guild.name}")
        await itx.followup.send(f"Settings for {provider_name} saved.", ephemeral=True)


async def setup(bot: commands.Bot):
    provider_cog = bot.get_cog('provider')
    if provider_cog is not None:
        await bot.add_cog(SubscriberCog(bot, provider_cog))
        log.debug("Subscriber Cog loaded with Provider Cog instnace")
    else:
        log.error("SubscriberCog could not find reference to ProviderCog. Not Loaded.")



class SubscriberConfigModal(ui.Modal):
    channel_id = ui.TextInput(label="Enter Channel ID to post to.")
    text = ui.TextInput(label="Enter message. Use {count} to substitute")
    banner_url = ui.TextInput(label="Banner Image URL")
    interval = ui.TextInput(label="Enter the update interval (ex 1d2h3m4s)", placeholder="5m")

    def __init__(self, provider_name: str, callback: Callable, current_config: Optional[Dict[str, str]], **kwargs):
        log.debug(current_config)
        if current_config is not None:
            self.channel_id.default = current_config.get('channel_id', '')
            self.text.default = current_config.get('text', '')
            self.banner_url.default = current_config.get('banner_url', '')
            self.interval.default = current_config.get('interval', '')
        super().__init__(title=f"Configure Subscriber Alert for {provider_name}", **kwargs)
        self.provider_name = provider_name
        self.callback = callback


    async def on_submit(self, itx: Interaction) -> None:
        await itx.response.defer()
        payload = {
            'text': self.text.value,
            'banner_url': self.banner_url.value,
            'channel_id': self.channel_id.value,
            'interval': self.interval.value
        }
        await self.callback(itx, self.provider_name, payload)