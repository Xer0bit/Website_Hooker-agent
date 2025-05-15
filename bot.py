import os
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from dotenv import load_dotenv
from modules.website_monitor import WebsiteMonitor
from modules.database import Database
import asyncio
from typing import Optional
import pytz
from collections import Counter

# Load environment variables
load_dotenv()

# Bot setup with increased timeout
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='bito ', intents=intents)  # Note the space after 'bito'

# Initialize database and website monitor
db = Database()
monitor = WebsiteMonitor(db)

# Constants
MAX_WEBSITES_PER_PAGE = 10
EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_ERROR = discord.Color.red()
EMBED_COLOR_INFO = discord.Color.blue()
DEFAULT_CHECK_INTERVAL = 30  # Changed to 30 minutes default
REPORT_HOUR = 5  # UTC time
REPORT_COLOR = discord.Color.gold()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    check_websites.start()
    daily_report.start()  # Start the daily report task

async def send_paginated_embeds(ctx, title: str, items: list, formatter):
    """Send paginated embeds for large datasets"""
    pages = []
    for i in range(0, len(items), MAX_WEBSITES_PER_PAGE):
        chunk = items[i:i + MAX_WEBSITES_PER_PAGE]
        embed = discord.Embed(title=f"{title} (Page {len(pages)+1})", color=EMBED_COLOR_INFO)
        for item in chunk:
            formatter(embed, item)
        pages.append(embed)
    
    if not pages:
        await ctx.send("No items to display.")
        return
        
    current_page = 0
    message = await ctx.send(embed=pages[current_page])
    
    if len(pages) > 1:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"]
            
        while True:
            try:
                reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
                
                if str(reaction.emoji) == "▶️" and current_page < len(pages) - 1:
                    current_page += 1
                    await message.edit(embed=pages[current_page])
                elif str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=pages[current_page])
                    
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                break

@bot.command(name='add', help='Add a website to monitor.\nUsage: bito add <url> [check_interval_in_minutes]\nNote: Full page screenshots will be captured')
@commands.guild_only()
async def add_website(ctx, url: str = commands.parameter(description="Website URL to monitor"), 
                     interval: Optional[int] = commands.parameter(default=60, description="Check interval in minutes")):
    if not url:
        await ctx.send("Please provide a URL to monitor. Usage: !add <url> [check_interval_in_minutes]")
        return
    
    async with ctx.typing():
        try:
            # Validate interval
            if interval < 1:
                await ctx.send("Interval must be at least 1 minute.")
                return
                
            # Add website (removed await since it's no longer async)
            status = monitor.add_website(url, interval)
            
            # Create response embed
            embed = discord.Embed(
                title="Website Added Successfully",
                description=f"Now monitoring: {url}",
                color=EMBED_COLOR_SUCCESS
            )
            embed.add_field(name="Check Interval", value=f"{interval} minutes", inline=False)
            embed.add_field(name="Initial Status", value="Website added successfully", inline=False)
            
            await ctx.send(embed=embed)
            
            # Send screenshot if available
            website_data = monitor.get_website_status(url)
            if website_data and website_data.get('screenshot_path'):
                await ctx.send("Current view")
                with open(website_data['screenshot_path'], 'rb') as f:
                    screenshot = discord.File(f)
                    await ctx.send(file=screenshot)
                    
        except Exception as e:
            embed = discord.Embed(
                title="Error Adding Website",
                description=str(e),
                color=EMBED_COLOR_ERROR
            )
            await ctx.send(embed=embed)

@bot.command(name='remove', help='Remove a website from monitoring.\nUsage: !remove <url>')
@commands.guild_only()
async def remove_website(ctx, url: str = commands.parameter(description="Website URL to stop monitoring")):
    if not url:
        await ctx.send("Please provide a URL to remove. Usage: !remove <url>")
        return
    """Remove a website from monitoring. Usage: !remove [url]"""
    try:
        monitor.remove_website(url)
        embed = discord.Embed(
            title="Website Removed",
            description=f"Stopped monitoring: {url}",
            color=EMBED_COLOR_SUCCESS
        )
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="Error Removing Website",
            description=str(e),
            color=EMBED_COLOR_ERROR
        )
        await ctx.send(embed=embed)

@bot.command(name='list')
async def list_websites(ctx):
    """Show all monitored websites"""
    websites = monitor.get_all_websites()
    
    def format_website(embed, website):
        latest_status = monitor.get_website_status(website['url'])
        
        # Convert time to UTC and UTC+5
        try:
            last_check_utc = datetime.fromisoformat(website['last_check'])
            last_check_plus5 = last_check_utc.astimezone(pytz.timezone('Asia/Karachi'))
            time_display = (f"Last Check:\n"
                        #   f"UTC: {last_check_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                          f"PKT: {last_check_plus5.strftime('%Y-%m-%d %H:%M:%S')} PKT")
        except Exception:
            time_display = "Last Check: Unknown"
        
        # Determine status emoji and message
        if latest_status:
            status_code = latest_status.get('status_code', 0)
            response_time = latest_status.get('response_time', 0)
            
            if status_code in [200, 201, 202]:
                status_indicator = "✅ Online"
                if response_time > 5:  # High latency threshold
                    status_indicator = "🟨 Online (High Latency)"
            elif status_code >= 500:
                status_indicator = "❌ Server Error"
            elif status_code >= 400:
                status_indicator = "⚠️ Client Error"
            elif status_code == 0:
                status_indicator = "⚪ No Data"
            else:
                status_indicator = "❓ Unknown Status"
            
            # Add any active issues
            active_issues = []
            if latest_status.get('dns_changed'):
                active_issues.append("DNS Changed")
            if latest_status.get('ip_changed'):
                active_issues.append("IP Changed")
            if latest_status.get('content_changed'):
                active_issues.append("Content Changed")
                
            status_text = f"Status: {status_indicator}"
            if active_issues:
                status_text += f"\nActive Issues: {', '.join(active_issues)}"
        else:
            status_text = "Status: ⚪ No Data"

        embed.add_field(
            name=website['url'],
            value=f"{status_text}\nInterval: {website['interval']} minutes\n{time_display}",
            inline=False
        )
    
    await send_paginated_embeds(ctx, "Monitored Websites", websites, format_website)

@bot.command(name='status', help='Get detailed status of a specific website.\nUsage: !status <url>')
@commands.guild_only()
async def website_status(ctx, url: str = commands.parameter(description="Website URL to check status")):
    if not url:
        await ctx.send("Please provide a URL to check. Usage: !status <url>")
        return
    """Get detailed status of a specific website. Usage: !status [url]"""
    try:
        status = monitor.get_website_status(url)
        if status:
            # Create main status embed
            embed = discord.Embed(
                title=f"Status for {url}",
                color=EMBED_COLOR_SUCCESS if status.get('status_code') in [200, 201, 202] else EMBED_COLOR_ERROR
            )
            
            # Add status code and response time
            if status.get('status_code'):
                embed.add_field(
                    name="Status Code",
                    value=f"{status['status_code']} ({'OK' if status['status_code'] == 200 else 'Error'})",
                    inline=True
                )
            
            if status.get('response_time'):
                embed.add_field(
                    name="Response Time",
                    value=f"{status['response_time']:.2f}s",
                    inline=True
                )
            
            # Add IP information
            embed.add_field(name="IP Address", value=status.get('ip', 'Unknown'), inline=False)
            
            # Add DNS information (truncated if too long)
            dns_info = status.get('dns', 'Unknown')
            if len(dns_info) > 1024:  # Discord's field value limit
                dns_info = dns_info[:1021] + "..."
            embed.add_field(name="DNS Info", value=dns_info, inline=False)
            
            # Add last check time
            embed.add_field(name="Last Check", value=status['last_check'], inline=False)
            
            # Send the embed first
            await ctx.send(embed=embed)
            
            # Then send the screenshot if it exists
            if status['screenshot_path'] and os.path.exists(status['screenshot_path']):
                with open(status['screenshot_path'], 'rb') as f:
                    screenshot = discord.File(f)
                    await ctx.send(file=screenshot)
        else:
            await ctx.send(f"No monitoring data found for {url}")
    except Exception as e:
        embed = discord.Embed(
            title="Error Getting Status",
            description=str(e),
            color=EMBED_COLOR_ERROR
        )
        await ctx.send(embed=embed)

@bot.command(name='addadmin')
@commands.has_permissions(administrator=True)
async def add_admin(ctx, user: discord.Member):
    """Add an admin for notifications"""
    try:
        db.add_admin(str(user.id))
        embed = discord.Embed(
            title="Admin Added",
            description=f"{user.mention} has been added as an admin",
            color=EMBED_COLOR_SUCCESS
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Error adding admin: {str(e)}")

@bot.command(name='removeadmin')
@commands.has_permissions(administrator=True)
async def remove_admin(ctx, user: discord.Member):
    """Remove an admin from notifications"""
    try:
        db.remove_admin(str(user.id))
        embed = discord.Embed(
            title="Admin Removed",
            description=f"{user.mention} has been removed as an admin",
            color=EMBED_COLOR_SUCCESS
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Error removing admin: {str(e)}")

@bot.command(name='listadmins')
@commands.has_permissions(administrator=True)
async def list_admins(ctx):
    """List all configured admins"""
    admins = db.get_admins()
    embed = discord.Embed(
        title="Configured Admins",
        color=EMBED_COLOR_INFO
    )
    for admin in admins:
        user = bot.get_user(int(admin['admin_id']))
        if user:
            embed.add_field(
                name=user.name,
                value=f"Notify on changes: {admin['notify_on_changes']}\nNotify on errors: {admin['notify_on_errors']}",
                inline=False
            )
    await ctx.send(embed=embed)

async def notify_admins(channel, message, error=False):
    """Notify all admins based on their preferences"""
    admins = db.get_admins()
    for admin in admins:
        if (error and admin['notify_on_errors']) or (not error and admin['notify_on_changes']):
            mention = f"<@{admin['admin_id']}>"
            await channel.send(f"{mention} {message}")

@tasks.loop(minutes=30)
async def check_websites():
    """Regular check of all websites"""
    channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    
    if not channel:
        print(f"Could not find notification channel with ID {channel_id}")
        return

    try:
        anomalies = monitor.check_all_websites()
        for anomaly in anomalies:
            # Create detailed embed for the anomaly
            embed = discord.Embed(
                title="🚨 Website Monitoring Alert",
                description=f"Issues detected with {anomaly['url']}",
                color=EMBED_COLOR_ERROR,
                timestamp=datetime.now()
            )

            # Add status indicators
            status_indicators = []
            if anomaly.get('dns_changed'):
                status_indicators.append("🔄 DNS Changed")
            if anomaly.get('ip_changed'):
                status_indicators.append("🌐 IP Changed")
            if anomaly.get('high_latency'):
                status_indicators.append("⚡ High Latency")
            if anomaly.get('content_changed'):
                status_indicators.append("📝 Content Changed")
            if anomaly.get('status_code_error'):
                status_indicators.append("❌ Server Error")

            if status_indicators:
                embed.add_field(name="Detected Issues", value="\n".join(status_indicators), inline=False)

            # Add technical details
            if anomaly.get('technical_details'):
                embed.add_field(name="Technical Details", value=anomaly['technical_details'], inline=False)

            # Add metrics if available
            metrics = []
            if anomaly.get('response_time'):
                metrics.append(f"Response Time: {anomaly['response_time']:.2f}s")
            if anomaly.get('status_code'):
                metrics.append(f"Status Code: {anomaly['status_code']}")
            if metrics:
                embed.add_field(name="Metrics", value="\n".join(metrics), inline=False)

            # Send the main notification
            await channel.send(embed=embed)

            # Send screenshot if available
            if anomaly.get('screenshot_path') and os.path.exists(anomaly['screenshot_path']):
                await channel.send("📸 Current website state:")
                with open(anomaly['screenshot_path'], 'rb') as f:
                    screenshot = discord.File(f)
                    await channel.send(file=screenshot)

            # Notify admins
            await notify_admins(channel, f"⚠️ Alert for {anomaly['url']}\nDetected issues: {', '.join(status_indicators)}")

    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Monitoring System Error",
            description=f"Error during website monitoring:\n```{str(e)}```",
            color=EMBED_COLOR_ERROR
        )
        await channel.send(embed=error_embed)
        await notify_admins(channel, "🔥 Monitoring system encountered an error!", error=True)

async def generate_daily_report():
    """Generate a comprehensive daily report of all websites"""
    websites = monitor.get_all_websites()
    
    # Collect statistics
    total_sites = len(websites)
    status_counts = Counter()
    avg_response_times = []
    issues_found = []
    
    for site in websites:
        status = monitor.get_website_status(site['url'])
        if status:
            # Count status codes
            status_code = getattr(monitor, 'last_status_code', 0)
            if status_code >= 500:
                status_counts['Critical'] += 1
            elif status_code >= 400:
                status_counts['Warning'] += 1
            elif status_code >= 200:
                status_counts['Healthy'] += 1
            
            # Collect response times
            response_time = getattr(monitor, 'last_response_time', 0)
            if response_time:
                avg_response_times.append(response_time)
            
            # Check for issues
            if status.get('technical_details'):
                issues_found.append((site['url'], status['technical_details']))

    # Create report embed
    embed = discord.Embed(
        title="📊 Daily Website Monitoring Report",
        description=f"Report generated at {datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        color=REPORT_COLOR
    )
    
    # Add overview statistics
    embed.add_field(
        name="📈 Overview",
        value=f"Total Websites: {total_sites}\n"
              f"Healthy: {status_counts['Healthy']}\n"
              f"Warning: {status_counts['Warning']}\n"
              f"Critical: {status_counts['Critical']}",
        inline=False
    )
    
    # Add performance metrics
    if avg_response_times:
        avg_time = sum(avg_response_times) / len(avg_response_times)
        embed.add_field(
            name="⚡ Performance",
            value=f"Average Response Time: {avg_time:.2f}s",
            inline=False
        )
    
    # Add issues if any
    if issues_found:
        issues_text = "\n".join([f"• {url}: {details}" for url, details in issues_found[:5]])
        if len(issues_found) > 5:
            issues_text += f"\n...and {len(issues_found) - 5} more issues"
        embed.add_field(
            name="⚠️ Active Issues",
            value=issues_text,
            inline=False
        )
    
    return embed

@tasks.loop(hours=24)
async def daily_report():
    """Send daily report at specified UTC time"""
    channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    
    if channel:
        report_embed = await generate_daily_report()
        await channel.send("📬 Daily Website Monitoring Report", embed=report_embed)
        await notify_admins(channel, "Daily monitoring report is available.")

@daily_report.before_loop
async def before_daily_report():
    """Wait until the specified hour (UTC) to start the daily report"""
    await bot.wait_until_ready()
    now = datetime.now(pytz.UTC)
    next_run = now.replace(hour=REPORT_HOUR, minute=0, second=0)
    
    if now.hour >= REPORT_HOUR:
        next_run = next_run + timedelta(days=1)
    
    await asyncio.sleep((next_run - now).total_seconds())

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for bot commands"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: {error.param.name}\nUse !help <command> for proper usage.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Invalid argument provided. Use !help <command> for proper usage.")
    else:
        await ctx.send(f"An error occurred: {str(error)}")

@bot.command(name='bito', help='Call the bot and get a response')
async def bito(ctx):
    """Respond when called"""
    embed = discord.Embed(
        title="Hello! 👋",
        description="I'm here to help you monitor websites! Use %help to see what I can do.",
        color=EMBED_COLOR_INFO
    )
    await ctx.send(embed=embed)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
