#!/bin/bash
# Generate audio files for all 14 visible characters
# Usage: bash backend/scripts/generate_all_visible_character_audios.sh [--skip-existing]

set -e

cd "$(dirname "$0")/../.." || exit 1
source backend/venv/bin/activate

SKIP_EXISTING=""
if [ "$1" = "--skip-existing" ]; then
    SKIP_EXISTING="--skip-existing"
fi

# 14 Visible Characters
CHARACTERS=(
    "mino"
    "luna"
    "tiko"
    "bubu"
    "sunny"
    "koko"
    "tom"
    "jerry"
    "elsa"
    "ninjaturtles"
    "spiderman"
    "minion"
    "tweety"
    "spongebob"
)

echo "🚀 Generating audio files for 14 visible characters"
echo "📊 Characters: ${#CHARACTERS[@]}"
echo "📊 Languages: de, en, es, fr, tr (5)"
echo "📊 Topics: 10 topics"
echo ""

TOTAL=${#CHARACTERS[@]}
CURRENT=0

for CHAR in "${CHARACTERS[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo "[$CURRENT/$TOTAL] 🎤 Processing: $CHAR"
    
    python3 backend/scripts/generate_character_audios_from_stories.py \
        --character "$CHAR" \
        --all \
        $SKIP_EXISTING
    
    echo ""
done

echo "✅ All audio files generated!"


