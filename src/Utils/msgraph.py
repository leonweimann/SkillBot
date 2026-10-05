"""
Thin async wrapper around Microsoft Graph for reading a teacher's Outlook calendar.

Authentication uses the MSAL delegated device code flow. The serialized MSAL token cache is
persisted per teacher in the database (``TeacherCalendar.token_cache``); MSAL itself is
synchronous, so all of its calls run in a worker thread via ``asyncio.to_thread``.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
import msal
from dotenv import load_dotenv

if TYPE_CHECKING:
    from Utils.database import TeacherCalendar

logger = logging.getLogger(__name__)


# region Exceptions

class GraphNotConfiguredError(Exception):
    """Raised when MS_CLIENT_ID or MS_TENANT_ID is missing from the environment"""
    pass


class GraphAuthError(Exception):
    """Raised when the teacher has to (re-)link their Microsoft account"""
    pass


class GraphError(Exception):
    """Raised for any other Microsoft Graph API failure"""
    pass

# endregion


# region Constants

SCOPES = ['Calendars.Read']

GRAPH_BASE_URL = 'https://graph.microsoft.com/v1.0'
AUTHORITY_BASE_URL = 'https://login.microsoftonline.com'
OUTLOOK_TIMEZONE = 'W. Europe Standard Time'
EVENT_FIELDS = 'subject,start,end,isAllDay,isCancelled,isOnlineMeeting,onlineMeetingProvider,location,categories'

HTTP_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
DEFAULT_RETRY_AFTER_SECONDS = 5
ERROR_BODY_EXCERPT_LENGTH = 300

# Indirection so tests can skip real waiting without patching asyncio globally.
_sleep = asyncio.sleep

# endregion


# region Configuration & MSAL

def _get_config() -> tuple[Optional[str], Optional[str]]:
    """Return (client_id, tenant_id) from the environment."""
    load_dotenv()
    return os.getenv('MS_CLIENT_ID'), os.getenv('MS_TENANT_ID')


def is_configured() -> bool:
    """
    Checks whether the Microsoft Graph integration is configured.

    Returns:
        bool: True if both MS_CLIENT_ID and MS_TENANT_ID are set, False otherwise.
    """
    client_id, tenant_id = _get_config()
    return bool(client_id) and bool(tenant_id)


def _build_app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    """
    Builds a PublicClientApplication for the configured single-tenant app registration.

    Note: Constructing the application performs a blocking metadata request, so this must be
    called from a worker thread.

    Raises:
        GraphNotConfiguredError: If MS_CLIENT_ID or MS_TENANT_ID is missing.
    """
    client_id, tenant_id = _get_config()
    if not client_id or not tenant_id:
        raise GraphNotConfiguredError('MS_CLIENT_ID and MS_TENANT_ID must be set')
    return msal.PublicClientApplication(
        client_id,
        authority=f'{AUTHORITY_BASE_URL}/{tenant_id}',
        token_cache=cache,
    )


def _ensure_configured():
    if not is_configured():
        raise GraphNotConfiguredError('MS_CLIENT_ID and MS_TENANT_ID must be set')

# endregion


# region Device Flow

async def start_device_flow() -> dict:
    """
    Starts the device code flow for linking a Microsoft account.

    Returns:
        dict: The MSAL flow object. ``flow['message']`` contains the verification URL and user
        code to show to the teacher; pass the whole dict to `complete_device_flow`.

    Raises:
        GraphNotConfiguredError: If the integration is not configured.
        GraphAuthError: If the flow could not be started.
    """
    _ensure_configured()

    def _initiate() -> dict:
        app = _build_app(msal.SerializableTokenCache())
        return app.initiate_device_flow(scopes=SCOPES)

    try:
        flow = await asyncio.to_thread(_initiate)
    except GraphNotConfiguredError:
        raise
    except Exception as e:
        raise GraphError(f'Could not start device flow: {e}') from e

    if 'user_code' not in flow:
        description = flow.get('error_description') or flow.get('error') or 'unknown error'
        raise GraphAuthError(f'Could not start device flow: {description}')
    return flow


async def complete_device_flow(flow: dict) -> str:
    """
    Waits (in a worker thread) until the teacher completed the device code login.

    Args:
        flow (dict): The flow object returned by `start_device_flow`.

    Returns:
        str: The serialized MSAL token cache to persist in ``TeacherCalendar.token_cache``.

    Raises:
        GraphNotConfiguredError: If the integration is not configured.
        GraphAuthError: If the login failed, was declined or timed out.
    """
    _ensure_configured()

    def _complete() -> tuple[dict, str]:
        cache = msal.SerializableTokenCache()
        app = _build_app(cache)
        result = app.acquire_token_by_device_flow(flow)
        return result, cache.serialize()

    try:
        result, serialized = await asyncio.to_thread(_complete)
    except GraphNotConfiguredError:
        raise
    except Exception as e:
        raise GraphError(f'Could not complete device flow: {e}') from e

    if 'access_token' not in result:
        description = result.get('error_description') or result.get('error') or 'unknown error'
        raise GraphAuthError(f'Microsoft login failed: {description}')
    return serialized

# endregion


# region Token Acquisition

async def _acquire_token(db_cal: 'TeacherCalendar') -> str:
    """
    Acquires an access token silently from the teacher's persisted token cache.

    If MSAL refreshed tokens (the cache changed), the new cache is saved via ``db_cal.edit``.

    Args:
        db_cal (TeacherCalendar): The teacher's calendar record holding the token cache.

    Returns:
        str: A valid access token.

    Raises:
        GraphNotConfiguredError: If the integration is not configured.
        GraphAuthError: If no account is cached or the refresh failed (re-login required).
        GraphError: If MSAL failed for another reason (e.g. network).
    """
    _ensure_configured()

    def _acquire() -> tuple[str, Optional[str]]:
        cache = msal.SerializableTokenCache()
        if db_cal.token_cache:
            cache.deserialize(db_cal.token_cache)
        app = _build_app(cache)

        accounts = app.get_accounts()
        if not accounts:
            raise GraphAuthError('No Microsoft account linked; please log in again')

        result = app.acquire_token_silent_with_error(SCOPES, accounts[0])
        if result is None:
            raise GraphAuthError('No cached token available; please log in again')
        if 'error' in result or 'access_token' not in result:
            description = result.get('error_description') or result.get('error') or 'unknown error'
            raise GraphAuthError(f'Token refresh failed; please log in again: {description}')

        new_cache = cache.serialize() if cache.has_state_changed else None
        return result['access_token'], new_cache

    try:
        token, new_cache = await asyncio.to_thread(_acquire)
    except (GraphAuthError, GraphNotConfiguredError):
        raise
    except Exception as e:
        raise GraphError(f'Token acquisition failed: {e}') from e

    if new_cache is not None:
        logger.debug(f"MSAL token cache changed for teacher {getattr(db_cal, 'teacher_id', '?')}; saving")
        db_cal.edit(token_cache=new_cache)
    return token

# endregion


# region HTTP

def _new_session() -> aiohttp.ClientSession:
    """Creates an aiohttp session with the module's default timeout."""
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS))


def _parse_retry_after(value: Optional[str]) -> float:
    try:
        return max(0.0, float(value)) if value is not None else DEFAULT_RETRY_AFTER_SECONDS
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS


async def _get_json(session: Any, url: str, token: str, params: Optional[dict] = None) -> dict:
    """
    Performs an authenticated GET request against Microsoft Graph and returns the JSON body.

    Args:
        session: The aiohttp client session.
        url (str): The full request URL.
        token (str): The access token (never logged).
        params (Optional[dict]): Query parameters.

    Returns:
        dict: The parsed JSON response.

    Raises:
        GraphAuthError: On 401 (token invalid) or 403 (missing consent/permission).
        GraphError: On any other non-2xx status, or if 429 persists after MAX_RETRIES retries.
    """
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Prefer': f'outlook.timezone="{OUTLOOK_TIMEZONE}"',
    }

    retries = 0
    delay: float = DEFAULT_RETRY_AFTER_SECONDS
    while True:
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                status = resp.status
                if 200 <= status < 300:
                    return await resp.json()

                body = await resp.text()
                excerpt = body[:ERROR_BODY_EXCERPT_LENGTH]

                if status == 401:
                    raise GraphAuthError('Microsoft Graph rejected the token (401); please log in again')
                if status == 403:
                    raise GraphAuthError(
                        'Microsoft Graph denied access (403): the permission "Calendars.Read" has '
                        'not been consented. Please log in again and grant consent, or ask the '
                        f'tenant admin to approve the app. Details: {excerpt}'
                    )
                if status == 429:
                    if retries >= MAX_RETRIES:
                        raise GraphError(f'Microsoft Graph throttled the request (429) after {MAX_RETRIES} retries')
                    delay = _parse_retry_after(resp.headers.get('Retry-After'))
                    retries += 1
                    logger.warning(f'Microsoft Graph throttled (429); retry {retries}/{MAX_RETRIES} in {delay}s')
                else:
                    raise GraphError(f'Microsoft Graph request failed ({status}): {excerpt}')
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise GraphError(f'Microsoft Graph request failed: {type(e).__name__}: {e}') from e

        await _sleep(delay)

# endregion


# region Public API

async def list_calendars(db_cal: 'TeacherCalendar') -> list[tuple[str, str]]:
    """
    Lists the calendars of the linked Microsoft account.

    Args:
        db_cal (TeacherCalendar): The teacher's calendar record holding the token cache.

    Returns:
        list[tuple[str, str]]: (calendar id, calendar name) pairs.

    Raises:
        GraphNotConfiguredError, GraphAuthError, GraphError
    """
    token = await _acquire_token(db_cal)
    calendars: list[tuple[str, str]] = []
    url: Optional[str] = f'{GRAPH_BASE_URL}/me/calendars'
    params: Optional[dict] = {'$select': 'id,name'}

    async with _new_session() as session:
        while url:
            data = await _get_json(session, url, token, params=params)
            calendars.extend((c['id'], c.get('name') or '') for c in data.get('value', []))
            url = data.get('@odata.nextLink')
            params = None  # nextLink already carries all query parameters
    return calendars


async def get_events(db_cal: 'TeacherCalendar', start: datetime, end: datetime) -> list[dict]:
    """
    Fetches all events of the selected calendar in ``[start, end)``, with recurring series expanded.

    Event times are returned in "W. Europe Standard Time".

    Args:
        db_cal (TeacherCalendar): The teacher's calendar record (token cache and calendar id).
        start (datetime): Timezone-aware start of the window.
        end (datetime): Timezone-aware end of the window.

    Returns:
        list[dict]: The raw Graph event objects (selected fields only).

    Raises:
        ValueError: If start or end is naive, or no calendar is selected.
        GraphNotConfiguredError, GraphAuthError, GraphError
    """
    if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
        raise ValueError('start and end must be timezone-aware datetimes')
    if not db_cal.calendar_id:
        raise ValueError('No calendar selected')

    token = await _acquire_token(db_cal)
    events: list[dict] = []
    url: Optional[str] = f'{GRAPH_BASE_URL}/me/calendars/{db_cal.calendar_id}/calendarView'
    params: Optional[dict] = {
        'startDateTime': start.isoformat(),
        'endDateTime': end.isoformat(),
        '$select': EVENT_FIELDS,
        '$top': '100',
    }

    async with _new_session() as session:
        while url:
            data = await _get_json(session, url, token, params=params)
            events.extend(data.get('value', []))
            url = data.get('@odata.nextLink')
            params = None  # nextLink already carries all query parameters
    return events

# endregion
