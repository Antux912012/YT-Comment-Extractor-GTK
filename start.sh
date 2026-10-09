#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}=========================================================${NC}"
echo -e "${GREEN}          YOUTUBE COMMENT EXTRACTOR - LAUNCHER           ${NC}"
echo -e "${CYAN}=========================================================${NC}\n"

# Check if .env already exists and contains the keys
if [ -f ".env" ] && grep -q "GOOGLE_CLIENT_ID" ".env" && grep -q "GOOGLE_CLIENT_SECRET" ".env"; then
    echo -e "${GREEN}✓ Credentials found in .env file!${NC}"
    echo -e "Starting the application...\n"
else
    echo -e "${YELLOW}No Google Cloud credentials found. Let's set them up!${NC}"
    echo -e "To use the Official YouTube API, you need a free Client ID and Secret.\n"
    
    echo -e "${CYAN}--- HOW TO GET YOUR CREDENTIALS ---${NC}"
    echo "1. Go to https://console.cloud.google.com/"
    echo "2. Create a new Project (or select an existing one)."
    echo "3. Go to 'APIs & Services' > 'Library' and enable the 'YouTube Data API v3'."
    echo "4. Go to 'APIs & Services' > 'Credentials'."
    echo "5. Click 'Create Credentials' -> 'OAuth client ID'."
    echo "   (If asked to configure the OAuth consent screen, select 'External', fill in required fields, and publish it)."
    echo "6. Choose 'Web application' as the Application type."
    echo "7. Under 'Authorized redirect URIs', click ADD URI and paste EXACTLY:"
    echo -e "   ${GREEN}http://localhost:5000/api/auth/callback${NC}"
    echo "8. Click Create. A window will pop up with your Client ID and Client Secret."
    echo -e "${CYAN}-----------------------------------${NC}\n"

    read -p "Enter your Google Client ID: " client_id
    read -p "Enter your Google Client Secret: " client_secret
    
    echo ""
    echo -e "${CYAN}Generating secure Flask secret key...${NC}"
    flask_secret=$(openssl rand -hex 24 2>/dev/null || echo $RANDOM$RANDOM$RANDOM)

    echo "GOOGLE_CLIENT_ID=$client_id" > .env
    echo "GOOGLE_CLIENT_SECRET=$client_secret" >> .env
    echo "FLASK_SECRET_KEY=$flask_secret" >> .env
    echo "GOOGLE_REDIRECT_URI=http://localhost:5000/api/auth/callback" >> .env

    echo -e "${GREEN}✓ Credentials saved successfully to .env!${NC}\n"
fi

# Detect docker vs podman
if command -v docker &> /dev/null; then
    # Check if docker-compose plugin or standalone exists
    if docker compose version &> /dev/null; then
        CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        CMD="docker-compose"
    else
        echo "Docker is installed but docker-compose is not found."
        exit 1
    fi
elif command -v podman &> /dev/null; then
    if command -v podman-compose &> /dev/null; then
        CMD="podman-compose"
    else
        echo "Podman is installed but podman-compose is not found."
        exit 1
    fi
else
    echo "Neither Docker nor Podman was found. Please install one to run this app."
    exit 1
fi

echo -e "${CYAN}Executing: ${CMD} up -d --build${NC}"
$CMD up -d --build

echo -e "\n${GREEN}=========================================================${NC}"
echo -e "${GREEN}✓ Application is starting in the background!${NC}"
echo -e "Wait a few seconds for the build, then open your browser at:"
echo -e "${CYAN}http://localhost:5000${NC}"
echo -e "${GREEN}=========================================================${NC}"
