FROM python:3.12-slim

# Install Chrome and required dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    xvfb \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 appuser

# Set up Chrome Driver
RUN CHROME_DRIVER_VERSION=`curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
    wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
    rm /tmp/chromedriver.zip && \
    chmod +x /usr/local/bin/chromedriver

WORKDIR /app

# Create necessary directories with correct permissions
RUN mkdir -p /app/data /app/screenshots /app/.wdm /home/appuser/.cache \
    && chown -R appuser:appuser /app /home/appuser/.cache \
    && chmod -R 755 /app /home/appuser/.cache

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .
RUN chown -R appuser:appuser /app

# Switch to appuser
USER appuser

# Set environment variables
ENV HOME=/home/appuser \
    PATH="/usr/local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    WDM_LOCAL=1 \
    WDM_CACHE_DIR=/app/.wdm

# Create xvfb wrapper script
RUN echo '#!/bin/bash\nxvfb-run -a --server-args="-screen 0 1920x1080x24 -ac" "$@"' > /app/xvfb-run.sh \
    && chmod +x /app/xvfb-run.sh

CMD ["python", "bot.py"]
