FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy dependency definitions first to leverage Docker cache
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# Exclude the default database.json from the image so that data persists across
# restarts via a mounted volume. The bot will create the file if it
# doesn't exist.
COPY bot.py streak_manager.py README.md ./

# Create secrets directory placeholder (will be mounted at runtime)
RUN mkdir -p /app/secrets

# The entrypoint executes the bot. The token will be read from
# /app/secrets/discord_token.txt (mounted volume) or as configured
CMD ["python", "bot.py"]