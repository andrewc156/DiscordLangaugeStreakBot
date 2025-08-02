"""
Main entrypoint for the Discord streak bot.

This module creates and configures a Discord bot that listens for messages
beginning with ``Streak:`` in a designated channel. When such a message is
detected, the bot records the user’s streak on that server, incrementing or
resetting it depending on the date. The bot also exposes a few commands for
administrators and regular users alike:

* ``!set`` – Administrators use this to designate the current channel as
  the streak channel. Only one streak channel can exist per guild.
* ``!streak`` – Replies with the author’s current streak in the guild.
* ``!leaderboard`` – Displays the top streak holders for the guild.
* ``!help`` – Lists the available commands and their descriptions.

The bot reads its authentication token from a file under ``secrets/``. See
``secrets/README.md`` for details on how to supply the token.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import List, Tuple

import discord
from discord.ext import commands, tasks

from streak_manager import StreakManager


def load_token(token_path: str | None = None) -> str:
    """Retrieve the Discord bot token.

    The bot first checks the environment variable ``DISCORD_TOKEN``. If it
    exists and is non‑empty, its value is returned. Otherwise, if
    ``token_path`` is provided, the function attempts to read the token
    from that file. A ``FileNotFoundError`` or ``ValueError`` is raised
    if no token can be found.

    Args:
        token_path: Optional path to a token file. If ``None``, the file
            will not be checked and only the environment variable will be
            used.

    Returns:
        The Discord bot token as a string.
    """
    # First preference: environment variable
    env_token = os.environ.get("DISCORD_TOKEN")
    if env_token:
        return env_token.strip()

    # Fall back to file on disk if provided
    if token_path:
        if not os.path.exists(token_path):
            raise FileNotFoundError(
                f"Token file not found at {token_path}. Please set the DISCORD_TOKEN environment variable or create the file."
            )
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if not token:
            raise ValueError(
                f"Token file at {token_path} is empty. Provide your Discord bot token via the DISCORD_TOKEN environment variable or in this file."
            )
        return token

    # If neither is available, raise an error
    raise ValueError(
        "No Discord token provided. Set the DISCORD_TOKEN environment variable or provide a token file."
    )


async def main() -> None:
    """Entry point for running the bot."""
    # Initialise streak manager. All file I/O happens within this helper
    # class to keep bot.py focused on Discord interactions.
    data_file = os.environ.get("STREAK_DB_FILE", "database.json")
    streak_manager = StreakManager(data_file)
    await streak_manager.load_data()

    # We need the MESSAGE CONTENT intent enabled to read user messages.
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    # Remove the default help command so we can override it
    bot.remove_command("help")

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user} (ID: {bot.user.id})")
        print("------")
        # Start the cleanup task after the bot is ready
        try:
            cleanup_inactive_roles.start()
        except RuntimeError:
            # Task has already been started
            pass

    # Background task to remove streak roles from inactive users
    @tasks.loop(hours=24)
    async def cleanup_inactive_roles() -> None:
        """Daily task that scans for users inactive for more than a week and removes their streak roles."""
        now = datetime.now(timezone.utc).date()
        # Iterate over a copy of guild IDs to avoid mutation issues
        async with streak_manager._lock:
            guild_ids = list(streak_manager._data.get("guilds", {}).keys())
        for guild_id in guild_ids:
            guild_obj = bot.get_guild(int(guild_id))
            if guild_obj is None:
                continue
            # Get rewards mapping for this guild
            rewards = await streak_manager.get_role_rewards(guild_id)
            if not rewards:
                continue
            # Determine roles to potentially remove
            role_ids = [int(role_id) for role_id in rewards.values()]
            # For each user, check inactivity
            async with streak_manager._lock:
                users_data = streak_manager._data["guilds"][guild_id].get("users", {}).copy()
            for user_id, data in users_data.items():
                last_date = data.get("last_date")
                if not last_date:
                    continue
                try:
                    from datetime import date
                    last = date.fromisoformat(last_date)
                    diff = (now - last).days
                except Exception:
                    continue
                if diff > 7:
                    member = guild_obj.get_member(int(user_id))
                    if not member:
                        continue
                    # Remove all reward roles the member currently has
                    roles_to_remove = [guild_obj.get_role(rid) for rid in role_ids if guild_obj.get_role(rid) in member.roles]
                    if roles_to_remove:
                        try:
                            await member.remove_roles(*roles_to_remove, reason="Streak inactivity")
                        except Exception as e:
                            print(f"Error removing roles from {member}: {e}")

    @cleanup_inactive_roles.before_loop
    async def before_cleanup() -> None:
        # Wait until the bot is connected and ready before starting the loop
        await bot.wait_until_ready()


    @bot.event
    async def on_message(message: discord.Message):
        # Ignore messages from bots
        if message.author.bot:
            return

        # Let commands process first
        await bot.process_commands(message)

        # Only operate in guilds
        if message.guild is None:
            return

        # Check if this guild has a streak channel configured
        guild_id = str(message.guild.id)
        channel_id = await streak_manager.get_streak_channel(guild_id)
        if channel_id is None:
            return

        # Ensure we only act in the configured channel
        if str(message.channel.id) != channel_id:
            return

        # Case-insensitive check for messages starting with "Streak:"
        content = message.content.lstrip()
        if not content.lower().startswith("streak:"):
            return

        # Record the streak for the user
        today = datetime.now(timezone.utc).date().isoformat()
        user_id = str(message.author.id)
        streak_count = await streak_manager.record_streak(guild_id, user_id, today)

        # Check for role rewards
        try:
            # Determine rewards configured for this guild
            rewards = await streak_manager.get_role_rewards(guild_id)
            if rewards:
                # Determine which rewards the user qualifies for
                member = message.guild.get_member(int(user_id))
                if member:
                    roles_to_add = []
                    for days_threshold, role_id in rewards.items():
                        if streak_count >= days_threshold:
                            role = message.guild.get_role(int(role_id))
                            if role and role not in member.roles:
                                roles_to_add.append(role)
                    if roles_to_add:
                        await member.add_roles(*roles_to_add, reason="Streak reward")
        except Exception as e:
            # Catch and log exceptions silently to avoid crashing the bot
            print(f"Error assigning roles: {e}")

        # Respond with an encouraging message
        try:
            await message.reply(
                f"Great job {message.author.mention}! Your streak is now {streak_count} day{'s' if streak_count != 1 else ''}!"
            )
        except discord.Forbidden:
            # If we can't reply (due to permissions), silently ignore
            pass

    @bot.command(name="set", help="Set this channel as the streak channel. Admin only.")
    @commands.has_permissions(administrator=True)
    async def set_channel(ctx: commands.Context) -> None:
        guild_id = str(ctx.guild.id)
        channel_id = str(ctx.channel.id)
        await streak_manager.set_streak_channel(guild_id, channel_id)
        await ctx.send("This channel is now the streak channel!")

    @set_channel.error
    async def set_channel_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an administrator to set the streak channel.")
        else:
            await ctx.send("An error occurred while setting the streak channel.")

    @bot.command(name="streak", help="Show your current streak in this server.")
    async def get_streak(ctx: commands.Context) -> None:
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)
        streak = await streak_manager.get_user_streak(guild_id, user_id)
        if streak <= 0:
            await ctx.send(
                f"{ctx.author.mention}, you don't have a streak yet. Post a message starting with 'Streak:' in the designated channel to begin!"
            )
        else:
            await ctx.send(
                f"{ctx.author.mention}, your current streak is {streak} day{'s' if streak != 1 else ''}. Keep it up!"
            )

    @bot.command(name="unset", help="Unset the streak channel for this server. Admin only.")
    @commands.has_permissions(administrator=True)
    async def unset_channel(ctx: commands.Context) -> None:
        guild_id = str(ctx.guild.id)
        await streak_manager.unset_streak_channel(guild_id)
        await ctx.send("The streak channel has been unset for this server.")

    @unset_channel.error
    async def unset_channel_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an administrator to unset the streak channel.")
        else:
            await ctx.send("An error occurred while unsetting the streak channel.")

    @bot.command(name="reset", help="Admin command to reset a user's streak.")
    @commands.has_permissions(administrator=True)
    async def reset_streak(ctx: commands.Context, member: discord.Member) -> None:
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)
        await streak_manager.remove_user_streak(guild_id, user_id)
        await ctx.send(f"{member.display_name}'s streak has been reset.")

    @reset_streak.error
    async def reset_streak_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: !reset @user")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an administrator to reset streaks.")
        else:
            await ctx.send("An error occurred while resetting the streak.")

    @bot.command(name="addrole", help="Admin command to assign a role reward: !addrole <days> <role>")
    @commands.has_permissions(administrator=True)
    async def add_role(ctx: commands.Context, days: int, role: discord.Role) -> None:
        if days <= 0:
            await ctx.send("Days must be a positive integer.")
            return
        guild_id = str(ctx.guild.id)
        await streak_manager.set_role_reward(guild_id, days, str(role.id))
        await ctx.send(f"Role reward configured: {role.mention} for a {days}-day streak.")

    @add_role.error
    async def add_role_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send("Usage: !addrole <days> <@role>")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an administrator to configure role rewards.")
        else:
            await ctx.send("An error occurred while configuring role rewards.")

    @bot.command(name="removerole", help="Admin command to remove a role reward: !removerole <days>")
    @commands.has_permissions(administrator=True)
    async def remove_role(ctx: commands.Context, days: int) -> None:
        guild_id = str(ctx.guild.id)
        await streak_manager.remove_role_reward(guild_id, days)
        await ctx.send(f"Removed role reward for a {days}-day streak, if it existed.")

    @remove_role.error
    async def remove_role_error(ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.BadArgument):
            await ctx.send("Usage: !removerole <days>")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You need to be an administrator to remove role rewards.")
        else:
            await ctx.send("An error occurred while removing role rewards.")

    @bot.command(name="listroles", help="List configured role rewards for this server.")
    async def list_roles(ctx: commands.Context) -> None:
        guild_id = str(ctx.guild.id)
        rewards = await streak_manager.get_role_rewards(guild_id)
        if not rewards:
            await ctx.send("No role rewards have been configured.")
            return
        lines = []
        for days, role_id in sorted(rewards.items()):
            role = ctx.guild.get_role(int(role_id))
            role_name = role.name if role else f"Role {role_id}"
            lines.append(f"{days} day{'s' if days != 1 else ''} → {role_name}")
        await ctx.send("**Role Rewards:**\n" + "\n".join(lines))


    @bot.command(name="leaderboard", help="Show the streak leaderboard for this server.")
    async def leaderboard(ctx: commands.Context) -> None:
        guild_id = str(ctx.guild.id)
        leaderboard_data: List[Tuple[str, int]] = await streak_manager.get_leaderboard(guild_id)
        if not leaderboard_data:
            await ctx.send("No one has started a streak yet. Be the first by posting in the streak channel!")
            return

        # Build a leaderboard message. Only show top 10 to avoid spamming huge lists.
        lines = []
        for idx, (user_id, streak) in enumerate(leaderboard_data[:10], start=1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"User {user_id}"
            lines.append(f"{idx}. {name} – {streak} day{'s' if streak != 1 else ''}")
        leaderboard_text = "\n".join(lines)
        await ctx.send(f"**Streak Leaderboard:**\n{leaderboard_text}")

    @bot.command(name="help", help="Show help for the bot.")
    async def help_command(ctx: commands.Context) -> None:
        help_lines = [
            "**Streak Bot Commands**",
            "`!set` – Set this channel as the streak channel (admin only)",
            "`!streak` – Show your current streak in this server",
            "`!leaderboard` – Show the server's streak leaderboard",
            "`!reset @user` – Reset a member's streak (admin only)",
            "`!unset` – Unset the streak channel for this server (admin only)",
            "`!addrole <days> <@role>` – Award a role when members reach a streak of `<days>` (admin only)",
            "`!removerole <days>` – Remove the role reward for a specific streak length (admin only)",
            "`!listroles` – List configured role rewards for this server",
            "`!help` – Show this help message",
        ]
        await ctx.send("\n".join(help_lines))

    # Load the token and run the bot
    token_path = os.environ.get("DISCORD_TOKEN_FILE", os.path.join("secrets", "discord_token.txt"))
    token = load_token(token_path)
    await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass