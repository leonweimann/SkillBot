"""Discord fakes for archive tests: a server-side 50 channel limit and a lagging guild cache.

- Discord itself rejects a 51st channel in a category (400, code 50035 on ``parent_id``).
- The guild cache lags: ``category.channels`` / ``channel.category_id`` only change when the gateway
  events are applied (``FakeGuild.sync``), never during a burst of moves.
"""

from types import SimpleNamespace

import discord


GUILD_ID = 5
MAX = 50


def http_error(status: int, code: int, errors: dict | None = None, message: str = 'Invalid Form Body'):
    response = SimpleNamespace(status=status, reason='Bad Request')
    return discord.HTTPException(response, {'code': code, 'message': message, 'errors': errors or {}})


def category_full_error():
    return http_error(400, 50035, {'parent_id': {'_errors': [{
        'code': 'CHANNEL_PARENT_MAX_CHANNELS', 'message': 'Maximum number of channels in category reached (50)'
    }]}})


def server_error():
    return discord.DiscordServerError(SimpleNamespace(status=503, reason='Service Unavailable'), 'upstream')


class FakeCategory:
    def __init__(self, guild, id, name):
        self.guild = guild
        self.id = id
        self.name = name
        self.category_id = None

    @property
    def channels(self):  # Like discord.py: derived from the (lagging) cache
        return [c for c in self.guild.cached_channels if c.category_id == self.id]


class FakeChannel:
    def __init__(self, guild, id, name, category_id):
        self.guild = guild
        self.id = id
        self.name = name
        self.category_id = category_id  # Cached parent, only updated by FakeGuild.sync

    @property
    def mention(self):
        return f'<#{self.id}>'

    async def edit(self, *, category, reason=None):
        guild = self.guild
        guild.edit_calls.append((self.id, category.id))
        if guild.fail_edits:
            raise guild.fail_edits.pop(0)
        if category.id not in guild.server_categories:
            raise http_error(404, 10003, message='Unknown Channel')
        already_there = guild.server_parent.get(self.id) == category.id
        if not already_there and guild.server_count(category.id) >= MAX:
            raise category_full_error()
        guild.server_parent[self.id] = category.id
        # Like discord.py: a new object is returned, the cached one stays untouched
        return FakeChannel(guild, self.id, self.name, category.id)


class FakeGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.server_parent: dict[int, int | None] = {}   # Server truth: channel id -> parent id
        self.server_categories: dict[int, str] = {}      # Server truth: category id -> name
        self.cached_channels: list[FakeChannel] = []
        self.cached_categories: list[FakeCategory] = []
        self.edit_calls: list[tuple[int, int]] = []
        self.fail_edits: list[Exception] = []
        self.fail_fetches: list[Exception] = []
        self.fetches = 0
        self.created: list[str] = []
        self._next_id = 10_000
        self.lounge = SimpleNamespace(name='lounge', members=[])
        self.voice_channels = [self.lounge]

    @property
    def categories(self):
        return list(self.cached_categories)

    @property
    def text_channels(self):
        return list(self.cached_channels)

    def add_category(self, id, name):
        self.server_categories[id] = name
        category = FakeCategory(self, id, name)
        self.cached_categories.append(category)
        return category

    def add_channel(self, id, name, category_id):
        self.server_parent[id] = category_id
        channel = FakeChannel(self, id, name, category_id)
        self.cached_channels.append(channel)
        return channel

    def fill(self, category_id, count, start):
        return [self.add_channel(start + i, f'alt-{start + i}', category_id) for i in range(count)]

    def server_count(self, category_id):
        return sum(1 for parent in self.server_parent.values() if parent == category_id)

    def sync(self):
        """Applies all pending gateway events to the cache."""
        for channel in self.cached_channels:
            channel.category_id = self.server_parent.get(channel.id)
        known = {category.id for category in self.cached_categories}
        for id, name in self.server_categories.items():
            if id not in known:
                self.cached_categories.append(FakeCategory(self, id, name))

    async def fetch_channels(self):
        self.fetches += 1
        if self.fail_fetches:
            raise self.fail_fetches.pop(0)
        fresh = [FakeCategory(self, id, name) for id, name in self.server_categories.items()]
        fresh += [FakeChannel(self, id, f'ch-{id}', parent) for id, parent in self.server_parent.items()]
        return fresh

    async def create_category(self, name):
        self._next_id += 1
        self.server_categories[self._next_id] = name
        self.created.append(name)
        return FakeCategory(self, self._next_id, name)  # Not in the cache yet (gateway lag)


class FakeArchiveTable:
    """Stands in for Utils.database.Archive (rows in insertion order, like rowid order)."""

    def __init__(self):
        self.rows: dict[int, str | None] = {}

    def __call__(self, guild_id, id):
        table = self

        class Row:
            def __init__(self):
                self.id = id
                self.name = table.rows.get(id)

            def edit(self, name=None):
                if name is not None:
                    self.name = name
                table.rows[id] = self.name

        return Row()

    def get_all(self, guild_id):
        return [SimpleNamespace(id=id, name=name) for id, name in self.rows.items()]
