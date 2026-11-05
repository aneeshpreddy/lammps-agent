#!/bin/bash
# Start the presentation demo: ./demo/run.sh [navy|violet]   (default navy; opens http://localhost:8501)
# Run it from a terminal where ANTHROPIC_API_KEY is set (Live mode); Demo mode needs no key and no internet.
cd "$(dirname "$0")/.." && source .venv/bin/activate || exit 1
if [ "${1:-navy}" = "violet" ]; then
  export DEMO_PALETTE=violet
  exec streamlit run demo/app.py --theme.primaryColor "#a78bfa" --theme.backgroundColor "#0b0714" \
       --theme.secondaryBackgroundColor "#1a1030" --theme.textColor "#efeaff"
fi
export DEMO_PALETTE=navy
exec streamlit run demo/app.py
