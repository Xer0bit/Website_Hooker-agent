#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Website Monitor Deployment${NC}"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create .env file with DISCORD_TOKEN and DISCORD_CHANNEL_ID"
    exit 1
fi

# Create required directories
mkdir -p data screenshots

# Build and start containers
echo -e "${GREEN}Building and starting containers...${NC}"
docker-compose -f docker-compose.prod.yml up -d --build

echo -e "${GREEN}Deployment complete!${NC}"
echo "Monitor the logs with: docker-compose logs -f"
