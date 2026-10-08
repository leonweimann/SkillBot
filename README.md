# SkillBot

Discord-Bot für einen Nachhilfe-Server: Lehrer und Schüler, pro Schüler ein eigener Channel
(in der Kategorie des Lehrers) und ein Archiv für Channels ohne aktuellen Termin. Der Bot verwaltet
die Zuordnung Lehrer/Schüler (`/teachers`, `/students`), sortiert Channels und kann die Kategorie eines
Lehrers anhand seines Outlook-Kalenders automatisch vorbereiten.

## Setup

Voraussetzung: [uv](https://docs.astral.sh/uv/). uv installiert bei Bedarf auch Python 3.12
(siehe `.python-version`).

```bash
uv sync --no-dev                       # .venv anlegen, Abhängigkeiten aus uv.lock installieren
cp .env.example .env                   # und Werte eintragen
mkdir -p data                          # Datenverzeichnis, muss existieren
uv run python src/main.py
```

- Abhängigkeiten stehen in `pyproject.toml`, die exakten Versionen in `uv.lock` (mit committen).
  Neue Pakete mit `uv add <paket>` hinzufügen, Updates mit `uv lock --upgrade-package <paket>`.
- `discord.py` ist bewusst gepinnt, weil das Channel-Sorting einen internen Endpoint von discord.py nutzt.

- Der Bot muss aus dem Repo-Root gestartet werden: `main.py` lädt die Erweiterungen über
  `./src/cogs` und `./src/cmds` relativ zum aktuellen Verzeichnis.
- `.env`-Schlüssel:
  - `DISCORD_TOKEN` (Pflicht)
  - `MS_CLIENT_ID`, `MS_TENANT_ID` (nur für die Kalender-Automatik, siehe unten)
- Daten liegen pro Server in `./data/skillbot_<guild_id>.db` (SQLite). Der Ordner `data/` wird vom Bot
  nicht angelegt und muss vorhanden sein. Die Tabellen werden beim Start automatisch erstellt.
- Die Datenbank enthält auch die Microsoft-Token (siehe unten): `data/` privat halten, nicht committen.

## Deployment (Docker)

Der Bot wird als Docker-Image betrieben. Das Image installiert die Abhängigkeiten exakt aus `uv.lock`
(ohne Dev-Gruppe) und läuft als Nicht-Root-User.

```bash
cp .env.example .env          # DISCORD_TOKEN, MS_CLIENT_ID, MS_TENANT_ID eintragen
docker compose up -d --build  # bauen und starten (Neustart automatisch: restart: unless-stopped)
docker compose logs -f        # Logs
docker compose down           # stoppen (Daten bleiben im Volume)
```

- Die `.env` wird zur Laufzeit übergeben (`env_file`), nicht ins Image kopiert.
- Die SQLite-Datenbanken (inkl. Microsoft-Token) liegen im Named Volume `skillbot-data` unter `/app/data`.
  Bestehende Daten (`./data/*.db`) einmalig übernehmen, bevor der Bot zum ersten Mal startet:

  ```bash
  docker compose run --rm --no-deps --user root -v ./data:/import:ro --entrypoint sh skillbot \
    -c 'cp -a /import/. /app/data/ && chown -R skillbot:skillbot /app/data'
  ```

  (`docker compose cp` eignet sich nicht: die Dateien gehören danach nicht dem Bot-User und sind
  schreibgeschützt.)
- Update: `git pull && docker compose up -d --build`.
- `docker stop` sendet SIGINT, damit der Bot die Verbindung sauber schließt.

## Tests

```bash
uv sync                                # inkl. Dev-Gruppe (pytest)
uv run pytest -q
```

## Kalender-Automatik (Auto-Stash/Pop)

Der Bot sorgt dafür, dass in der Lehrer-Kategorie nur die Schüler-Channels liegen, die gerade gebraucht
werden. Lehrer können dafür optional ihren Microsoft-365-Kalender (Outlook) verknüpfen.

**Nachts um 04:00 Uhr (Europe/Berlin, Sommer-/Winterzeit wird berücksichtigt):**

- **Ohne Kalender** (oder wenn die Microsoft-Anbindung nicht konfiguriert ist): Alle Schüler-Channels in der
  Lehrer-Kategorie werden archiviert, außer von Schülern, die gerade in der Lounge warten. Morgens ist die
  Kategorie leer, Lounge und Nachrichten holen die Channels zurück (siehe Auto-Pop).
- **Mit verknüpftem und ausgewähltem Kalender** wird die Kategorie für den Tag vorbereitet:

  - Schüler mit einem Termin heute: Channel wird in die Lehrer-Kategorie verschoben (pop).
  - Alle anderen Schüler dieses Lehrers: Channel wird archiviert (stash).
  - Eine Zusammenfassung (verschoben, übersprungen, nicht zugeordnet, mehrdeutig) landet im `cmd`-Channel
    des Lehrers. Mit `/calendar summary enabled:False` lässt sie sich abschalten (`enabled:True` schaltet sie
    wieder ein). Die Vorbereitung selbst läuft weiter, und der Hinweis auf eine abgelaufene
    Kalender-Verbindung kommt trotzdem.
  - Wurde der Bot um 04:00 nicht ausgeführt, holt er die Kalender-Vorbereitung beim Start nach. Das
    Archivieren ohne Kalender wird bewusst nicht nachgeholt: Ein Neustart tagsüber würde sonst Channels
    laufender Stunden wegräumen.
- `cmd` bleibt immer in der Lehrer-Kategorie.

**Auto-Pop:** Ein archivierter Schüler-Channel kommt automatisch zurück in die Lehrer-Kategorie, sobald

- der Schüler (oder ein verbundener Zweit-Account) den Sprachkanal `lounge` betritt, oder
- jemand außer dem Lehrer in den Channel schreibt.

Das gilt immer, für alle Lehrer, mit und ohne Kalender. Ein nicht erkannter Termin ist also unkritisch.

**Sicherheitsregel:** Gibt es bei einem Lehrer mit Kalender einen Kalenderfehler (Verbindung, abgelaufener
Token, ...), wird für ihn nichts verschoben oder archiviert. Bei abgelaufener Anmeldung meldet der Bot das im `cmd`-Channel.

**Manuelles `/students stash` und `/students pop`** funktionieren weiterhin. Der nächste nächtliche Lauf
überschreibt sie aber, es gibt kein Festpinnen.

### Titelformat und Erkennung

Termine heißen `<Fach> mit <Vorname Nachname>`, z. B. `Mathematik mit Marco Reising`. Der Name ist der Text
nach dem ersten " mit " (Groß-/Kleinschreibung egal).

Übersprungen werden:

- abgesagte Termine
- ganztägige Termine
- Teams-/Online-Meetings
- Termine mit der Outlook-Kategorie "Telefon"
- Termine, deren Ort eine Telefonnummer ist (mind. 6 Ziffern, nur Ziffern und `+ / ( ) - .`)
- Titel ohne " mit "

Der Name wird mit dem `real_name` des Schülers im Bot verglichen:

- Groß-/Kleinschreibung, Bindestriche und Umlaute werden normalisiert (ä = ae, ö = oe, ü = ue, ß = ss).
- Zuerst zählt ein exakter Treffer. Sonst wird ein Schüler gefunden, dessen Name alle Wörter des
  Kalendernamens enthält (mind. 2 Wörter, z. B. "Marco Reising" passt auf "Marco Paul Reising").
- Mehrere mögliche Treffer: der Termin wird übersprungen und in der Zusammenfassung als mehrdeutig genannt.

Tipp: Die `real_name`-Werte der Schüler müssen zu den Kalendernamen passen. Andernfalls mit
`/students rename` korrigieren. Mit `/calendar preview` lässt sich das prüfen.

Achtung: Ist in Outlook „Allen Besprechungen eine Onlinebesprechung hinzufügen“ aktiv, gilt jeder Termin als
Teams-Meeting und wird übersprungen. Dann würden nachts alle Schüler archiviert. Die Zusammenfassung zeigt
das als `N× online-meeting`.

Archive fassen höchstens 50 Channels (Discord-Grenze). Der Bot zählt die freien Plätze vor dem Archivieren
anhand der aktuellen Daten von Discord (nicht anhand seines Zwischenspeichers). Ist ein Archiv voll, kommt der
Channel ins nächste Archiv, bei Bedarf legt der Bot ein neues an. Schlägt ein Verschieben trotzdem fehl
(z. B. Netzwerkfehler auch nach einem zweiten Versuch), bleibt der Channel bis zur nächsten Nacht in der
Lehrer-Kategorie und wird als fehlgeschlagen genannt; den Grund schreibt der Bot in den `logs`-Channel.

### Microsoft-Entra-App registrieren

Einmalig pro Microsoft-365-Business-Mandant (Admin-Zugang nötig). Die Bezeichnungen im Portal können
leicht abweichen.

1. [entra.microsoft.com](https://entra.microsoft.com) öffnen, anmelden.
2. Entra ID (Identity) → App registrations → **New registration**.
3. Name z. B. `SkillBot Kalender`. Supported account types: **Accounts in this organizational directory
   only (Single tenant)**. Redirect URI leer lassen. Registrieren.
4. Auf der Übersichtsseite kopieren:
   - **Application (client) ID** → `MS_CLIENT_ID`
   - **Directory (tenant) ID** → `MS_TENANT_ID`
5. Authentication → Advanced settings → **Allow public client flows** = **Yes** → Speichern.
6. API permissions → Add a permission → Microsoft Graph → **Delegated permissions** → `Calendars.Read`
   hinzufügen. Admin-Zustimmung ist dafür normalerweise nicht nötig. Blockiert der Mandant die
   Zustimmung durch Benutzer, auf **Grant admin consent** klicken.
7. Ein Client Secret wird nicht benötigt.
8. Beide IDs in `.env` eintragen und den Bot neu starten.

### Kalender verknüpfen

Alle `/calendar`-Befehle erfordern die Rolle `Lehrer`.

1. `/calendar connect`: Der Bot antwortet (nur für dich sichtbar) mit einem Link und einem Code.
   Link öffnen, Code eingeben, mit dem Microsoft-Konto anmelden (der Code ist ca. 15 Minuten gültig).
   Der Bot bestätigt die Verknüpfung im `cmd`-Channel.
2. `/calendar select`: Kalender auswählen (Autovervollständigung), z. B. "Nachhilfe".
3. `/calendar preview`: Zeigt, welche Schüler heute verschoben würden, ohne etwas zu verschieben.
   Hier prüfen, ob die Namen zugeordnet werden.
4. Optional `/calendar prepare-now`: Führt die Vorbereitung sofort aus.

Weitere Befehle: `/calendar status` (Verknüpfung, Kalender, letzter Lauf, Zusammenfassung an/aus),
`/calendar disconnect` (Verknüpfung löschen) und `/calendar summary` (nächtliche Zusammenfassung im
`cmd`-Channel ein- oder ausschalten; `/calendar preview` und `/calendar prepare-now` antworten weiterhin
mit der Zusammenfassung). Die Einstellung bleibt auch nach `/calendar disconnect` erhalten.

Der Refresh-Token wird durch die nächtliche Nutzung erneuert. Nach ca. 90 Tagen ohne Nutzung oder nach einem
Widerruf der Anmeldung postet der Bot einen Hinweis im `cmd`-Channel. Dann einfach erneut
`/calendar connect` ausführen. Der Token-Cache liegt in der SQLite-Datenbank (`data/`), daher privat halten.

## Hinweise

- Der wöchentliche DatabaseIntegrity-Lauf ist deaktiviert (die manuellen Befehle bleiben).
