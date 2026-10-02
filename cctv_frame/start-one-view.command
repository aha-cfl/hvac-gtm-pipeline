#!/bin/bash
# Visual Radio - one-view template. Double-click to start; close this window to stop.
cd "$(dirname "$0")"
echo "Installing the two Python packages it needs (first run only takes a minute)..."
python3 -m pip install --quiet -r requirements.txt || { echo "Python 3 is missing: install it from https://www.python.org/downloads/"; read -r; exit 1; }
echo; echo "Checking the live camera..."
python3 web.py --one --check
echo; echo "Starting Visual Radio in your browser. Keep this window open; close it to stop."
python3 web.py --one --open
