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

def format_timedelta(td):
    """Convert a timedelta into a human-readable string."""
    seconds = int(td.total_seconds())
    if seconds < 60:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    return f"{days} days ago"
DEFAULT_CHECK_INTERVAL = 0.5  # Changed to 30 seconds default
REPORT_HOUR = 5  # UTC time
REPORT_COLOR = discord.Color.gold()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    check_websites.change_interval(seconds=30)  # Change to 30 seconds
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
                     interval: Optional[int] = commands.parameter(default=0.5, description="Check interval in minutes")):
    if not url:
        await ctx.send("Please provide a URL to monitor. Usage: !add <url> [check_interval_in_minutes]")
        return
    
    async with ctx.typing():
        try:
            # Perform initial thorough check
            status = monitor.initial_check_website(url)  # New method for thorough initial check
            
            # Add website with specified interval
            monitor.add_website(url, interval)
            
            # Create response embed
            embed = discord.Embed(
                title="Website Added Successfully",
                description=f"Now monitoring: {url}",
                color=EMBED_COLOR_SUCCESS
            )
            embed.add_field(name="Check Interval", value=f"{interval} minutes", inline=False)
            embed.add_field(name="Initial Status", value="✅ Initial check completed", inline=False)
            
            if status.get('technical_details'):
                embed.add_field(name="Technical Details", value=status['technical_details'], inline=False)
            
            await ctx.send(embed=embed)
            
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
        embed.add_field(
            name=f"🌐 {website['url']}",
            value=f"Checking every {website['interval']} minutes",
            inline=False
        )
    
    if not websites:
        await ctx.send("No websites are currently being monitored.")
        return
        
    await send_paginated_embeds(ctx, "📋 Monitored Websites", websites, format_website)

@bot.command(name='status')
async def website_status(ctx, url: str):
    """Get detailed website status with proper error handling"""
    if not url:
        await ctx.send("Please provide a URL to check. Usage: !status <url>")
        return

    loading_msg = await ctx.send("🔍 Checking website status...")
    try:
        status = monitor.get_website_status(url)
        if not status:
            await loading_msg.edit(content=f"❌ Website {url} is not being monitored. Use !add to start monitoring.")
            return

        # Determine embed color based on status
        is_ok = status.get('availability', {}).get('reachable', False)
        embed_color = EMBED_COLOR_SUCCESS if is_ok else EMBED_COLOR_ERROR

        embed = discord.Embed(
            title=f"📊 Status Report: {url}",
            color=embed_color,
            timestamp=datetime.now()
        )

        # Status Information
        status_info = status.get('availability', {})
        status_emoji = "🟢" if is_ok else "🔴"
        embed.add_field(
            name="Status",
            value=f"{status_emoji} {status_info.get('status', 'Unknown')}\n"
                  f"Response Time: {status.get('response_time', 0):.2f}s\n"
                  f"Status Code: {status.get('status_code', 'N/A')}\n"
                  f"Details: {status.get('technical_details', 'No details available')}",
            inline=False
        )

        # Network Info
        embed.add_field(
            name="Network",
            value=f"IP: {status.get('ip', 'Unknown')}\n"
                  f"DNS Records:\n{status.get('dns', 'Unknown')}",
            inline=False
        )

        # Security & Performance
        if status.get('is_secure'):
            embed.add_field(name="Security", value="🔒 HTTPS Enabled", inline=True)

        # Add any errors or warnings
        if status.get('error_message'):
            embed.add_field(
                name="⚠️ Issues",
                value=status['error_message'],
                inline=False
            )

        await loading_msg.edit(content=None, embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="Error Checking Status",
            description=str(e),
            color=EMBED_COLOR_ERROR
        )
        await loading_msg.edit(content=None, embed=error_embed)

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

@tasks.loop(seconds=30)  # Changed from minutes=30 to seconds=30
async def check_websites():
    """Silent check of all websites with immediate alerts for anomalies"""
    channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    
    if not channel:
        return  # Silent return if channel not found

    try:
        anomalies = monitor.check_all_websites()
        for anomaly in anomalies:
            if anomaly.get('critical_changes', False):  # Only alert for critical changes
                embed = discord.Embed(
                    title="🚨 Critical Website Change Detected",
                    description=f"Important changes detected on {anomaly['url']}",
                    color=EMBED_COLOR_ERROR,
                    timestamp=datetime.now()
                )
                
                # Add critical changes first
                critical_issues = []
                if anomaly.get('status_code_error'):
                    critical_issues.append("❌ Website Down/Error")
                if anomaly.get('dns_changed'):
                    critical_issues.append("🔄 DNS Records Changed")
                if anomaly.get('ip_changed'):
                    critical_issues.append("🌐 IP Address Changed")
                
                if critical_issues:
                    embed.add_field(name="Critical Issues", value="\n".join(critical_issues), inline=False)
                    
                if anomaly.get('technical_details'):
                    embed.add_field(name="Technical Details", value=anomaly['technical_details'], inline=False)
                
                # Send alert to admins
                await channel.send(embed=embed)
                await notify_admins(channel, f"⚠️ Critical changes detected for {anomaly['url']}")

    except Exception as e:
        # Only notify admins of monitoring system errors
        await notify_admins(channel, f"🔥 Monitoring system error: {str(e)}", error=True)

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
