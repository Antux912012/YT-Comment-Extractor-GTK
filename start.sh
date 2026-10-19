#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\033[0;36m=========================================================\033[0m"
echo -e "\033[0;32m   YOUTUBE COMMENT EXTRACTOR v0.3 - LIBADWAITA GTK4      \033[0m"
echo -e "\033[0;36m=========================================================\033[0m\n"

echo -e "\033[0;36mChecking Python Virtual Environment...\033[0m"
if [ ! -x "venv/bin/python3" ] || ! grep -q "$SCRIPT_DIR/venv" "venv/bin/activate" 2>/dev/null; then
    echo -e "\033[1;33mCreating virtual environment with system site-packages (for GTK4/Adw)...\033[0m"
    rm -rf venv
    python3 -m venv --system-site-packages venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo -e "\033[0;32mLaunching Native GTK4 / Libadwaita Application...\033[0m"
exec python3 main_gtk.py "$@"
