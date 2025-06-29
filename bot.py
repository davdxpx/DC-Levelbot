"""Discord level bot main entry point."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import asyncio

import discord
from discord import app_commands
from discord.ext import commands, tasks

import leveling
from rank_card import create_rank_card
import badges

ENV_PATH = Path(".env")


def load_config() -> dict:
    """Load configuration from environment variables."""
    print("\U0001F527 Lade .env Konfiguration...")  # Debug
    if ENV_PATH.exists():
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH)
        print("\u2705 .env geladen")
    else:
        print("\u26a0\ufe0f Keine .env gefunden, benutze Umgebungsvariablen")

    token = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    guild_id = int(os.getenv("GUILD_ID", "0"))
    rewards_raw = os.getenv("ROLE_REWARDS", "")
    rewards: dict[str, int] = {}
    for pair in rewards_raw.split(","):
        if ":" in pair:
            level, role_id = pair.split(":", 1)
            if level and role_id:
                rewards[level.strip()] = int(role_id.strip())

    return {"token": token, "guild_id": guild_id, "role_rewards": rewards}


async def sync_commands_standalone(config: dict, intents: discord.Intents) -> None:
    """Creates a temporary bot instance, logs in, syncs slash commands, and exits."""
    print("\U0001F9F9 Erstelle temporäre Bot-Instanz für die Synchronisation...")
    temp_bot = LevelBot(command_prefix="!", intents=intents, config=config)
    token = config["token"]

    print(f"\U0001F511 Versuche Bot-Login für Befehlssynchronisation (Token: ...{token[-5:]})")
    await temp_bot.login(token)
    print("\U0001F510 Temporärer Bot erfolgreich eingeloggt.")

    guild_id = temp_bot.config.get("guild_id")
    guild = discord.Object(id=guild_id) if guild_id else None

    # Commands are added to tree in LevelBot.__init__
    # We need to ensure the tree is populated for the temp_bot instance
    # However, LevelBot.__init__ already adds commands to self.tree
    # So temp_bot.tree should be ready.

    target_description = f"Guild {guild_id}" if guild_id else "Global"
    print(f"\U0001F503 Starte Synchronisation für: {target_description}")

    try:
        await temp_bot.tree.sync(guild=guild)
        print(f"\u2705 Befehle erfolgreich synchronisiert für: {target_description}")
    except discord.errors.HTTPException as e:
        print(f"\U0001F525 FEHLER bei der {target_description} Befehlssynchronisation: {e}")
    except Exception as e:
        print(f"\U0001F525 Unerwarteter FEHLER bei der {target_description} Befehlssynchronisation: {e}")
    finally:
        await temp_bot.close()
        print("\U0001F4F5 Temporäre Bot-Verbindung für Synchronisation geschlossen.")


def main() -> None:
    parser = argparse.ArgumentParser(description="LevelBot entry point")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Synchronise slash commands and exit",
    )
    parser.add_argument(
        "--sync-first",
        action="store_true",
        help="Sync commands before running the bot",
    )
    args = parser.parse_args()

    print("\U0001F680 Starte LevelBot...")
    config = load_config()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    # Removed bot instance creation here, it will be created after potential sync

    if args.sync:
        asyncio.run(sync_commands_standalone(config, intents))
        return

    auto_sync = args.sync_first or os.getenv("AUTO_SYNC", "").lower() in {"1", "true", "yes"}
    if auto_sync:
        print("\U0001F504 AUTO_SYNC oder --sync-first erkannt. Führe Befehlssynchronisation durch...")
        asyncio.run(sync_commands_standalone(config, intents))
        print("\U0001F50C Synchronisation abgeschlossen.")

    # Create the main bot instance AFTER sync operations are complete
    print("\U0001F916 Erstelle Haupt-Bot-Instanz...")
    bot = LevelBot(command_prefix="!", intents=intents, config=config)
    bot.run(config["token"])


class LevelBot(commands.Bot):
    """A Discord bot that manages user XP and levels."""

    def __init__(self, command_prefix: str, intents: discord.Intents, config: dict):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.config = config
        self.cooldowns: dict[int, datetime] = {}
        guild_id = self.config.get("guild_id")
        self.target_guild = discord.Object(id=guild_id) if guild_id else None

        # Store commands in a list to iterate through
        self.bot_commands = [
            self.rank,
            self.leaderboard,
            self.badges_command,
            self.profile,
            self.start_command,
            self.stats_command,
            self.server_stats_command,
            self.give_xp_command,
            self.daily_command,
            self.trivia_command # Added
        ]

        for cmd in self.bot_commands:
            if self.target_guild:
                self.tree.add_command(cmd, guild=self.target_guild)
            else:
                self.tree.add_command(cmd)
        print("\U0001F916 Bot initialisiert und Befehle zur Synchronisation vorbereitet.")

    async def setup_hook(self) -> None:
        print("\U0001F503 Setup Hook: Starte Befehlssynchronisation...")
        try:
            if self.target_guild:
                await self.tree.sync(guild=self.target_guild)
                print(f"\U0001F504 Befehle erfolgreich für Guild {self.target_guild.id} synchronisiert.")
            else:
                await self.tree.sync()
                print("\U0001F504 Globale Befehle erfolgreich synchronisiert.")
        except discord.errors.HTTPException as e:
            print(f"\U0001F525 FEHLER bei der Befehlssynchronisation: {e}")
        except Exception as e:
            print(f"\U0001F525 Unerwarteter FEHLER bei der Befehlssynchronisation: {e}")

        # start background tasks once the event loop is running
        self.daily_reset.start()
        self.keep_alive.start()
        print("\u23F1\uFE0F Hintergrundaufgaben gestartet")

    # --- New Commands ---
    @app_commands.command(name="stats", description="Zeigt detaillierte Statistiken für einen Nutzer.")
    @app_commands.describe(member="Der Nutzer, dessen Statistiken angezeigt werden sollen (standardmäßig du selbst).")
    async def stats_command(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        target_user = member or interaction.user

        xp, level, next_level_xp = leveling.get_user_data(target_user.id)

        # Fetch raw stats from badges module
        user_stats_raw = badges._STATS.get(str(target_user.id), {})
        messages_sent = user_stats_raw.get("messages", 0)
        reactions_given = user_stats_raw.get("reactions_given", 0)
        reactions_received = user_stats_raw.get("reactions_received", 0)
        join_date_str = user_stats_raw.get("join_date")

        join_date_display = "Unbekannt"
        if join_date_str:
            try:
                join_dt = datetime.fromisoformat(join_date_str)
                join_date_display = f"<t:{int(join_dt.timestamp())}:D>" # Discord timestamp format (Short Date)
            except ValueError:
                join_date_display = "Ungültiges Datum"

        xp_for_current_level = level * leveling.XP_PER_LEVEL
        xp_in_current_level = xp - xp_for_current_level
        xp_needed_for_next_level_increment = leveling.XP_PER_LEVEL

        embed = discord.Embed(title=f"📊 Statistiken für {target_user.display_name}", color=discord.Color.purple())
        if target_user.avatar:
            embed.set_thumbnail(url=target_user.avatar.url)

        embed.add_field(name="🏆 Level & XP", value=f"**Level:** {level}\n**XP:** {xp}/{next_level_xp}\n**Fortschritt:** {xp_in_current_level}/{xp_needed_for_next_level_increment} XP", inline=True)
        embed.add_field(name="💬 Aktivität", value=f"**Nachrichten:** {messages_sent}\n**Reaktionen (gegeben):** {reactions_given}\n**Reaktionen (erhalten):** {reactions_received}", inline=True)
        embed.add_field(name="📅 Mitgliedschaft", value=f"**Beitrittsdatum (Server):** <t:{int(target_user.joined_at.timestamp())}:D>\n**Tracking-Start:** {join_date_display}", inline=False)

        user_badges_ids = badges.get_user_badges(target_user.id)
        if user_badges_ids:
            badge_icons = " ".join(badges.BADGE_DEFINITIONS[b_id].icon for b_id in user_badges_ids)
            embed.add_field(name="🏅 Abzeichen", value=badge_icons if badge_icons else "Keine", inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverstats", description="Zeigt Statistiken für den gesamten Server.")
    async def server_stats_command(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Dieser Befehl kann nur auf einem Server verwendet werden.", ephemeral=True)
            return

        guild = interaction.guild
        total_members = guild.member_count

        # Calculate total XP and unique users with XP from leveling data
        all_xp_data = leveling._DATA
        total_xp_accumulated = sum(data.xp for data in all_xp_data.values())
        unique_users_with_xp = len(all_xp_data)

        # Calculate total messages and reactions from badge stats data
        all_badge_stats = badges._STATS
        total_messages_tracked = sum(s.get("messages", 0) for s in all_badge_stats.values())
        total_reactions_given_tracked = sum(s.get("reactions_given", 0) for s in all_badge_stats.values())
        total_reactions_received_tracked = sum(s.get("reactions_received", 0) for s in all_badge_stats.values())

        embed = discord.Embed(title=f"📈 Server Statistiken für {guild.name}", color=discord.Color.orange())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="👥 Mitglieder", value=f"**Gesamtmitglieder:** {total_members}\n**Nutzer mit XP:** {unique_users_with_xp}", inline=True)
        embed.add_field(name="🌟 XP & Aktivität", value=f"**Gesamte XP:** {total_xp_accumulated}\n**Gesendete Nachrichten (getrackt):** {total_messages_tracked}", inline=True)
        embed.add_field(name="👍 Reaktionen (getrackt)", value=f"**Gegeben:** {total_reactions_given_tracked}\n**Erhalten:** {total_reactions_received_tracked}", inline=True)

        # Bot uptime (rough estimate based on when bot object was created)
        # This is very basic. For a more accurate uptime, you'd store startup time.
        # However, self.user.created_at is the bot's account creation, not this session's start.
        # For now, we'll omit a potentially misleading uptime.

        embed.set_footer(text=f"Server ID: {guild.id}")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="givexp", description="Vergibt XP an einen Nutzer (nur für Administratoren).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Der Nutzer, der XP erhalten soll.", amount="Die Menge an XP, die vergeben werden soll.")
    async def give_xp_command(self, interaction: discord.Interaction, member: discord.Member, amount: int) -> None:
        if amount <= 0:
            await interaction.response.send_message("Die XP-Menge muss positiv sein.", ephemeral=True)
            return

        if member.bot:
            await interaction.response.send_message("Bots können keine XP erhalten.", ephemeral=True)
            return

        level_before = leveling.get_level(member.id)
        new_level = leveling.add_xp(member.id, amount)

        await interaction.response.send_message(
            f"{amount} XP wurden erfolgreich an {member.mention} vergeben. Er ist jetzt Level {new_level}.",
            ephemeral=True
        )

        print(f"\U0001F4E9 Admin {interaction.user.display_name} hat {member.display_name} {amount} XP gegeben.")

        # Check for level up and announce if necessary (similar to on_message)
        if new_level > level_before:
            # We need guild context for role rewards and sending messages
            guild = interaction.guild
            if not guild: # Should not happen with admin commands but good practice
                stored_guild_id = self.config.get("guild_id")
                if stored_guild_id:
                    guild = self.get_guild(stored_guild_id)

            if guild:
                # Re-fetch member from the guild the bot is primarily operating on, if needed
                # This ensures role assignments happen on the correct configured guild
                # However, for `givexp`, the interaction guild is likely the correct one.
                target_member_for_roles = guild.get_member(member.id)
                if target_member_for_roles:
                    await self.handle_level_up(target_member_for_roles.id, new_level)
                else: # Member might not be in the primary configured guild if it's a global bot
                    print(f"Konnte Nutzer {member.id} nicht in Guild {guild.id} für Level-Up-Rolle finden nach givexp.")
            else:
                print("Keine Guild-Informationen für Level-Up-Nachricht/Rolle nach givexp verfügbar.")

    @app_commands.command(name="daily", description="Beanspruche deine tägliche XP-Belohnung.")
    async def daily_command(self, interaction: discord.Interaction) -> None:
        user_id = interaction.user.id

        can_claim, time_remaining = leveling.can_claim_daily(user_id)

        if not can_claim and time_remaining is not None:
            hours, remainder = divmod(int(time_remaining.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            await interaction.response.send_message(
                f"Du hast deine tägliche Belohnung bereits beansprucht. "
                f"Versuche es in {hours}h {minutes}m wieder.",
                ephemeral=True
            )
            return

        level_before = leveling.get_level(user_id)
        xp_gained, new_level = leveling.claim_daily(user_id)

        if xp_gained is None: # Should be caught by can_claim, but as a safeguard
            await interaction.response.send_message(
                "Fehler beim Beanspruchen der täglichen Belohnung. Bist du sicher, dass du warten musstest?",
                ephemeral=True
            )
            return

        message = f"🎉 Du hast deine tägliche Belohnung von {xp_gained} XP erhalten!"
        if new_level > level_before:
            message += f"\nHerzlichen Glückwunsch zum Erreichen von Level {new_level}! 🎉"
            # Announce level up (similar to givexp and on_message)
            if interaction.guild:
                 await self.handle_level_up(user_id, new_level)
                 # handle_level_up sends its own message, so we might not need the one from here
                 # For now, let's keep the interaction response simple.
                 # The handle_level_up will send the main channel message.
            else: # DM context or guild unavailable
                await interaction.user.send(f"Herzlichen Glückwunsch zum Erreichen von Level {new_level} auf einem Server!")


        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="triviapursuit", description="Starte eine Runde Trivia Pursuit und gewinne XP!")
    async def trivia_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "🧠 Das Trivia Pursuit Feature ist noch in Entwicklung! Schau bald wieder vorbei für spannende Quizfragen.",
            ephemeral=True
        )


    async def on_ready(self) -> None:
        print(f"\U0001F389 Eingeloggt als {self.user} (ID: {self.user.id})!")
        print(f"Intents: Members: {self.intents.members}, Message Content: {self.intents.message_content}")

        if not self.intents.members:
            print("\u26A0\uFE0F WARNUNG: 'members' Intent ist nicht aktiviert. Einige Funktionen könnten eingeschränkt sein.")
            print("Bitte aktiviere den 'Privileged Gateway Intent for Server Members' im Discord Developer Portal für deinen Bot.")
        if not self.intents.message_content:
            print("\u26A0\uFE0F WARNUNG: 'message_content' Intent ist nicht aktiviert. XP-Vergabe für Nachrichten könnte fehlschlagen.")
            print("Bitte aktiviere den 'Privileged Gateway Intent for Message Content' im Discord Developer Portal für deinen Bot.")

        app_info = await self.application_info()
        print(f"Bot ist im Besitz von: {app_info.owner}")
        if self.target_guild:
            print(f"Bot operiert primär auf Guild ID: {self.target_guild.id}")
        else:
            print("Bot operiert global (keine spezifische GUILD_ID gesetzt).")


    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        print(f"\U0001F6AB Fehler in App Command: {interaction.command.name if interaction.command else 'Unbekanntes Kommando'}")
        print(f"Fehlertyp: {type(error)}, Fehler: {error}")

        if isinstance(error, app_commands.errors.CommandSignatureMismatch):
            print("\U0001F504 Signaturkonflikt - versuche erneute Synchronisation der Befehle...")
            try:
                await self.tree.sync(guild=self.target_guild)
                print("\u2705 Befehle nach Signaturkonflikt neu synchronisiert.")
                await interaction.response.send_message(
                    "\u26A0\uFE0F Die Befehlsliste wurde gerade aktualisiert. Bitte versuche deinen Befehl erneut.",
                    ephemeral=True,
                )
            except Exception as e:
                print(f"\U0001F525 FEHLER bei der erneuten Synchronisation nach Signaturkonflikt: {e}")
                if interaction.response.is_done():
                    await interaction.followup.send("Ein Fehler ist aufgetreten und die Befehle konnten nicht automatisch aktualisiert werden. Bitte informiere einen Administrator.", ephemeral=True)
                else:
                    await interaction.response.send_message("Ein Fehler ist aufgetreten und die Befehle konnten nicht automatisch aktualisiert werden. Bitte informiere einen Administrator.", ephemeral=True)
            return

        elif isinstance(error, app_commands.errors.MissingPermissions):
            print(f"\U0001F6AB Fehlende Berechtigungen für {interaction.user}: {error.missing_permissions}")
            await interaction.response.send_message(
                f"Du hast nicht die nötigen Berechtigungen ({', '.join(error.missing_permissions)}) für diesen Befehl.",
                ephemeral=True,
            )
            return

        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            print(f"\U0001F975 Befehl auf Cooldown für {interaction.user}: {error.retry_after:.2f}s")
            await interaction.response.send_message(
                f"Dieser Befehl ist noch im Cooldown. Bitte warte {error.retry_after:.2f} Sekunden.",
                ephemeral=True,
            )
            return

        # Fallback für andere AppCommandErrors
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Ups! Etwas ist schiefgelaufen. Bitte versuche es später erneut oder kontaktiere einen Admin.",
                ephemeral=True,
            )
        else: # If response already sent, use followup
             await interaction.followup.send(
                "Ups! Etwas ist schiefgelaufen bei der Verarbeitung nach der ersten Antwort.",
                ephemeral=True,
            )

        # Raise für detaillierteres Logging in der Konsole, wenn nicht bereits behandelt
        # raise error # Kann man einkommentieren für Tracebacks in der Konsole

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        await self.process_xp(message.author.id, base_xp=10)
        print(f"\U0001F4AC Nachricht von {message.author.display_name} gezählt")
        new_badges = badges.increment_messages(message.author.id)
        for bid in new_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            print(f"\U0001F3C6 Neuer Badge für {message.author.display_name}: {badge.name}")
            await message.author.send(
                f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}'
            )
        await self.process_commands(message)

    async def on_reaction_add(
        self, reaction: discord.Reaction, user: discord.User
    ) -> None:
        if user.bot or not reaction.message.guild:
            return
        await self.process_xp(user.id, base_xp=2)
        print(f"\U0001F44D Reaktion von {user.display_name} gezählt")
        new_badges = badges.increment_reaction_given(user.id)
        for bid in new_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            print(f"\U0001F3C6 Neuer Badge für {user.display_name}: {badge.name}")
            await user.send(
                f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}'
            )
        # bonus XP if message gets popular
        if reaction.count in {3, 5, 10}:
            await self.process_xp(reaction.message.author.id, base_xp=5)
        author_badges = badges.increment_reaction_received(reaction.message.author.id)
        for bid in author_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            member = reaction.message.guild.get_member(reaction.message.author.id)
            if member:
                print(f"\U0001F3C6 Neuer Badge für {member.display_name}: {badge.name}")
                await member.send(
                    f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}'
                )

    async def process_xp(self, user_id: int, base_xp: int) -> None:
        """Add XP with a short cooldown."""
        now = datetime.utcnow()
        cooldown_end = self.cooldowns.get(user_id, now - timedelta(seconds=1))
        if now < cooldown_end:
            return
        self.cooldowns[user_id] = now + timedelta(seconds=60)
        level_before = leveling.get_level(user_id)
        new_level = leveling.add_xp(user_id, base_xp)
        print(f"\u2728 {user_id} erhält {base_xp} XP")
        if new_level > level_before:
            await self.handle_level_up(user_id, new_level)

    async def handle_level_up(self, user_id: int, level: int) -> None:
        guild = self.get_guild(self.config["guild_id"])
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return
        role_id = self.config.get("role_rewards", {}).get(str(level))
        if role_id:
            role = guild.get_role(role_id)
            if role:
                await member.add_roles(role)
        print(f"\U0001F973 {member.display_name} erreicht Level {level}")
        channel = member.guild.system_channel or member.guild.text_channels[0]
        await channel.send(
            f"Glückwunsch {member.mention}, du bist jetzt Level {level}!"
        )

    @app_commands.command(
        name="start", description="Zeigt eine Begrüßungsnachricht an."
    )
    async def start_command(self, interaction: discord.Interaction) -> None:
        """Simple command to confirm the bot is running."""
        await interaction.response.send_message("Levelbot bereit!", ephemeral=True)

    @app_commands.command(description="Zeigt deine aktuelle Rank-Card.")
    async def rank(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user
        xp, level_, next_level_xp = leveling.get_user_data(member.id)
        card = await create_rank_card(member, xp, level_, next_level_xp)
        await interaction.response.send_message(
            file=discord.File(card, filename="rank.png")
        )

    @app_commands.command(description="Zeigt das Server-Leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "Dieser Befehl kann nur auf einem Server verwendet werden.", ephemeral=True
            )
            return

        top_users_data = leveling.get_top_users(10)
        embed = discord.Embed(title="🏆 Community Leaderboard", color=discord.Color.gold())

        if not top_users_data:
            embed.description = "Noch niemand auf dem Leaderboard. Sei der Erste!"
            await interaction.response.send_message(embed=embed)
            return

        for idx, (user_id, xp) in enumerate(top_users_data, start=1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            avatar_url = member.avatar.url if member and member.avatar else (member.default_avatar.url if member else "")

            current_level = leveling.calculate_level(xp)
            xp_for_current_level = current_level * leveling.XP_PER_LEVEL
            xp_in_current_level = xp - xp_for_current_level
            next_level_xp_total = leveling.xp_for_next_level(current_level)
            xp_needed_for_next_level = leveling.XP_PER_LEVEL

            progress_percent = (xp_in_current_level / xp_needed_for_next_level) * 100 if xp_needed_for_next_level > 0 else 0

            field_name = f"{idx}. {name}"
            field_value = (
                f"**Level {current_level}** ({xp} XP)\n"
                f"Fortschritt: {xp_in_current_level}/{xp_needed_for_next_level} XP ({progress_percent:.1f}%)\n"
            )
            embed.add_field(name=field_name, value=field_value, inline=False)
            if idx == 1 and avatar_url: # Set top user's avatar as thumbnail
                embed.set_thumbnail(url=avatar_url)
            elif not embed.thumbnail and avatar_url: # Fallback thumbnail if top user has no avatar
                 embed.set_thumbnail(url=avatar_url)


        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="badges", description="Zeigt die verdienten Abzeichen.")
    async def badges_command(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user
        user_badges_ids = badges.get_user_badges(member.id)

        embed = discord.Embed(
            title=f"🏅 Abzeichen von {member.display_name}",
            color=discord.Color.blue()
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        if not user_badges_ids:
            embed.description = "Noch keine Abzeichen gesammelt. Zeit aktiv zu werden!"
        else:
            badge_fields = []
            for bid in user_badges_ids:
                b = badges.BADGE_DEFINITIONS[bid]
                badge_fields.append(f"{b.icon} **{b.name}**: {b.description}")
            embed.description = "\n".join(badge_fields)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Zeigt dein Profil inklusive Abzeichen.")
    async def profile(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user
        xp, level_, next_level_xp = leveling.get_user_data(member.id)
        card = await create_rank_card(member, xp, level_, next_level_xp)
        embed = discord.Embed(title=f"Profil von {member.display_name}")
        embed.set_image(url="attachment://rank.png")
        badge_ids = badges.get_user_badges(member.id)
        if badge_ids:
            icons = " ".join(badges.BADGE_DEFINITIONS[b].icon for b in badge_ids)
            embed.add_field(name="Abzeichen", value=icons, inline=False)
        await interaction.response.send_message(
            embed=embed, file=discord.File(card, filename="rank.png")
        )

    @tasks.loop(minutes=5)
    async def keep_alive(self) -> None:
        """Periodic task to show the bot is still running."""
        print("\U0001F49A Bot lebt")

    @tasks.loop(hours=24)
    async def daily_reset(self) -> None:
        """Example scheduled task for events/challenges."""
        print("\U0001F552 Tagesreset")
        leveling.new_day()

    async def close(self) -> None:
        """Shut down the bot and cancel background tasks."""
        self.keep_alive.cancel()
        await super().close()


if __name__ == "__main__":
    main()
