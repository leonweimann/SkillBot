import asyncio
from types import SimpleNamespace

import discord

from Coordination import sorting
from Coordination.sorting import build_position_payload, ordered_channels


def ch(id, name, position=0):
    return SimpleNamespace(id=id, name=name, position=position)


def names(channels):
    return [c.name for c in channels]


# ordered_channels

def test_cmd_first():
    channels = [ch(1, 'anna'), ch(2, 'cmd'), ch(3, 'bert')]
    assert names(ordered_channels(channels)) == ['cmd', 'anna', 'bert']


def test_case_insensitive_order():
    channels = [ch(1, 'Zoe'), ch(2, 'bert'), ch(3, 'Anna'), ch(4, 'carl')]
    assert names(ordered_channels(channels)) == ['Anna', 'bert', 'carl', 'Zoe']


def test_tie_break_by_id():
    channels = [ch(9, 'Anna'), ch(3, 'anna'), ch(5, 'ANNA')]
    assert [c.id for c in ordered_channels(channels)] == [3, 5, 9]


def test_without_cmd():
    channels = [ch(1, 'b'), ch(2, 'a')]
    assert names(ordered_channels(channels)) == ['a', 'b']


def test_empty():
    assert ordered_channels([]) == []


# build_position_payload

def test_already_sorted_gives_empty_payload():
    ordered = [ch(1, 'cmd', 0), ch(2, 'anna', 1), ch(3, 'bert', 2)]
    assert build_position_payload(ordered) == []


def test_only_changed_positions_are_included():
    ordered = [ch(1, 'cmd', 0), ch(2, 'anna', 2), ch(3, 'bert', 1)]
    assert build_position_payload(ordered) == [
        {"id": 2, "position": 1},
        {"id": 3, "position": 2},
    ]


def test_guild_wide_positions_are_renumbered():
    ordered = [ch(1, 'cmd', 40), ch(2, 'anna', 42), ch(3, 'bert', 45)]
    assert build_position_payload(ordered) == [
        {"id": 1, "position": 0},
        {"id": 2, "position": 1},
        {"id": 3, "position": 2},
    ]


def test_ordered_then_payload():
    channels = [ch(10, 'bert', 41), ch(11, 'cmd', 43), ch(12, 'Anna', 40)]
    payload = build_position_payload(ordered_channels(channels))
    assert payload == [
        {"id": 11, "position": 0},
        {"id": 12, "position": 1},
        {"id": 10, "position": 2},
    ]


# sort_channels_in_category

def text_channel(id, name, position, category_id):
    channel = object.__new__(discord.TextChannel)
    channel.id = id
    channel.name = name
    channel.position = position
    channel.category_id = category_id
    return channel


class FakeGuild:
    def __init__(self, channels):
        self.id = 1
        self._channels = channels
        self.fetch_calls = 0

    async def fetch_channels(self):
        self.fetch_calls += 1
        return self._channels


def run_sort(monkeypatch, guild, category, allowed=True):
    calls = []

    async def fake_bulk(guild, payload, reason=None):
        calls.append((guild, payload, reason))

    coordinator = sorting.ChannelSortingCoordinator()
    monkeypatch.setattr(coordinator, '_is_allowed_category', lambda c: allowed)
    monkeypatch.setattr(coordinator, '_bulk_update_positions', fake_bulk)
    asyncio.run(coordinator.sort_channels_in_category(category))
    return calls


def test_sort_category_sends_single_bulk_request(monkeypatch):
    guild = FakeGuild([
        text_channel(10, 'bert', 41, category_id=100),
        text_channel(11, 'cmd', 43, category_id=100),
        text_channel(12, 'Anna', 40, category_id=100),
        text_channel(20, 'other', 5, category_id=200),
        SimpleNamespace(id=30, name='voice', position=0, category_id=100),
    ])
    category = SimpleNamespace(id=100, name='Teacher', guild=guild)

    calls = run_sort(monkeypatch, guild, category)

    assert guild.fetch_calls == 1
    assert len(calls) == 1
    assert calls[0][0] is guild
    assert calls[0][1] == [
        {"id": 11, "position": 0},
        {"id": 12, "position": 1},
        {"id": 10, "position": 2},
    ]


def test_sort_category_skips_request_when_sorted(monkeypatch):
    guild = FakeGuild([
        text_channel(11, 'cmd', 0, category_id=100),
        text_channel(12, 'anna', 1, category_id=100),
    ])
    category = SimpleNamespace(id=100, name='Teacher', guild=guild)

    assert run_sort(monkeypatch, guild, category) == []


def test_sort_category_skips_disallowed_category(monkeypatch):
    guild = FakeGuild([text_channel(12, 'anna', 5, category_id=100)])
    category = SimpleNamespace(id=100, name='Teacher', guild=guild)

    assert run_sort(monkeypatch, guild, category, allowed=False) == []
    assert guild.fetch_calls == 0


def test_bulk_update_positions_uses_http_client():
    calls = []

    class FakeHttp:
        async def bulk_channel_update(self, guild_id, payload, *, reason=None):
            calls.append((guild_id, payload, reason))

    guild = SimpleNamespace(id=1, _state=SimpleNamespace(http=FakeHttp()))
    payload = [{"id": 2, "position": 0}]

    asyncio.run(sorting.ChannelSortingCoordinator._bulk_update_positions(guild, payload, reason='sort'))

    assert calls == [(1, payload, 'sort')]
