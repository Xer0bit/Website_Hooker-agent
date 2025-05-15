FROM python:3.12-slim

# Install Chrome and required dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up Chrome Driver
RUN CHROME_DRIVER_VERSION=`curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE` && \
    wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/bin && \
    rm /tmp/chromedriver.zip && \
    chmod +x /usr/bin/chromedriver

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install  -r requirements.txt

# Copy the rest of the application
COPY . .

# Create app directories
RUN mkdir -p /app/data /app/screenshots /app/.wdm \
    && chown -R 1000:1000 /app \
    && chmod -R 755 /app

# Switch to non-root user
USER 1000:1000

CMD ["python", "bot.py"]
