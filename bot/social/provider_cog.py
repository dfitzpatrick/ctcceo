import asyncio
from datetime import timedelta
from typing import List, Protocol, Optional, Callable, Any, Dict, Type

import discord
from discord.ext import commands
from discord import app_commands, ui
from discord.interactions import Interaction

from bot.social.providers import YouTubeProvider, RedditProvider, TwitchProvider, TwitterProvider

from mixins.config import ConfigMixin
from discord.ext import tasks
import logging
from functools import partial
from services import establish_member_config

log = logging.getLogger(__name__)

class Provider(Protocol):
    def __call__(self, *args, **kwargs):
        return self

    async def subscriber_count(self) -> int:
        ...

    async def verify_config(self) -> bool:
        ...


class ProviderConfig:

    def __init__(self, name: str, provider: Type[Provider], **object_init_descriptions):
        self.provider = provider
        self.name = name
        self.init_kwargs = object_init_descriptions

    def create(self, **kwargs):
        return self.provider(**kwargs)

class ProviderTaskService:
    interval = timedelta(minutes=5)

    def __init__(self, name: str, provider: Provider, callback: Callable, interval: Optional[timedelta] = None):
        self.name = name
        self.provider = provider
        self.callback = callback
        self.task: Optional[asyncio.Task] = None
        if interval is not None:
            self.interval = interval
            self.provider_task.change_interval(seconds=interval.total_seconds())

    @tasks.loop(seconds=interval.total_seconds(), reconnect=True)
    async def provider_task(self):
        log.debug(f"In task for {self.name}. Calling callback")
        await self.callback(self.name, self.provider)

    def start(self):
        name = self.provider.__repr__()
        log.debug(f"Starting {name} Task Service with interval {self.interval.total_seconds()}")
        self.task = self.provider_task.start()
        task_finished = partial(self._task_finished, provider=self.provider)
        self.task.add_done_callback(task_finished)
        return self.task

    def stop(self):
        self.provider_task.cancel()


    def _task_finished(self, future: asyncio.Future, *, provider: Provider):
        name = provider.__repr__()
        try:
            if future.exception() and not future.cancelled():
                log.error(str(future.exception()))
                raise future.exception()
        except asyncio.CancelledError:
            log.debug(f"ProviderTaskService task for {name} was cancelled")
            pass



class ProviderCog(ConfigMixin, commands.GroupCog, name='provider'):

    def __init__(self, bot: commands.Bot, provider_definitions: List[ProviderConfig]):
        self.bot = bot
        self.provider_definitions = provider_definitions
        self.provider_instances = {}
        self.first_run = True
        super().__init__()

    @commands.Cog.listener()
    async def on_ready(self):
        if self.first_run:
            self.load_providers_from_settings()
            self.first_run = False

    def load_providers_from_settings(self):
        log.debug("Loading providers from configuration")
        for guild_string in self.config_settings.keys():
            guild = self.bot.get_guild(int(guild_string))
            if guild is None:
                continue
            for member_string in self.config_settings[guild_string].keys():
                member = guild.get_member(int(member_string))
                if member is None:
                    continue
                for provider_name in self.config_settings[guild_string][member_string]['providers'].keys():
                    try:
                        self.load_provider(member, provider_name)
                    except ValueError as e:
                        log.error(e)
                        continue

    def load_provider(self, member: discord.Member, provider_name: str):
        guild_str = str(member.guild.id)
        member_str = str(member.id)
        if member not in self.provider_instances.keys():
            self.provider_instances[member] = {}
        definition = self.find_provider_definition_by_name(provider_name)
        payload = self.config_settings.get(guild_str, {}).get(member_str, {}).get('providers', {}).get(provider_name, {}).get('payload')
        if definition is None:
            raise ValueError(f"Could not find provider with name {provider_name}")
        if payload is None:
            raise ValueError(f"No settings for provider found for user")

        self.provider_instances[member][provider_name] = definition.create(**payload)
        log.debug(f"Provider {provider_name} loaded for {member.display_name} in guild {member.guild}")

    def find_provider_instance_by_member_and_name(self, member: discord.Member, name: str) -> Optional[Provider]:
        providers = self.provider_instances.get(member, {})
        return providers.get(name)

    def find_provider_definition_by_name(self, name: str) -> Optional[ProviderConfig]:
        for p in self.provider_definitions:
            if p.name == name:
                return p
    def establish_member_config(self, guild_id: str, member_id: str):
        if guild_id not in self.config_settings.keys():
            self.config_settings[guild_id] = {}
        if member_id not in self.config_settings[guild_id].keys():
            self.config_settings[guild_id][member_id] = {}

    def establish_member_provider_config(self, guild_id: str, member_id: str, provider_name: str):
        if 'providers' not in self.config_settings[guild_id][member_id].keys():
            self.config_settings[guild_id][member_id]['providers'] = {}
        if provider_name not in self.config_settings[guild_id][member_id]['providers'].keys():
            self.config_settings[guild_id][member_id]['providers'][provider_name] = {}

    def save_member_provider_config(self, guild_id: str, member_id: str, provider_name: str, payload: Dict[str, Any]):
        self.establish_member_config(guild_id, member_id)
        self.establish_member_provider_config(guild_id, member_id, provider_name)

        self.config_settings[guild_id][member_id]['providers'][provider_name]['payload'] = payload
        self.save_settings()



    async def config_modal_callback(self, itx: Interaction, provider_config: ProviderConfig, payload: Dict[str, Any]):
        key = provider_config.name
        instance = provider_config.create(**payload)
        success = await instance.verify_config()
        if not success:
            await itx.followup.send("Invalid configuration settings. Changes not saved.", ephemeral=True)
            return

        self.provider_instances[key] = instance
        guild_key = str(itx.guild_id)
        member_key = str(itx.user.id)
        provider_key = provider_config.name
        establish_member_config(self.config_settings, guild_key, member_key)
        self.establish_member_provider_config(guild_key, member_key, provider_key)
        self.config_settings[guild_key][member_key]['providers'][provider_key]['payload'] = payload
        self.save_settings()
        await itx.followup.send("Settings Saved!", ephemeral=True)
        self.load_provider(itx.user, key)

    @app_commands.command()
    async def config(self, itx: Interaction, provider_name: str):
        provider = self.find_provider_definition_by_name(provider_name)
        if provider is None:
            await itx.response.send_message("Provider not found", ephemeral=True)
            return

        await itx.response.send_modal(ProviderConfigModal(provider, self.config_modal_callback))



async def setup(bot: commands.Bot):
    provider_definitions = [
        ProviderConfig(
            "youtube",
            YouTubeProvider,
            api_key="YouTube API Key",
            channel_id="Channel ID"
        ),
        ProviderConfig(
            "reddit",
            RedditProvider,
            subreddit="Sub Reddit Name"
        ),
        ProviderConfig(
            "twitch",
            TwitchProvider,
            user_id="Twitch User-Id",
            client_id="Twitch Client-Id",
            client_secret="Twitch Client Secret"
        ),
        ProviderConfig(
            "twitter",
            TwitterProvider,
            user_id="Twitter User-Id",
            app_bearer_token="Twitter Bearer Authentication Token"
        )
    ]
    provider_cog = ProviderCog(bot, provider_definitions)
    await bot.add_cog(provider_cog)


class ProviderConfigModal(ui.Modal):
    def __init__(self, provider_config: ProviderConfig, callback: Callable, **kwargs):
        super().__init__(title="Configure Provider", **kwargs)
        self.provider_config = provider_config
        self.callback = callback

        for attr, description in self.provider_config.init_kwargs.items():
            o = ui.TextInput(label=description)
            setattr(self, attr, o)
            self.add_item(o)

    async def on_submit(self, itx: Interaction) -> None:
        payload = {attr:getattr(self, attr).value for attr in self.provider_config.init_kwargs.keys()}
        await itx.response.defer()
        await self.callback(itx, self.provider_config, payload)


class ProviderCommandGroup(app_commands.Group):

    def __init__(self, cog: 'ProviderCog', **kwargs):
        super().__init__(**kwargs)
        self.cog = cog



