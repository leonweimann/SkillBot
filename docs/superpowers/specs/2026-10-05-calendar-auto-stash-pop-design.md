# Calendar-driven Auto-Stash/Pop — Design

Date: 2026-10-05 · Status: approved in chat

## Goal

The teacher links their Microsoft 365 (Exchange Online) calendar to the bot. Every night the bot
prepares the teacher's category for the day: students with an appointment today get their channel
moved into the teacher category, all other students of that teacher get archived. Independently,
whenever a student writes into an archived channel, the channel is popped back into the teacher
category automatically.

Worst case (an appointment is not recognised) is acceptable: auto-pop on message covers it.

## Requirements (from the user)

- Calendar entries are titled `<Fach> mit <Vorname Nachname>`, e.g. `Mathematik mit Marco Reising`.
- Ignore non-Discord appointments: Teams (online meeting flag), phone (Outlook category `Telefon`
  and/or a phone number in the location). Phone appointments are new customers that usually have no
  Discord channel, so name matching filters them too.
- `cmd` always stays in the teacher category.
- Nightly prep only for teachers with a linked calendar. Run at 04:00 Europe/Berlin (DST-aware).
- Auto-pop on message is always active, for every teacher. Every student belongs to exactly one
  teacher (`teacher_student` table).
- Manual `/students stash` / `/students pop` keep working. The nightly prep simply overrides them;
  no pinning state.
- Disable the weekly DatabaseIntegrity run (it posts into the alerts channel).
- Sorting after moves must work reliably (current sorter is broken, see below).

## Verified facts (docs research)

discord.py 2.7.1 / Discord API:
- `GuildChannel.position` is the raw, guild-wide position (all text channels share one bucket), not
  an index within a category. `edit(position=i)` runs `_move`, which renumbers the *whole* guild text
  bucket from a possibly stale cache — this is why the current sorter misbehaves.
- `edit(category=...)` keeps overwrites (`sync_permissions` defaults to `False`). Never pass
  `sync_permissions=True`: student channels carry their own overwrites.
- `PATCH /guilds/{id}/channels` (bulk positions) allows at most one `parent_id` change per request.
  So: one `edit(category=...)` per moved channel, then one bulk position request per category.
- No public bulk-position API; use `guild._state.http.bulk_channel_update(guild.id, payload, reason=)`
  with payload `[{"id": int, "position": int}]`. Private → wrap in one helper, pin discord.py.
- Positions 0..n-1 within one category are fine (ties across categories are irrelevant for the UI;
  discord.py's own `move()` does the same).
- The cache updates only on `CHANNEL_UPDATE` gateway events, after the HTTP call returns. Sort from
  fresh data (`await guild.fetch_channels()`) instead of `category.channels` right after moves.
- `tasks.loop(time=datetime.time(4, 0, tzinfo=ZoneInfo("Europe/Berlin")))` is DST-correct.
- `on_message` with author/channel only needs `guild_messages`; bot uses `Intents.all()`.
- discord.py retries 429s automatically.

Microsoft Graph / MSAL:
- Delegated device code flow with `msal.PublicClientApplication` (sync; run in `asyncio.to_thread`).
  Single-tenant app registration, "Allow public client flows" = Yes, no redirect URI. Authority must
  be tenant-specific: `https://login.microsoftonline.com/<tenant-id>`.
- Scope `Calendars.Read` (no admin consent required; tenant consent settings may still require it).
  MSAL adds `offline_access`/`openid`/`profile` automatically.
- Persist `msal.SerializableTokenCache` (`serialize()`/`deserialize()`), save after every acquire when
  `has_state_changed`. Refresh tokens rotate; 90-day lifetime. Use
  `acquire_token_silent_with_error`: `None` → no account, dict with `error` → re-login required.
- Show `flow["message"]` (contains `verification_uri` + `user_code`); code valid ~15 min.
  `acquire_token_by_device_flow` blocks while polling.
- `GET /me/calendars` → `id`, `name`. `GET /me/calendars/{id}/calendarView?startDateTime&endDateTime`
  expands recurring series. Pass ISO datetimes with offset. Follow `@odata.nextLink`. Header
  `Prefer: outlook.timezone="W. Europe Standard Time"`. Handle 429 + `Retry-After`.
- Teams: `isOnlineMeeting == true` (provider `teamsForBusiness`). Other fields used: `subject`,
  `isAllDay`, `isCancelled`, `location.displayName`, `categories`.

## Architecture

New/changed modules (existing structure: `Utils/` helpers, `Coordination/` logic, `cogs/` listeners &
tasks, `cmds/` slash groups; `main.py` auto-loads every top-level `.py` in `cogs/` and `cmds/`).

### `Utils/database.py` (changed)

- New table:
  ```sql
  CREATE TABLE IF NOT EXISTS teacher_calendar (
      teacher_id INTEGER PRIMARY KEY,
      token_cache TEXT,
      calendar_id TEXT,
      calendar_name TEXT,
      last_prepared_date TEXT,          -- ISO date (YYYY-MM-DD), Europe/Berlin
      FOREIGN KEY (teacher_id) REFERENCES teachers (user_id)
  )
  ```
- `TeacherCalendar` dataclass (same style as `Archive`): fields `guild_id, teacher_id, token_cache,
  calendar_id, calendar_name, last_prepared_date`; `load()` in `__post_init__`, `save()` (upsert),
  `delete()` (no error if missing), `edit(**kwargs)`, property `is_linked` (token_cache set),
  property `is_ready` (token_cache and calendar_id set), `@staticmethod get_all(guild_id) -> list`.
- `Teacher.pop()` also deletes the `teacher_calendar` row (foreign keys are ON).
- `TeacherStudentConnection.find_all_by_teacher(guild_id, teacher_id) -> list[TeacherStudentConnection]`
- `TeacherStudentConnection.find_by_channel(guild_id, channel_id) -> Optional[TeacherStudentConnection]`

### `Coordination/sorting.py` (rewritten internals, same public entry point)

- `ordered_channels(channels) -> list`: pure; `cmd` first, then `name.lower()`, tie-break `id`.
- `build_position_payload(ordered) -> list[dict]`: pure; `{"id", "position": i}` only for channels
  whose current `position != i`.
- `ChannelSortingCoordinator.sort_channels_in_category(category)`: keeps `_is_allowed_category` check;
  fetches `await category.guild.fetch_channels()`, takes `discord.TextChannel`s with
  `category_id == category.id`, builds payload, sends a single bulk request via helper
  `_bulk_update_positions(guild, payload, reason)` (skip if empty). Debug logging kept.

### `Coordination/schedule.py` (new, pure — no discord imports)

```python
@dataclass(frozen=True)
class CalendarEvent:
    subject: str
    is_all_day: bool = False
    is_cancelled: bool = False
    is_online_meeting: bool = False
    location: str = ''
    categories: tuple[str, ...] = ()
    @classmethod
    def from_graph(cls, data: dict) -> 'CalendarEvent': ...   # tolerant to missing keys / None

def skip_reason(event: CalendarEvent) -> str | None
    # 'ganztägig' | 'abgesagt' | 'online-meeting' | 'telefon' (category casefold == 'telefon')
    # | 'telefonnummer' (location contains >= 6 digits, only [+\d\s/()-.]) | None
def extract_student_name(subject: str) -> str | None   # text after first ' mit ' (case-insensitive), stripped
def normalize_name(name: str) -> str                   # NFKC, casefold, ä→ae ö→oe ü→ue ß→ss, '-'/'_'→' ', collapse ws
def match_name(name: str, students: dict[int, str]) -> tuple[int | None, bool]
    # (student_id, ambiguous). 1) exact normalized match; 2) unique student whose normalized token set
    # is a superset of the calendar name's tokens (min 2 tokens). Multiple hits → (None, True).

@dataclass
class DayPlan:
    student_ids: set[int]
    matched: dict[int, str]            # student_id -> event subject
    skipped: list[tuple[str, str]]     # (subject, reason)
    unmatched: list[str]               # subjects with a name but no student
    ambiguous: list[str]

def plan_day(events: list[CalendarEvent], students: dict[int, str]) -> DayPlan
    # students: student_id -> real_name (only this teacher's students)

def compute_moves(connections: list[tuple[int, int, int | None]], teacher_category_id: int,
                  target_student_ids: set[int]) -> tuple[list[int], list[int]]
    # connections: (student_id, channel_id, current_category_id) → (channel_ids_to_pop, channel_ids_to_stash)
    # pop: target and current != teacher category; stash: not target and current == teacher category.
```

### `Utils/msgraph.py` (new)

```python
class GraphNotConfiguredError(Exception)   # MS_CLIENT_ID / MS_TENANT_ID missing
class GraphAuthError(Exception)            # (re-)login required
class GraphError(Exception)                # other API failure

SCOPES = ['Calendars.Read']
def is_configured() -> bool
async def start_device_flow() -> dict                       # raises GraphAuthError if no user_code
async def complete_device_flow(flow: dict) -> str            # blocks in thread; returns serialized cache
async def list_calendars(db_cal: TeacherCalendar) -> list[tuple[str, str]]   # (id, name)
async def get_events(db_cal: TeacherCalendar, start: datetime, end: datetime) -> list[dict]
```
- Env: `MS_CLIENT_ID`, `MS_TENANT_ID` (read via `os.getenv` after `load_dotenv()`).
- One `PublicClientApplication` per call with a deserialized cache from `db_cal.token_cache`; on token
  acquisition, if the cache changed → `db_cal.edit(token_cache=cache.serialize())`.
- HTTP via `aiohttp` (ships with discord.py), `$select=subject,start,end,isAllDay,isCancelled,
  isOnlineMeeting,onlineMeetingProvider,location,categories`, `$top=100`, follow nextLink,
  401 → `GraphAuthError`, 429 → sleep `Retry-After` (max 3 retries), other → `GraphError`.

### `Coordination/daily_prep.py` (new)

```python
BERLIN = ZoneInfo('Europe/Berlin')
def get_guild_lock(guild_id: int) -> asyncio.Lock           # serialises all channel moves per guild
def is_archived_category(guild, category_id) -> bool

@dataclass
class PrepResult:
    plan: DayPlan
    popped: list[str]     # channel names
    stashed: list[str]

async def prepare_teacher(guild: discord.Guild, teacher_id: int, day: date, dry_run=False) -> PrepResult
async def pop_to_teacher(guild: discord.Guild, ts_con: TeacherStudentConnection) -> bool   # auto-pop
def format_summary(result: PrepResult, dry_run: bool) -> str   # German, for the cmd channel
def get_cmd_channel(guild, teacher_id) -> discord.TextChannel | None
```
`prepare_teacher`:
1. Load `TeacherCalendar`; not ready → `UsageError`. Fetch events for `[day 00:00, day+1 00:00)`
   Berlin. Any Graph error propagates **before** any channel is touched (safety rule).
2. `students = {c.student_id: Student(...).real_name}` from `find_all_by_teacher`; `plan_day`.
3. Under the guild lock: resolve channels (skip missing), `compute_moves`, pop via
   `channel.edit(category=teacher_category)`, stash via `ArchiveCategory.make(guild)` →
   `add_channel` (re-`make` per channel so a full archive rolls over). Then sort the teacher category
   and every archive category that received channels.
4. Not dry run → `edit(last_prepared_date=day.isoformat())`.

`pop_to_teacher`: under the guild lock, re-fetch the channel (`guild.fetch_channel`) to get its real
category; if not in an archive category → return False; else move into the teacher category, sort it,
return True.

### `cogs/DailyPreparation.py` (new)

- `tasks.loop(time=time(4, 0, tzinfo=BERLIN))` → for every guild, every `TeacherCalendar.is_ready`:
  `prepare_teacher(day=today_berlin)`; post `format_summary` into the teacher's `cmd` channel.
- `on_ready`: start loop (guard `is_running`); catch-up: if Berlin time ≥ 04:00 and
  `last_prepared_date != today` → run prep for that teacher.
- `GraphAuthError` → post into `cmd`: "Kalender-Verbindung abgelaufen, bitte `/calendar connect`" +
  `log(...)`. Other exceptions → `log(...)`. One teacher failing never stops the others.

### `cogs/AutoPop.py` (new)

- `on_message`: ignore DMs and bots; `find_by_channel`; ignore if none or
  `message.author.id == ts_con.teacher_id`; quick cache pre-check (channel category is an archive
  category) to avoid API calls on every message; then `pop_to_teacher`. Log pops to the logs channel.

### `cmds/CalendarGroup.py` (new) — `/calendar …`, `@app_commands.checks.has_role('Lehrer')`

- `connect`: not configured → failure response. `start_device_flow`, reply ephemeral with
  `flow["message"]`; background task awaits `complete_device_flow`, saves `token_cache`, then posts
  success (or failure) into the teacher's `cmd` channel with mention (interaction tokens expire after
  15 min, same as the device code).
- `select calendar:<autocomplete>`: autocomplete lists `list_calendars` (cache per user ~60 s,
  autocomplete must answer within 3 s); stores `calendar_id` + `calendar_name`.
- `status`: linked? calendar name? last prepared date?
- `disconnect`: delete `TeacherCalendar`.
- `preview`: `prepare_teacher(dry_run=True)` → summary ephemeral (nothing is moved).
- `prepare-now`: `prepare_teacher(day=today)` → summary.
- Errors via `env.handle_app_command_error`; `GraphAuthError` → `UsageError`-style message.

### Misc

- `cogs/DatabaseIntegrity.py`: weekly loop no longer started (manual commands stay).
- `requirements.txt` (pinned `discord.py==2.7.1`, `python-dotenv`, `msal==1.35.0`),
  `requirements-dev.txt` (`pytest`), `pytest.ini` (`pythonpath = src`, `testpaths = tests`),
  `.gitignore` += `.venv/`.
- README: setup incl. Entra app registration, `.env` keys, `/calendar` usage.

## Error handling summary

| Situation | Behaviour |
|---|---|
| Graph not configured | `/calendar connect` refuses; nightly job skips silently |
| Token expired / revoked | nothing moved; notice in `cmd` + log |
| Calendar not selected | teacher skipped |
| Name ambiguous / unknown | skipped, listed in summary |
| Student channel missing | skipped, logged |
| Archive full | `ArchiveCategory` rolls over to a new archive |

## Testing

pytest (Python 3.12) for the pure parts: `schedule.py` (filtering, name extraction, normalization,
matching incl. ambiguity, `compute_moves`), `sorting.py` (`ordered_channels`,
`build_position_payload` with fake channel objects), `database.py` (`TeacherCalendar` and the new
queries against a temp DB by monkeypatching the db path). Discord/Graph side verified manually via
`/calendar preview` before relying on the nightly job.

## Delivery

Stacked PRs via `gh stack` on top of `main` (nothing merged), Conventional Commits, small commits
(bottom → top):
1. `docs/calendar-spec` — this spec
2. `chore/tooling-and-integrity` — disable weekly integrity run, requirements, pytest setup
3. `fix/channel-sorting` — bulk sorting
4. `feat/calendar-db` — table + queries
5. `feat/calendar-matching` — `schedule.py`
6. `feat/msgraph-client` — `msgraph.py`
7. `feat/daily-preparation` — env followup fix, archive return value, `daily_prep.py`, `DailyPreparation` cog
8. `feat/calendar-commands` — `/calendar` commands
9. `feat/auto-pop` — `AutoPop` cog
10. `docs/calendar-setup` — README
