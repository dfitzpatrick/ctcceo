import json
from datetime import datetime, timezone, timedelta
from json import JSONDecodeError
from typing import Optional, Any, Dict
import re

import aiohttp
from bs4 import BeautifulSoup
class ProviderError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class BaseProvider:

    async def subscriber_count(self):
        raise NotImplemented

    async def verify_config(self):
        try:
            return (await self.subscriber_count()) >= 0
        except Exception:
            return False

class YouTubeProvider(BaseProvider):

    def __init__(self, api_key: str, channel_id: str):
        self._api_key = api_key
        self._channel_id = channel_id
        self.target = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={self._channel_id}&key={self._api_key}"

    async def subscriber_count(self) -> int:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.target) as resp:
                data = await resp.json()
                return int(data['items'][0]['statistics']['subscriberCount'])



class AppToken(dict):
    def __init__(self,*args, **kwargs):
        super(AppToken, self).__init__(*args, **kwargs)
        self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=self['expires_in'])

    @property
    def is_valid(self):
        now = datetime.now(timezone.utc)
        return now < self.expires_at

class ApplicationOATH:


    def __init__(self, token_url: str, request_payload: Dict[str, Any]):
        self._payload = request_payload
        self.token_url = token_url
        self.app_token: Optional[AppToken] = None

    @property
    def auth_header(self):
        if self.app_token is None:
            raise AuthenticationError

        token_type = self.app_token['token_type'].capitalize()
        return {
            'Authorization': f'{token_type} {self._app_token}',
            'Client-Id': self.client_id
        }


    def authenticate(coro):
        async def _dec(self):
            if self.app_token and not self.app_token.valid:
                form_data = aiohttp.FormData(self._payload)
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.token_url, data=form_data) as resp:
                        data = await resp.json()
                        self.app_token = AppToken(**data)

            return await coro(self)
        return _dec

class RedditProvider(BaseProvider):

    def __init__(self, subreddit: str):
        self.subreddit = subreddit
        self.about_url = f"https://www.reddit.com/r/{subreddit}/about.json"


    async def subscriber_count(self):
        headers = {'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(self.about_url, headers=headers) as resp:
                data = await resp.json()
                print(data)
                return data['data']['subscribers']

    async def verify_config(self):
        try:
            return (await self.subscriber_count()) >= 0
        except Exception:
            return False


class TwitchProvider(BaseProvider):

    def __init__(self, user_id: str, client_id: str, client_secret: str):
        self.user_id = user_id
        self._client_id = client_id
        self._client_secret = client_secret
        self.expires: Optional[datetime] = None
        self._app_token: Optional[str] = None
        self._token_type = "bearer"

    @property
    def auth_header(self):
        if self._app_token is None:
            raise AuthenticationError

        token_type = self._token_type.capitalize()
        return {
            'Authorization': f'{token_type} {self._app_token}',
            'Client-Id': self._client_id
        }

    def _authenticate(coro):
        async def _dec(self):
            target = "https://id.twitch.tv/oauth2/token"
            fields = {
                'client_id': self._client_id,
                'client_secret': self._client_secret,
                'grant_type': 'client_credentials'
            }
            form_data = aiohttp.FormData(fields)
            async with aiohttp.ClientSession() as session:
                async with session.post(target, data=form_data) as resp:
                    data = await resp.json()
                    self._app_token = data['access_token']
                    self.expires = datetime.now(timezone.utc) + timedelta(seconds=data['expires_in'])
                    self._token_type = data['token_type']

            return await coro(self)
        return _dec

    @_authenticate
    async def subscriber_count(self):
        target = f"https://api.twitch.tv/helix/users/follows?to_id={self.user_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(target, headers=self.auth_header) as resp:
                data = await resp.json()
                return data['total']



class TwitterProvider(BaseProvider):
    def __init__(self, user_id: str, app_bearer_token: str):
        self._bearer = app_bearer_token
        self._user_id = user_id

    async def subscriber_count(self):
        target = f"https://api.twitter.com/2/users/{self._user_id}?user.fields=public_metrics"
        headers = {"Authorization": f"Bearer {self._bearer}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(target, headers=headers) as resp:
                data = await resp.json()
                return data['data']['public_metrics']['followers_count']


class InstagramProvider(BaseProvider):

    def __init__(self, username: str):
        self.username = username
        self._shared_data = {}

    @classmethod
    async def for_username(cls, username: str) -> 'InstagramProvider':
        o = cls(username)
        await o.refresh()
        return o

    async def _get_html(self):
        url = "https://www.instagram.com"
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/{self.username}") as resp:
                self.html = await resp.text()
                return self.html

    def _fetch_shared_data(self, html: str) -> Dict[str, Any]:
        pattern = r'window\._sharedData = (.*);'
        try:
            result = re.findall(pattern, html)[0]
            data = json.loads(result)
            return data
        except (IndexError, JSONDecodeError):
            return {}

    async def refresh(self):
        html = await self._get_html()
        self._shared_data = self._fetch_shared_data(html)
        if not self._shared_data:
            raise ProviderError("No User Data Found")

    @property
    def user(self) -> Dict[str, Any]:
        try:
            print(self._shared_data)
            return self._shared_data['entry_data']['ProfilePage'][0]['graphql']['user']
        except (KeyError, IndexError):
            raise ProviderError("Could not locate user object")

    async def subscriber_count(self):
        try:
            return self.user['edge_followed_by']['count']
        except KeyError:
            raise ProviderError("Subscriber count not found")

class TikTokProvider(BaseProvider):
    def __init__(self, username: str):
        self._username = username

    def _soup_followers(self, html: str) -> Optional[int]:
        print("parsing")
        soup = BeautifulSoup(html)
        print("parsed")
        follower = soup("strong", {"data-e2e": "followers-count"})
        try:
            return int(follower[0].text)
        except (IndexError, ValueError):
            return

    async def subscriber_count(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:90.0) Gecko/20100101 Firefox/90.0"
        }

        target = f"https://www.tiktok.com/{self._username}"
        print(target)
        async with aiohttp.ClientSession() as session:
            print('got session')
            async with session.get(target, headers=headers) as resp:
                print('got resp')
                #print(resp)
                html = await resp.text()
                print(html)
                return html
                #followers = self._soup_followers(html)
                #return followers if followers else 0

