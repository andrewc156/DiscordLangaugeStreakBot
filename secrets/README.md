# Secrets Directory

This folder holds sensitive information that should **never** be committed to
source control. The Discord bot reads its authentication token from
`discord_token.txt` located inside this folder. When running the bot
locally or in a container, mount the `secrets` directory and place your
token inside `discord_token.txt`.

## Adding Your Discord Token

1. Create a new Discord application and bot via the [Discord Developer
   Portal](https://discord.com/developers/applications). Copy the bot
   token from the bot tab.
2. Create a file named `discord_token.txt` in this `secrets` directory.
3. Paste your bot token into `discord_token.txt`. Ensure there are no
   leading or trailing spaces or newlines.

The token file is ignored by version control (see `.gitignore`) to
prevent accidental leakage.