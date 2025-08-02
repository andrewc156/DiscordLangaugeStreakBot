# Discord Streak Bot

This project implements a multi‑server **Japanese learning streak bot** for
Discord. Users can keep track of their daily study progress simply by
posting messages beginning with `Streak:` in a dedicated channel. The bot
records each user’s streak, responds with encouraging messages, and
provides simple commands to view individual progress or the server
leaderboard.

## Features

* **Multi‑server support** – Each guild (server) can configure its own
  streak channel without interfering with others.
* **Automatic streak tracking** – Users post messages that start with
  `Streak:` and the bot automatically updates their streak for that day.
* **Commands**:
  * `!set` – Set the current channel as the streak channel (admin only).
  * `!streak` – Display your current streak in the server.
  * `!leaderboard` – Show the top streaks in the server.
  * `!reset @member` – Reset a member’s streak (admin only).
  * `!unset` – Unset the streak channel (admin only).
  * `!addrole <days> <@role>` – Configure a role reward (admin only).
  * `!removerole <days>` – Remove a configured role reward (admin only).
  * `!listroles` – List role rewards configured for the server.
  * `!help` – List available commands and their descriptions.
* **Persistent storage** – All data is stored in a JSON file so that
  streaks and configuration persist across restarts.
* **Secrets management** – The bot token can be supplied either via an
  environment variable (`DISCORD_TOKEN`) or read from
  `secrets/discord_token.txt` at runtime. Both methods allow easy
  integration with hosting providers like Fly.io. Never commit your
  token to version control.
* **Docker‑ready** – Includes a `Dockerfile` and `docker-compose.yml` for
  easy deployment.

### New in this version

* **Administrative streak reset** – Administrators can reset a member’s
  streak with `!reset @member`.
* **Role rewards** – Administrators can configure role rewards that are
  automatically granted when a member reaches a specified streak length.
  Use `!addrole <days> <@role>` to set a reward and `!removerole <days>`
  to remove it. Members can view configured rewards with `!listroles`.
* **Role removal on inactivity** – If a member goes more than a week
  without logging a streak (no messages starting with `Streak:`), any
  role rewards they earned are automatically removed. Their streak
  remains recorded but roles must be re‑earned.

## Getting Started

### Prerequisites

* Python 3.10 or higher
* A Discord bot token

### Local Installation

1. **Clone the repository**

   ```sh
   git clone <repo-url>
   cd discord-streak-bot
   ```

2. **Create a virtual environment (optional but recommended)**

   ```sh
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```sh
   pip install -r requirements.txt
   ```

4. **Configure your bot token**

   You can provide your Discord bot token in one of two ways:

   * **Environment variable** – Set the `DISCORD_TOKEN` environment
     variable before running the bot. This method is ideal for hosted
     environments like Fly.io where you can configure secrets via the
     platform. For example:

     ```sh
     export DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
     ```

   * **Secrets directory** – Alternatively, create the `secrets` directory
     (if it does not exist) and save your token in
     `secrets/discord_token.txt`:

     ```sh
     mkdir -p secrets
     echo "YOUR_BOT_TOKEN_HERE" > secrets/discord_token.txt
     ```

   **Never** commit your token to version control. It grants full
   control over your bot.

5. **Run the bot**

   ```sh
   python bot.py
   ```

The bot will connect to Discord and begin listening for streak messages
and commands.

### Docker Deployment

To deploy the bot using Docker, you can use the provided
`Dockerfile` and `docker-compose.yml`. This configuration builds a
lightweight container and mounts the secrets directory for your bot
token.

1. **Add your bot token**

   Place your bot token in `secrets/discord_token.txt` as described
   above.

2. **Build the image**

   ```sh
   docker compose build
   ```

3. **Start the bot**

   ```sh
   docker compose up -d
   ```

The `docker-compose.yml` includes `restart: unless-stopped`, so the bot
will automatically restart on failure. Logs are output to the
container’s stdout; you can follow them with `docker compose logs -f`.

### Updating the Bot

To update the bot code with zero downtime, build and deploy a new
container image then perform a rolling restart.

```sh
docker compose pull            # Pull updated image if using a registry
docker compose up -d --build   # Build a new image from local source
```

Docker Compose will recreate the container with the new image while
preserving mounted volumes, including the database file and secrets.

If you plan to deploy the bot on **Fly.io**, use the platform’s
secret management to supply the token as an environment variable
instead of mounting a file. For example, you can set the token with

```sh
fly secrets set DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
```

The bot automatically reads the `DISCORD_TOKEN` environment variable at
runtime.

## Usage

1. **Set up a streak channel**: An administrator should run `!set` in
   the chosen channel. This tells the bot where to listen for streak
   messages.
2. **Start your streak**: Members post a message starting with
   `Streak:` each day they study or practice Japanese. Only one entry
   per day counts toward the streak.
3. **Check your progress**: Use `!streak` to see your current streak
   within the server.
4. **View the leaderboard**: Use `!leaderboard` to see who has the
   longest streaks in the server.

5. **Reset a streak**: Administrators can reset another member’s streak
   with `!reset @member`.

6. **Unset the streak channel**: Administrators can clear the streak
   channel configuration with `!unset`. After unsetting, the bot will
   ignore streak posts until a channel is set again with `!set`.

7. **Configure role rewards**: Administrators can award roles based on
   streak length with `!addrole <days> <@role>`. For example,
   `!addrole 10 @Dedicated` will give members the `Dedicated` role when
   they reach a 10‑day streak. Remove a reward with
   `!removerole <days>`, and list all rewards with `!listroles`.

8. **Inactivity cleanup**: If members do not log a streak for more
   than 7 days, any roles awarded for streaks are automatically
   removed. Their streak counter remains and they can re‑earn roles by
   logging streaks again.

## Project Structure

```
discord-streak-bot/
│
├─ bot.py                # Main bot logic and command definitions
├─ streak_manager.py     # Persistence layer for streaks and server configs
├─ database.json         # JSON storage for all guilds’ streak data
├─ requirements.txt       # Python dependencies
│
├─ Dockerfile
├─ docker-compose.yml
│
├─ secrets/
│   ├─ discord_token.txt  # Place your bot token here (ignored in Git)
│   └─ README.md          # Instructions for adding your token
│
└─ README.md             # This file
```

## Contributing

If you wish to extend or improve the bot, feel free to open an issue
or submit a pull request. Suggestions and bug reports are welcome.

## License

This project is provided under the MIT License. See the `LICENSE` file
for details.