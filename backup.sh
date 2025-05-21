#!/bin/bash

# Backup directory
BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database and screenshots
echo "Creating backup..."
tar -czf "$BACKUP_DIR/website_monitor_${TIMESTAMP}.tar.gz" data screenshots

# Remove backups older than 7 days
find "$BACKUP_DIR" -name "website_monitor_*.tar.gz" -mtime +7 -delete

echo "Backup complete: $BACKUP_DIR/website_monitor_${TIMESTAMP}.tar.gz"
