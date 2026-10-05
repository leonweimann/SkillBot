"""Offline tests for Utils.msgraph (no network, no MSAL server calls)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from Utils import msgraph


# region Fakes

class FakeDbCal:
    def __init__(self, token_cache=None, calendar_id='cal-1'):
        self.teacher_id = 42
        self.token_cache = token_cache
        self.calendar_id = calendar_id
        self.edits = []

    def edit(self, **kwargs):
        self.edits.append(kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeResponse:
    def __init__(self, status=200, json_data=None, headers=None, text=''):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append({'url': url, 'params': params, 'headers': headers})
        return self.responses.pop(0)


class FakeApp:
    def __init__(self, cache, accounts=None, result=None, refresh=False):
        self.cache = cache
        self.accounts = accounts or []
        self.result = result
        self.refresh = refresh

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent_with_error(self, scopes, account):
        if self.refresh:
            # Simulate MSAL writing a rotated refresh token into the cache.
            self.cache.add({
                'client_id': 'dummy-client',
                'scope': scopes,
                'token_endpoint': 'https://login.microsoftonline.com/dummy-tenant/oauth2/v2.0/token',
                'response': {'access_token': 'new-at', 'expires_in': 3600, 'token_type': 'Bearer'},
            })
        return self.result

# endregion


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(msgraph, 'load_dotenv', lambda *a, **k: False)
    monkeypatch.setenv('MS_CLIENT_ID', 'dummy-client')
    monkeypatch.setenv('MS_TENANT_ID', 'dummy-tenant')


@pytest.fixture
def no_sleep(monkeypatch):
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(msgraph, '_sleep', fake_sleep)
    return delays


def _use_session(monkeypatch, session):
    monkeypatch.setattr(msgraph, '_new_session', lambda: session)


def _use_token(monkeypatch, token='tok'):
    async def fake_acquire(db_cal):
        return token
    monkeypatch.setattr(msgraph, '_acquire_token', fake_acquire)


# region Configuration

def test_is_configured_true(configured):
    assert msgraph.is_configured() is True


@pytest.mark.parametrize('missing', ['MS_CLIENT_ID', 'MS_TENANT_ID'])
def test_is_configured_false_when_var_missing(configured, monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert msgraph.is_configured() is False


def test_acquire_token_not_configured(monkeypatch):
    monkeypatch.setattr(msgraph, 'load_dotenv', lambda *a, **k: False)
    monkeypatch.delenv('MS_CLIENT_ID', raising=False)
    monkeypatch.delenv('MS_TENANT_ID', raising=False)
    with pytest.raises(msgraph.GraphNotConfiguredError):
        asyncio.run(msgraph._acquire_token(FakeDbCal()))

# endregion


# region Token acquisition

def test_acquire_token_empty_cache_raises_auth_error(configured, monkeypatch):
    monkeypatch.setattr(msgraph, '_build_app', lambda cache: FakeApp(cache))
    db_cal = FakeDbCal(token_cache=None)
    with pytest.raises(msgraph.GraphAuthError):
        asyncio.run(msgraph._acquire_token(db_cal))
    assert db_cal.edits == []


def test_acquire_token_error_result_raises_auth_error(configured, monkeypatch):
    result = {'error': 'invalid_grant', 'error_description': 'AADSTS70043: expired'}
    monkeypatch.setattr(msgraph, '_build_app', lambda cache: FakeApp(cache, accounts=[{'username': 'x'}], result=result))
    with pytest.raises(msgraph.GraphAuthError, match='AADSTS70043'):
        asyncio.run(msgraph._acquire_token(FakeDbCal(token_cache='{}')))


def test_acquire_token_none_result_raises_auth_error(configured, monkeypatch):
    monkeypatch.setattr(msgraph, '_build_app', lambda cache: FakeApp(cache, accounts=[{'username': 'x'}], result=None))
    with pytest.raises(msgraph.GraphAuthError):
        asyncio.run(msgraph._acquire_token(FakeDbCal(token_cache='{}')))


def test_acquire_token_success_without_cache_change(configured, monkeypatch):
    result = {'access_token': 'at', 'token_type': 'Bearer'}
    monkeypatch.setattr(msgraph, '_build_app', lambda cache: FakeApp(cache, accounts=[{'username': 'x'}], result=result))
    db_cal = FakeDbCal(token_cache='{}')
    assert asyncio.run(msgraph._acquire_token(db_cal)) == 'at'
    assert db_cal.edits == []


def test_acquire_token_saves_changed_cache(configured, monkeypatch):
    result = {'access_token': 'new-at', 'token_type': 'Bearer'}
    monkeypatch.setattr(
        msgraph, '_build_app',
        lambda cache: FakeApp(cache, accounts=[{'username': 'x'}], result=result, refresh=True),
    )
    db_cal = FakeDbCal(token_cache='{}')
    assert asyncio.run(msgraph._acquire_token(db_cal)) == 'new-at'
    assert len(db_cal.edits) == 1
    assert 'AccessToken' in db_cal.edits[0]['token_cache']


def test_acquire_token_with_real_msal_app_and_empty_cache(configured, monkeypatch):
    """Real PublicClientApplication with authority metadata stubbed out (no network)."""
    import msal.authority

    def fake_tenant_discovery(endpoint, http_client, **kwargs):
        base = 'https://login.microsoftonline.com/dummy-tenant'
        return {
            'authorization_endpoint': f'{base}/oauth2/v2.0/authorize',
            'token_endpoint': f'{base}/oauth2/v2.0/token',
            'issuer': f'{base}/v2.0',
        }

    monkeypatch.setattr(msal.authority, 'tenant_discovery', fake_tenant_discovery)
    with pytest.raises(msgraph.GraphAuthError):
        asyncio.run(msgraph._acquire_token(FakeDbCal(token_cache=None)))

# endregion


# region Device flow

def test_start_device_flow_without_user_code_raises(configured, monkeypatch):
    class App:
        def initiate_device_flow(self, scopes):
            return {'error': 'invalid_client', 'error_description': 'public client flows disabled'}

    monkeypatch.setattr(msgraph, '_build_app', lambda cache: App())
    with pytest.raises(msgraph.GraphAuthError, match='public client flows disabled'):
        asyncio.run(msgraph.start_device_flow())


def test_complete_device_flow_failure_raises(configured, monkeypatch):
    class App:
        def acquire_token_by_device_flow(self, flow):
            return {'error': 'authorization_declined', 'error_description': 'user declined'}

    monkeypatch.setattr(msgraph, '_build_app', lambda cache: App())
    with pytest.raises(msgraph.GraphAuthError, match='user declined'):
        asyncio.run(msgraph.complete_device_flow({'device_code': 'x'}))


def test_complete_device_flow_returns_serialized_cache(configured, monkeypatch):
    class App:
        def __init__(self, cache):
            self.cache = cache

        def acquire_token_by_device_flow(self, flow):
            self.cache.add({
                'client_id': 'dummy-client',
                'scope': msgraph.SCOPES,
                'token_endpoint': 'https://login.microsoftonline.com/dummy-tenant/oauth2/v2.0/token',
                'response': {'access_token': 'at', 'expires_in': 3600, 'token_type': 'Bearer'},
            })
            return {'access_token': 'at'}

    monkeypatch.setattr(msgraph, '_build_app', App)
    serialized = asyncio.run(msgraph.complete_device_flow({'device_code': 'x'}))
    assert 'AccessToken' in serialized

# endregion


# region HTTP / Graph API

def test_get_events_rejects_naive_datetimes():
    naive = datetime(2026, 10, 5)
    aware = naive.replace(tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        asyncio.run(msgraph.get_events(FakeDbCal(), naive, aware))
    with pytest.raises(ValueError):
        asyncio.run(msgraph.get_events(FakeDbCal(), aware, naive))


def test_get_events_paginates_and_sends_params(monkeypatch):
    next_link = 'https://graph.microsoft.com/v1.0/me/calendars/cal-1/calendarView?$skiptoken=abc'
    session = FakeSession([
        FakeResponse(json_data={'value': [{'subject': 'A'}], '@odata.nextLink': next_link}),
        FakeResponse(json_data={'value': [{'subject': 'B'}]}),
    ])
    _use_session(monkeypatch, session)
    _use_token(monkeypatch)

    tz = timezone(timedelta(hours=2))
    start = datetime(2026, 10, 5, tzinfo=tz)
    events = asyncio.run(msgraph.get_events(FakeDbCal(), start, start + timedelta(days=1)))

    assert [e['subject'] for e in events] == ['A', 'B']
    first, second = session.calls
    assert first['url'] == 'https://graph.microsoft.com/v1.0/me/calendars/cal-1/calendarView'
    assert first['params']['startDateTime'] == '2026-10-05T00:00:00+02:00'
    assert first['params']['endDateTime'] == '2026-10-06T00:00:00+02:00'
    assert first['params']['$top'] == '100'
    assert 'isOnlineMeeting' in first['params']['$select']
    assert first['headers']['Prefer'] == 'outlook.timezone="W. Europe Standard Time"'
    assert first['headers']['Authorization'] == 'Bearer tok'
    assert second['url'] == next_link
    assert second['params'] is None


def test_list_calendars(monkeypatch):
    session = FakeSession([FakeResponse(json_data={'value': [{'id': 'c1', 'name': 'Kalender'}, {'id': 'c2', 'name': 'Arbeit'}]})])
    _use_session(monkeypatch, session)
    _use_token(monkeypatch)

    assert asyncio.run(msgraph.list_calendars(FakeDbCal())) == [('c1', 'Kalender'), ('c2', 'Arbeit')]
    assert session.calls[0]['params'] == {'$select': 'id,name'}


def test_get_json_retries_on_429(no_sleep):
    session = FakeSession([
        FakeResponse(status=429, headers={'Retry-After': '2'}),
        FakeResponse(status=429, headers={}),
        FakeResponse(json_data={'ok': True}),
    ])
    assert asyncio.run(msgraph._get_json(session, 'https://x', 'tok')) == {'ok': True}
    assert no_sleep == [2.0, msgraph.DEFAULT_RETRY_AFTER_SECONDS]


def test_get_json_gives_up_after_max_retries(no_sleep):
    session = FakeSession([FakeResponse(status=429, headers={'Retry-After': '1'}) for _ in range(msgraph.MAX_RETRIES + 1)])
    with pytest.raises(msgraph.GraphError):
        asyncio.run(msgraph._get_json(session, 'https://x', 'tok'))
    assert len(no_sleep) == msgraph.MAX_RETRIES
    assert len(session.calls) == msgraph.MAX_RETRIES + 1


@pytest.mark.parametrize('status', [401, 403])
def test_get_json_auth_errors(status):
    session = FakeSession([FakeResponse(status=status, text='{"error":{"code":"Forbidden"}}')])
    with pytest.raises(msgraph.GraphAuthError) as exc_info:
        asyncio.run(msgraph._get_json(session, 'https://x', 'tok'))
    if status == 403:
        assert 'consent' in str(exc_info.value)
    assert 'tok' not in str(exc_info.value).replace('token', '')


def test_get_json_other_error_includes_status_and_excerpt():
    session = FakeSession([FakeResponse(status=500, text='x' * 1000)])
    with pytest.raises(msgraph.GraphError) as exc_info:
        asyncio.run(msgraph._get_json(session, 'https://x', 'tok'))
    message = str(exc_info.value)
    assert '500' in message
    assert len(message) < 400

# endregion


def test_acquire_token_transient_error_is_not_an_auth_error(configured, monkeypatch):
    result = {'error': 'temporarily_unavailable', 'error_description': 'try again later'}
    monkeypatch.setattr(msgraph, '_build_app', lambda cache: FakeApp(cache, accounts=[{'username': 'x'}], result=result))
    with pytest.raises(msgraph.GraphError, match='try again later'):
        asyncio.run(msgraph._acquire_token(FakeDbCal(token_cache='{}')))


def test_get_events_rejects_response_without_value_list(monkeypatch):
    _use_session(monkeypatch, FakeSession([FakeResponse(json_data={'unexpected': True})]))
    _use_token(monkeypatch)
    tz = timezone(timedelta(hours=2))
    start = datetime(2026, 10, 5, tzinfo=tz)
    with pytest.raises(msgraph.GraphError, match='value'):
        asyncio.run(msgraph.get_events(FakeDbCal(), start, start + timedelta(days=1)))


def test_cancelling_complete_device_flow_expires_the_flow(configured, monkeypatch):
    import threading
    release = threading.Event()

    class App:
        def acquire_token_by_device_flow(self, flow):
            release.wait(5)
            return {'error': 'expired'}

    monkeypatch.setattr(msgraph, '_build_app', lambda cache: App())
    flow = {'user_code': 'ABC', 'expires_at': 9999999999}

    async def run():
        task = asyncio.create_task(msgraph.complete_device_flow(flow))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

    asyncio.run(run())
    assert flow['expires_at'] == 0
