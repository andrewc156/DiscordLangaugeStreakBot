"""
Streak management module.

This module encapsulates reading and writing streak data to persistent
storage. Each guild can define its own streak channel and maintain its
own set of user streaks. Data is stored in a JSON file on disk. The
structure of the JSON file resembles::

    {
        "guilds": {
            "<guild_id>": {
                "streak_channel_id": "<channel_id>",
                "users": {
                    "<user_id>": {
                        "streak": <int>,
                        "last_date": "YYYY-MM-DD"
                    },
                    ...
                }
            },
            ...
        }
    }

All operations that modify the in-memory data structure are guarded by
an ``asyncio.Lock`` to prevent concurrent writes. Public methods on
``StreakManager`` are ``async`` where necessary because they may
perform file I/O or acquire the lock.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List, Optional, Tuple


class StreakManager:
    """Encapsulates reading, writing, and updating streak data."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._data: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def load_data(self) -> None:
        """Load streak data from the JSON file.

        If the file does not exist, it will be created on the first
        save. If the file contains invalid JSON, an empty data
        structure is used and the original file is left untouched.
        """
        async with self._lock:
            if not os.path.exists(self.file_path):
                # initialise base structure
                self._data = {"guilds": {}}
                return
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # Ensure keys exist
                if "guilds" not in self._data or not isinstance(self._data["guilds"], dict):
                    self._data = {"guilds": {}}
            except (json.JSONDecodeError, OSError):
                self._data = {"guilds": {}}

    async def _save_data(self) -> None:
        """Write the in-memory data back to disk."""
        # Acquire lock to ensure exclusive access to _data during write
        async with self._lock:
            # Make sure directory exists
            os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
            # Write to a temporary file and atomically replace the original
            tmp_path = self.file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file_path)

    async def ensure_guild(self, guild_id: str) -> None:
        """Ensure the guild data structure exists in memory."""
        async with self._lock:
            if "guilds" not in self._data:
                self._data["guilds"] = {}
            if guild_id not in self._data["guilds"]:
                self._data["guilds"][guild_id] = {
                    "streak_channel_id": None,
                    "users": {},
                    # role_rewards maps a stringified day threshold to a role ID
                    # for example: {"10": "123456789"}
                    "role_rewards": {},
                }

    async def set_streak_channel(self, guild_id: str, channel_id: str) -> None:
        """Set the streak channel for a guild.

        Args:
            guild_id: The ID of the guild.
            channel_id: The ID of the channel to use for streak logging.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            self._data["guilds"][guild_id]["streak_channel_id"] = channel_id
        await self._save_data()

    async def unset_streak_channel(self, guild_id: str) -> None:
        """Clear the streak channel configuration for a guild.

        Args:
            guild_id: The ID of the guild.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            self._data["guilds"][guild_id]["streak_channel_id"] = None
        await self._save_data()

    async def get_streak_channel(self, guild_id: str) -> Optional[str]:
        """Retrieve the streak channel ID for a guild.

        Args:
            guild_id: The ID of the guild.

        Returns:
            The channel ID as a string, or ``None`` if not set.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            return self._data["guilds"][guild_id].get("streak_channel_id")

    async def record_streak(self, guild_id: str, user_id: str, current_date: str) -> int:
        """Record a streak entry for a user.

        Updates the user’s streak if the entry is new or resets it if
        there was a gap. Returns the updated streak count.

        Args:
            guild_id: The ID of the guild.
            user_id: The ID of the user.
            current_date: ISO formatted date string (YYYY-MM-DD).

        Returns:
            The user's updated streak count.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            guild_data = self._data["guilds"][guild_id]
            users = guild_data.setdefault("users", {})
            user_data = users.setdefault(user_id, {"streak": 0, "last_date": None})
            last_date = user_data.get("last_date")
            # Determine streak logic
            if last_date == current_date:
                # Already recorded for today; no change
                streak = user_data["streak"]
            else:
                # Determine if the last recorded date was yesterday
                if last_date:
                    # Compare ISO date strings lexically; safe because format is YYYY-MM-DD
                    # Determine difference by converting to ints
                    try:
                        from datetime import date

                        last = date.fromisoformat(last_date)
                        curr = date.fromisoformat(current_date)
                        diff = (curr - last).days
                    except Exception:
                        diff = None
                    if diff == 1:
                        streak = user_data["streak"] + 1
                    else:
                        # Gap of 0 (same day) or >1 resets the streak
                        streak = 1
                else:
                    # First ever entry
                    streak = 1
                # Update user data
                user_data["streak"] = streak
                user_data["last_date"] = current_date
            # Save changes
            users[user_id] = user_data
        await self._save_data()
        return user_data["streak"]

    async def remove_user_streak(self, guild_id: str, user_id: str) -> None:
        """Reset a user's streak to zero and clear the last recorded date.

        Args:
            guild_id: The ID of the guild.
            user_id: The ID of the user.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            users = self._data["guilds"][guild_id].setdefault("users", {})
            if user_id in users:
                users[user_id]["streak"] = 0
                users[user_id]["last_date"] = None
        await self._save_data()

    async def set_role_reward(self, guild_id: str, days: int, role_id: str) -> None:
        """Assign a role reward for a given streak threshold.

        Args:
            guild_id: The ID of the guild.
            days: The streak length required to obtain the role.
            role_id: The Discord role ID to assign.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            guild_data = self._data["guilds"][guild_id]
            rewards = guild_data.setdefault("role_rewards", {})
            rewards[str(days)] = str(role_id)
        await self._save_data()

    async def remove_role_reward(self, guild_id: str, days: int) -> None:
        """Remove a role reward for a given streak threshold.

        Args:
            guild_id: The ID of the guild.
            days: The streak length whose reward should be removed.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            guild_data = self._data["guilds"][guild_id]
            rewards = guild_data.setdefault("role_rewards", {})
            rewards.pop(str(days), None)
        await self._save_data()

    async def get_role_rewards(self, guild_id: str) -> Dict[int, str]:
        """Retrieve the role rewards mapping for a guild.

        Args:
            guild_id: The ID of the guild.

        Returns:
            A dictionary mapping integer streak thresholds to role IDs.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            guild_data = self._data["guilds"][guild_id]
            rewards = guild_data.get("role_rewards", {})
            # Convert keys to ints for easier comparison
            return {int(k): str(v) for k, v in rewards.items() if k.isdigit()}

    async def get_user_streak(self, guild_id: str, user_id: str) -> int:
        """Retrieve the current streak for a user.

        Args:
            guild_id: The ID of the guild.
            user_id: The ID of the user.

        Returns:
            The streak count, or 0 if the user has no streak.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            users = self._data["guilds"][guild_id].get("users", {})
            user_data = users.get(user_id)
            return int(user_data["streak"]) if user_data else 0

    async def get_leaderboard(self, guild_id: str) -> List[Tuple[str, int]]:
        """Compute the leaderboard for a guild.

        Args:
            guild_id: The ID of the guild.

        Returns:
            A list of tuples ``(user_id, streak)`` sorted in descending order by
            streak. Users with a streak of 0 are excluded.
        """
        await self.ensure_guild(guild_id)
        async with self._lock:
            users = self._data["guilds"][guild_id].get("users", {})
            leaderboard: List[Tuple[str, int]] = [
                (user_id, int(data.get("streak", 0)))
                for user_id, data in users.items()
                if data.get("streak", 0) > 0
            ]
        # Sort outside of the lock to avoid holding lock during comparisons
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        return leaderboard