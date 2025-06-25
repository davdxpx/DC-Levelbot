"""Discord level bot main entry point."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

import leveling
from rank_card import create_rank_card
import badges

CONFIG_PATH = Path('config.json')


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'token': 'YOUR_BOT_TOKEN_HERE',
        'guild_id': 0,
        'role_rewards': {
            '5': 123456789012345678,
            '10': 234567890123456789
        }
    }


def main() -> None:
    config = load_config()
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = LevelBot(command_prefix='!', intents=intents, config=config)
    bot.run(config['token'])


class LevelBot(commands.Bot):
    """A Discord bot that manages user XP and levels."""

    def __init__(self, command_prefix: str, intents: discord.Intents, config: dict):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.config = config
        self.cooldowns: dict[int, datetime] = {}
        self.tree.add_command(self.rank)
        self.tree.add_command(self.leaderboard)
        self.tree.add_command(self.badges_command)
        self.tree.add_command(self.profile)
        self.daily_reset.start()

    async def setup_hook(self) -> None:
        guild_id = self.config.get('guild_id')
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        print(f'Logged in as {self.user}!')

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        await self.process_xp(message.author.id, base_xp=10)
        new_badges = badges.increment_messages(message.author.id)
        for bid in new_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            await message.author.send(f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}')
        await self.process_commands(message)

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User) -> None:
        if user.bot or not reaction.message.guild:
            return
        await self.process_xp(user.id, base_xp=2)
        new_badges = badges.increment_reaction_given(user.id)
        for bid in new_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            await user.send(f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}')
        # bonus XP if message gets popular
        if reaction.count in {3, 5, 10}:
            await self.process_xp(reaction.message.author.id, base_xp=5)
        author_badges = badges.increment_reaction_received(reaction.message.author.id)
        for bid in author_badges:
            badge = badges.BADGE_DEFINITIONS[bid]
            member = reaction.message.guild.get_member(reaction.message.author.id)
            if member:
                await member.send(f'\u2728 Du hast das Abzeichen "{badge.name}" erhalten! {badge.icon}')

    async def process_xp(self, user_id: int, base_xp: int) -> None:
        """Add XP with a short cooldown."""
        now = datetime.utcnow()
        cooldown_end = self.cooldowns.get(user_id, now - timedelta(seconds=1))
        if now < cooldown_end:
            return
        self.cooldowns[user_id] = now + timedelta(seconds=60)
        level_before = leveling.get_level(user_id)
        new_level = leveling.add_xp(user_id, base_xp)
        if new_level > level_before:
            await self.handle_level_up(user_id, new_level)

    async def handle_level_up(self, user_id: int, level: int) -> None:
        guild = self.get_guild(self.config['guild_id'])
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return
        role_id = self.config.get('role_rewards', {}).get(str(level))
        if role_id:
            role = guild.get_role(role_id)
            if role:
                await member.add_roles(role)
        channel = member.guild.system_channel or member.guild.text_channels[0]
        await channel.send(f'Glückwunsch {member.mention}, du bist jetzt Level {level}!')

    @app_commands.command(description='Zeigt deine aktuelle Rank-Card.')
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        xp, level_, next_level_xp = leveling.get_user_data(member.id)
        card = await create_rank_card(member, xp, level_, next_level_xp)
        await interaction.response.send_message(file=discord.File(card, filename='rank.png'))

    @app_commands.command(description='Zeigt das Server-Leaderboard.')
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        top = leveling.get_top_users(10)
        embed = discord.Embed(title='🏆 Community Leaderboard')
        for idx, (user_id, xp) in enumerate(top, start=1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f'User {user_id}'
            level_ = leveling.calculate_level(xp)
            embed.add_field(name=f'{idx}. {name}', value=f'Level {level_} ({xp} XP)', inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='badges', description='Zeigt die verdienten Abzeichen.')
    async def badges_command(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        badge_ids = badges.get_user_badges(member.id)
        embed = discord.Embed(title=f'Abzeichen von {member.display_name}')
        if not badge_ids:
            embed.description = 'Noch keine Abzeichen.'
        else:
            for bid in badge_ids:
                b = badges.BADGE_DEFINITIONS[bid]
                embed.add_field(name=f"{b.icon} {b.name}", value=b.description, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description='Zeigt dein Profil inklusive Abzeichen.')
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        xp, level_, next_level_xp = leveling.get_user_data(member.id)
        card = await create_rank_card(member, xp, level_, next_level_xp)
        embed = discord.Embed(title=f'Profil von {member.display_name}')
        embed.set_image(url='attachment://rank.png')
        badge_ids = badges.get_user_badges(member.id)
        if badge_ids:
            icons = ' '.join(badges.BADGE_DEFINITIONS[b].icon for b in badge_ids)
            embed.add_field(name='Abzeichen', value=icons, inline=False)
        await interaction.response.send_message(embed=embed, file=discord.File(card, filename='rank.png'))

    @tasks.loop(hours=24)
    async def daily_reset(self) -> None:
        """Example scheduled task for events/challenges."""
        leveling.new_day()


if __name__ == '__main__':
    main()
