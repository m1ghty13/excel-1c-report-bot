#!/bin/bash
set -e

echo "🚀 Deploying Excel Report Bot..."
git pull origin main
source venv/bin/activate
pip install -r requirements.txt -q
systemctl restart excel-report-bot
systemctl status excel-report-bot --no-pager
echo "✅ Deploy done"
