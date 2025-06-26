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

To configure the bot copy `.env.example` to `.env` and fill in your details:

```
cp .env.example .env
# edit the file and set BOT_TOKEN and optionally GUILD_ID and ROLE_REWARDS
```

The `ROLE_REWARDS` variable uses the format `level:role_id` separated by commas.
Commands are automatically synced every time the bot starts. If `GUILD_ID` is
set, commands sync instantly for that server; otherwise they sync globally.
See the `bot.py` file for further usage instructions.

To sync the slash commands without starting the bot (useful for Railway's
pre-deploy step), run:

```
python bot.py --sync
```
