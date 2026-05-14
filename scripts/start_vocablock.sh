#!/bin/bash

# Wait for desktop to fully load
sleep 8

VENV=/home/madiha/vocablock/.venv/bin/python3
DIR=/home/madiha/vocablock/scripts

# Sync new words from Obsidian file
$VENV $DIR/parser.py

# Generate AI cards for any new words
$VENV $DIR/ai_gen.py

# Start file watcher in background
$VENV $DIR/sync_watcher.py &

# Start popup scheduler in background
$VENV $DIR/schedule_popups.py &