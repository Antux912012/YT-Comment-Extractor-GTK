#!/bin/bash

echo -e "\033[0;36m=========================================================\033[0m"
echo -e "\033[0;32m    YOUTUBE COMMENT EXTRACTOR - DESKTOP LAUNCHER         \033[0m"
echo -e "\033[0;36m=========================================================\033[0m\n"

echo -e "\033[0;36mChecking Python Virtual Environment...\033[0m"
if [ ! -d "venv" ]; then
    echo -e "\033[1;33mCreating virtual environment and installing dependencies...\033[0m"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

export FLASK_SECRET_KEY=$(python3 -c "import os; print(os.urandom(24).hex())")

echo -e "\033[0;32mStarting Desktop Application...\033[0m"
python app.py
