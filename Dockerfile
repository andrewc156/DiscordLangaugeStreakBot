# ---- base image ----
FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (leverages Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY bot.py streak_manager.py README.md ./

# (Optional)—create a non-root user for security on Heroku
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Heroku passes DISCORD_TOKEN via env vars; no volumes needed
CMD ["python", "bot.py"]
