# Website Monitor Discord Bot

A powerful Discord bot for monitoring multiple websites, perfect for companies managing 100+ websites. The bot tracks changes in website content, DNS records, IP addresses, and captures screenshots, providing real-time alerts when changes are detected.

## Features

- 🔍 **Comprehensive Monitoring**
  - Website content changes
  - DNS record changes
  - IP address changes
  - Response time tracking
  - Status code monitoring
  - Screenshot capture
  
- 📊 **Scalable Performance**
  - Handles 100+ websites efficiently
  - Concurrent monitoring
  - Optimized resource usage
  - Docker containerization
  
- 🚨 **Smart Alerts**
  - Real-time change notifications
  - Detailed change descriptions
  - Visual comparisons with screenshots
  - Customizable check intervals
  
- 📱 **User-Friendly Interface**
  - Easy-to-use Discord commands
  - Paginated website listings
  - Detailed status reports
  - Interactive navigation

## Requirements

- Docker and Docker Compose
- Discord Bot Token
- Discord Server with a designated channel for alerts

## Quick Start

1. **Clone the repository:**
   ```powershell
   git clone <repository-url>
   cd Website_Hooker
   ```

2. **Configure the bot:**
   - Copy `.env.example` to `.env`
   - Add your Discord bot token and channel ID:
     ```
     DISCORD_TOKEN=your_discord_bot_token_here
     DISCORD_CHANNEL_ID=your_channel_id_here
     ```

3. **Build and run with Docker:**
   ```powershell
   docker-compose up --build
   ```

## Discord Commands

- `!add [url] [check_interval]` - Add a website to monitor
  - `url`: Website URL
  - `check_interval`: Check interval in minutes (default: 60)
  
- `!remove [url]` - Remove a website from monitoring
  
- `!list` - Show all monitored websites
  - Displays websites in paginated form
  - Shows status and last check time
  
- `!status [url]` - Get detailed status of a specific website
  - Shows IP, DNS, response time, and screenshot
  - Displays any detected changes

## Docker Support

The bot is containerized using Docker for easy deployment and scaling:

```yaml
version: '3.8'
services:
  website-monitor:
    build: .
    volumes:
      - ./screenshots:/app/screenshots
      - ./websites.db:/app/websites.db
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
      - DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
    restart: unless-stopped
```

## Performance Optimizations

1. **Concurrent Monitoring**
   - Asynchronous website checks
   - Parallel processing of multiple websites
   - Efficient resource utilization

2. **Smart Change Detection**
   - Ignores dynamic content
   - Reduces false positives
   - Configurable sensitivity

3. **Resource Management**
   - Automatic cleanup of old screenshots
   - Efficient database operations
   - Memory usage optimization

## Best Practices

1. **Monitoring Intervals**
   - Recommended minimum: 5 minutes
   - High-priority sites: 5-15 minutes
   - Standard sites: 30-60 minutes

2. **Screenshot Management**
   - Screenshots are stored in `./screenshots`
   - Regularly backup important screenshots
   - Old screenshots are automatically cleaned up

3. **Error Handling**
   - Automatic retry on temporary failures
   - Detailed error reporting
   - Graceful degradation

## Troubleshooting

1. **Connection Issues**
   - Check your network connection
   - Verify website accessibility
   - Check DNS configuration

2. **Bot Not Responding**
   - Verify Discord token
   - Check channel permissions
   - Review bot logs

3. **High Resource Usage**
   - Adjust monitoring intervals
   - Reduce concurrent checks
   - Update Docker resources

## License

[MIT License](LICENSE)

## Support

For issues and feature requests, please open an issue on GitHub.
