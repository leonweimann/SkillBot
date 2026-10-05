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
  Bestehende Daten einmalig übernehmen:
  `docker compose cp ./data/. skillbot:/app/data/` (bei laufendem Container), danach
  `docker compose restart`.
- Update: `git pull && docker compose up -d --build`.
- `docker stop` sendet SIGINT, damit der Bot die Verbindung sauber schließt.

## Tests

```bash
uv sync                                # inkl. Dev-Gruppe (pytest)
uv run pytest -q
```

## Kalender-Automatik (Auto-Stash/Pop)

Lehrer können ihren Microsoft-365-Kalender (Outlook) mit dem Bot verknüpfen.

**Nachts um 04:00 Uhr (Europe/Berlin, Sommer-/Winterzeit wird berücksichtigt)** bereitet der Bot für jeden
Lehrer mit verknüpftem und ausgewähltem Kalender die Kategorie vor:

- Schüler mit einem Termin heute: Channel wird in die Lehrer-Kategorie verschoben (pop).
- Alle anderen Schüler dieses Lehrers: Channel wird archiviert (stash).
- `cmd` bleibt immer in der Lehrer-Kategorie.
- Eine Zusammenfassung (verschoben, übersprungen, nicht zugeordnet, mehrdeutig) landet im `cmd`-Channel
  des Lehrers.
- Wurde der Bot um 04:00 nicht ausgeführt, holt er die Vorbereitung beim Start nach.

**Auto-Pop:** Schreibt jemand (außer dem Lehrer) in einen archivierten Schüler-Channel, wird dieser
automatisch zurück in die Lehrer-Kategorie geholt. Das gilt immer, für alle Lehrer, auch ohne Kalender.
Ein nicht erkannter Termin ist also unkritisch.

**Sicherheitsregel:** Gibt es einen Kalenderfehler (Verbindung, abgelaufener Token, ...), wird nichts
verschoben oder archiviert. Bei abgelaufener Anmeldung meldet der Bot das im `cmd`-Channel.

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

Bekannte Grenze: Werden in einer Nacht sehr viele Channels in ein fast volles Archiv (50 Channels) verschoben,
kann einzelnes Verschieben fehlschlagen. Der Channel bleibt dann bis zur nächsten Nacht in der
Lehrer-Kategorie und wird in der Zusammenfassung als fehlgeschlagen genannt.

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

Weitere Befehle: `/calendar status` (Verknüpfung, Kalender, letzter Lauf) und `/calendar disconnect`
(Verknüpfung löschen).

Der Refresh-Token wird durch die nächtliche Nutzung erneuert. Nach ca. 90 Tagen ohne Nutzung oder nach einem
Widerruf der Anmeldung postet der Bot einen Hinweis im `cmd`-Channel. Dann einfach erneut
`/calendar connect` ausführen. Der Token-Cache liegt in der SQLite-Datenbank (`data/`), daher privat halten.

## Hinweise

- Der wöchentliche DatabaseIntegrity-Lauf ist deaktiviert (die manuellen Befehle bleiben).
