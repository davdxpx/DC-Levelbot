# Discord Ticket Bot

Dieser Bot wurde entwickelt, um ein einfaches und effizientes Ticket-System auf deinem Discord-Server zu ermöglichen. Benutzer können Tickets über ein Panel mit vordefinierten Kategorien öffnen. Diese Tickets werden als private Threads in einem speziellen Admin/Mod-Forum erstellt, wo sie vom Team bearbeitet werden können.

## Features

*   **Ticket-Panel:** Admins können ein Panel mit Buttons für verschiedene Ticket-Typen in einem Kanal posten.
*   **Thread-basierte Tickets:** Jedes Ticket erstellt einen neuen, privaten Thread in einem konfigurierbaren Forum-Kanal.
*   **Ticket-Kategorien via Forum-Tags:** Wendet automatisch Forum-Tags basierend auf dem Ticket-Typ an (erfordert Konfiguration der Tags im Forum).
*   **Claim-System:** Admins/Mods können Tickets claimen, um die Zuständigkeit zu signalisieren.
*   **Close-System:** Tickets können mit einem optionalen Grund geschlossen werden.
    *   Der Thread wird umbenannt, archiviert und gesperrt.
    *   Der Ticketersteller wird per DM über die Schließung informiert.
*   **Logging:** Wichtige Ticket-Aktionen (Erstellung, Claim, Schließung) werden in einem Log-Kanal protokolliert.
*   **Konfigurierbar:** Die meisten wichtigen IDs und Einstellungen werden über eine `.env`-Datei verwaltet.

## Einrichtung

1.  **Bot-Anwendung erstellen:**
    *   Gehe zum [Discord Developer Portal](https://discord.com/developers/applications).
    *   Erstelle eine neue Anwendung.
    *   Gehe zum Tab "Bot" und klicke auf "Add Bot".
    *   **Wichtig:** Aktiviere die folgenden "Privileged Gateway Intents" für deinen Bot:
        *   `SERVER MEMBERS INTENT` (Notwendig, um Benutzerinformationen und DMs korrekt zu handhaben)
        *   `MESSAGE CONTENT INTENT` (Notwendig, falls du planst, textbasierte Befehle hinzuzufügen oder Nachrichten zu lesen - aktuell für Slash Commands nicht zwingend, aber gut für Flexibilität)
    *   Kopiere das **Bot-Token**.

2.  **Bot zum Server einladen:**
    *   Gehe zum Tab "OAuth2" -> "URL Generator".
    *   Wähle die Scopes `bot` und `applications.commands`.
    *   Wähle die notwendigen Bot-Berechtigungen aus. Mindestens erforderlich sind:
        *   `View Channels`
        *   `Send Messages`
        *   `Send Messages in Threads`
        *   `Create Public Threads` (falls das Forum öffentlich ist und private Threads darin erstellt werden)
        *   `Create Private Threads`
        *   `Manage Threads` (zum Umbenennen, Archivieren, Sperren, Anwenden von Tags)
        *   `Embed Links`
        *   `Read Message History`
        *   `Mention @everyone, @here, and All Roles` (für Benachrichtigungen)
    *   Kopiere die generierte URL und füge sie in deinen Browser ein, um den Bot zu deinem Server einzuladen.

3.  **Projekt klonen/herunterladen:**
    *   Downloade die Bot-Dateien (z.B. als ZIP oder via Git).

4.  **Abhängigkeiten installieren:**
    *   Stelle sicher, dass Python 3.8 oder höher installiert ist.
    *   Öffne ein Terminal im Projektverzeichnis und führe aus:
        ```bash
        pip install -r requirements.txt
        ```
    *   Die `requirements.txt` sollte mindestens `discord.py` und `python-dotenv` enthalten.

5.  **`.env`-Datei konfigurieren:**
    *   Erstelle eine Datei namens `.env` im Hauptverzeichnis des Bots (oder benenne `env.example` um, falls vorhanden).
    *   Füge die folgenden Variablen hinzu und ersetze die Platzhalter-Werte:

        ```dotenv
        # Erforderlich: Dein Discord Bot Token
        DISCORD_TOKEN=DEIN_BOT_TOKEN_HIER

        # Erforderlich: ID des Kanals, in dem das "Open a Ticket"-Panel gepostet wird
        OPEN_TICKET_CHANNEL_ID=DEINE_KANAL_ID_HIER

        # Erforderlich: ID des Forum-Kanals, in dem die Ticket-Threads erstellt werden
        APPEALS_FORUM_ID=DEINE_FORUM_KANAL_ID_HIER

        # Optional: ID der Rolle, die bei neuen Tickets im Thread erwähnt werden soll
        # ADMIN_MOD_ROLE_ID=DEINE_ADMIN_MOD_ROLLEN_ID_HIER

        # Optional: ID des Kanals für Ticket-Log-Nachrichten
        # TICKET_LOG_CHANNEL_ID=DEINE_LOG_KANAL_ID_HIER

        # Optional: ID einer Rolle, die Tickets schließen/claimen darf (zusätzlich zu Admins/Server-Moderatoren mit Thread-Berechtigungen)
        # TICKET_CLOSER_ROLE_ID=DEINE_TICKET_SCHLIESSER_ROLLEN_ID_HIER
        ```
    *   **Hinweis:** Alle Zeilen, die mit `#` beginnen, sind Kommentare und werden ignoriert. Entferne das `#` vor optionalen Variablen, wenn du sie verwenden möchtest.

6.  **Forum-Tags konfigurieren (optional, für Ticket-Kategorien):**
    *   Gehe zu deinem "Appeals"-Forum-Kanal in Discord (dessen ID du in `APPEALS_FORUM_ID` eingetragen hast).
    *   Bearbeite den Kanal und gehe zu "Tags".
    *   Erstelle Tags, deren Namen **exakt** den Beschriftungen der Buttons im Ticket-Panel entsprechen. Standardmäßig sind das:
        *   `General Help`
        *   `Bug Report`
        *   `User Report`
        *   `Other Issue`
    *   Der Bot benötigt die Berechtigung, Tags in diesem Forum anzuwenden (normalerweise Teil von "Manage Threads").

7.  **Bot starten:**
    *   Führe im Terminal im Projektverzeichnis aus:
        ```bash
        python bot.py
        ```
    *   Achte auf Fehlermeldungen in der Konsole, falls IDs nicht gefunden werden oder der Token falsch ist.

## Bot-Befehle

*   `/setup_ticket_panel`
    *   **Beschreibung:** Postet das Ticket-Erstellungs-Panel (Embed mit Buttons) im konfigurierten `OPEN_TICKET_CHANNEL_ID`.
    *   **Berechtigung:** Administrator.
    *   **Benutzung:** Führe den Befehl in einem beliebigen Kanal auf deinem Server aus. Der Bot wird dir eine kurzlebige Bestätigung senden. Stelle sicher, dass der Bot Schreibrechte im `OPEN_TICKET_CHANNEL_ID` hat.

## Funktionsweise der Buttons

### Im Ticket-Panel (`OPEN_TICKET_CHANNEL_ID`):

Die Button-Beschriftungen (`General Help` etc.) dienen gleichzeitig als Ticket-Typ und (falls konfiguriert) als Name des zu suchenden Forum-Tags.

*   Klickt ein Benutzer auf einen dieser Buttons, wird:
    1.  Ein neuer privater Thread im `APPEALS_FORUM_ID` erstellt.
    2.  Der Thread-Titel enthält `[Offen]`, den Ticket-Typ und den Benutzernamen.
    3.  (Optional) Ein passender Forum-Tag wird auf den Thread angewendet.
    4.  Eine initiale Embed-Nachricht mit Ticket-Informationen (Ersteller, Typ, Zeit) und Buttons für Admins/Mods (`Claim Ticket`, `Close Ticket`) wird im neuen Thread gepostet.
    5.  (Optional) Die `ADMIN_MOD_ROLE_ID` wird in der initialen Thread-Nachricht erwähnt.
    6.  Der Benutzer erhält eine kurzlebige Bestätigungsnachricht mit einem Link zum Thread und Info zum Tag.
    7.  (Optional) Eine Log-Nachricht über die Ticketerstellung wird im `TICKET_LOG_CHANNEL_ID` gepostet.

### In einem Ticket-Thread (`APPEALS_FORUM_ID`):

Diese Buttons erscheinen in der vom Bot geposteten initialen Embed-Nachricht im Ticket-Thread.

*   **`✅ Claim Ticket`**:
    *   Ein berechtigter Admin/Mod kann diesen Button klicken.
    *   Das ursprüngliche Embed wird aktualisiert: "Geclaimed von: @User am Datum".
    *   Der Button "Claim Ticket" wird deaktiviert und ändert sein Label zu "Geclaimed".
    *   Der klickende Admin/Mod erhält eine kurzlebige Bestätigung.
    *   (Optional) Eine Log-Nachricht wird gesendet.
*   **`🔒 Close Ticket`**:
    *   Ein berechtigter Admin/Mod kann diesen Button klicken.
    *   Es öffnet sich ein Modal, in dem optional ein Grund für die Schließung eingegeben werden kann.
    *   Nach Absenden des Modals:
        1.  Der Thread wird umbenannt (z.B. `[Geschlossen] Ticket-Typ - User`).
        2.  Der Thread wird archiviert und gesperrt.
        3.  Eine neue Embed-Nachricht über die Schließung (mit Schließer, Grund, Zeit) wird im Thread gepostet.
        4.  Der ursprüngliche Ticketersteller wird per DM informiert (falls möglich und User-ID extrahierbar ist).
        5.  Alle Aktionsbuttons (`Claim Ticket`, `Close Ticket`) in der ursprünglichen Nachricht werden deaktiviert.
        6.  Der Admin/Mod erhält eine kurzlebige Bestätigung.
        7.  (Optional) Eine Log-Nachricht wird gesendet.

## Wichtige Hinweise

*   **Berechtigungen des Bots:** Stelle sicher, dass der Bot über alle notwendigen Berechtigungen auf dem Server und in den relevanten Kanälen verfügt. Fehlende Berechtigungen (Threads erstellen/verwalten, Nachrichten senden, Tags anwenden, Mitglieder sehen für DMs) sind häufige Fehlerquellen.
*   **Neustart & Panel-Aktualisierung:** Wenn du den Bot-Code änderst (insbesondere die `View`-Klassen für Buttons oder deren Logik), musst du das Ticket-Panel mit `/setup_ticket_panel` **neu posten**, damit die Änderungen wirksam werden. Alte, bereits gepostete Panels verwenden weiterhin die Button-Logik vom Zeitpunkt ihrer Erstellung.
*   **Korrekte IDs:** Überprüfe alle Kanal-, Forum- und Rollen-IDs in der `.env`-Datei sorgfältig. Der Bot gibt beim Start Hinweise, wenn Kanäle/Foren nicht gefunden werden.
*   **Slash Command Synchronisation:** Es kann nach dem Start des Bots (oder bei erstmaliger globaler Registrierung) bis zu einer Stunde dauern, bis Slash Commands wie `/setup_ticket_panel` auf allen Servern sichtbar sind. Für schnellere Tests während der Entwicklung kann man den `sync`-Befehl im Code auf eine spezifische Guild-ID beschränken (siehe Kommentar in `async def setup_hook()`).

Dieser Bot ist eine Grundlage und kann bei Bedarf um weitere Features erweitert werden.
```
