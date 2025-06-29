# DC-Levelbot

This repository contains the source code for a Discord bot that implements an interactive user level system. The system is designed to keep your community engaged through XP, levels, rank cards and periodic challenges.

## Features Overview

- **Interactive XP System**: Gain XP for messages, reactions and being active on the server.
- **Cooldown Mechanism**: Prevents spam farming of XP.
- **Bonus XP**: Reward high quality interactions and popular messages.
- **Dynamic Rank Cards**: Users can display their progress with a `rank` slash command or check `/profile` for badges.
- **Automatic Role Rewards**: Unlock roles at certain level milestones.
- **Leaderboard**: Shows the most active members in real-time.
- **Challenges & Events**: Optional weekly/monthly events provide extra XP or special badges.
- **Badge System**: Collect unique badges for activity, reactions and long time membership. Display them with the `/badges` command.
- **Keep Alive Task**: A background loop prints a heartbeat every few minutes so the bot stays active.

## Implemented Slash Commands

- `/rank [member]`: Zeigt deine (oder eines anderen Nutzers) aktuelle Rank-Card an.
- `/leaderboard`: Zeigt das Server-Leaderboard mit den Top-Nutzern.
- `/badges [member]`: Zeigt deine (oder eines anderen Nutzers) verdienten Abzeichen an.
- `/profile [member]`: Zeigt dein (oder eines anderen Nutzers) Profil inklusive Rank-Card und Abzeichen.
- `/stats [member]`: Zeigt detaillierte Statistiken (XP, Level, Nachrichten, Reaktionen, etc.) für dich oder einen anderen Nutzer.
- `/serverstats`: Zeigt übergreifende Statistiken für den gesamten Server (Mitgliederzahl, Gesamt-XP, etc.).
- `/daily`: Erlaube Nutzern, eine tägliche XP-Belohnung zu beanspruchen.
- `/givexp <member> <amount>`: (Admin-only) Vergibt eine bestimmte Menge XP an einen Nutzer.
- `/triviapursuit`: (In Entwicklung) Starte eine Runde Trivia und gewinne XP.
- `/start`: Eine einfache Begrüßungsnachricht, um zu bestätigen, dass der Bot läuft.

## Privileged Intents

**Wichtig**: Dieser Bot benötigt die folgenden Privileged Gateway Intents, um voll funktionsfähig zu sein:
- `Server Members Intent`: Wird für das Abrufen von Mitgliederinformationen (z.B. für Rank-Cards, Avatare, Beitrittsdaten) und das Vergeben von Rollenbelohnungen benötigt.
- `Message Content Intent`: Wird benötigt, um XP für das Senden von Nachrichten zu vergeben.

Bitte stelle sicher, dass diese Intents für deinen Bot im Discord Developer Portal (unter `Privileged Gateway Intents`) aktiviert sind.

## Konfiguration

To configure the bot copy `.env.example` to `.env` and fill in your details:

```
cp .env.example .env
# edit the file and set BOT_TOKEN and optionally GUILD_ID and ROLE_REWARDS
```

The `ROLE_REWARDS` variable uses the format `level:role_id` separated by commas.
Commands are automatically synced every time the bot starts. If `GUILD_ID` is
set, commands sync instantly for that server; otherwise they sync globally.
See the `bot.py` file for further usage instructions.

If you want the bot to resynchronise the commands on every start automatically,
set `AUTO_SYNC=true` in your `.env` file. This can be helpful on hosting
platforms where cached commands might become outdated.

To sync the slash commands without starting the bot (useful for Railway's
pre-deploy step), run:

```
python bot.py --sync
```

You can also force a resync before running the bot with:

```
python bot.py --sync-first
```
