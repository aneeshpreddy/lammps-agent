#!/bin/bash
# Start AtomForge: ./web/run.sh   (blue; ./web/run.sh violet for the violet theme)
# Opens http://localhost:8501. Start it from a terminal where ANTHROPIC_API_KEY is set; offline mode needs no key.
cd "$(dirname "$0")/.." && source .venv/bin/activate || exit 1
if [ "${1:-blue}" = "violet" ]; then
  export APP_PALETTE=violet
  exec streamlit run web/app.py --theme.primaryColor "#a78bfa" --theme.backgroundColor "#0d0a16" \
       --theme.secondaryBackgroundColor "#161127" --theme.textColor "#efeaff"
fi
export APP_PALETTE=navy
exec streamlit run web/app.py
