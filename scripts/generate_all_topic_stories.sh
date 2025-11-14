#!/bin/bash
# Generate stories for all characters and all topics in both TR and EN
# Usage: bash backend/scripts/generate_all_topic_stories.sh [--topic TOPIC] [--skip-existing]

set -e

cd "$(dirname "$0")/../.." || exit 1
source backend/venv/bin/activate

# Characters from story_composer.py CHARACTER_PERSONALITY (all characters with personality definitions)
CHARACTERS=(
    # Original characters
    "Mino"
    "Luna"
    "Tiko"
    "Bubu"
    "Sunny"
    "Koko"
    # Derivative characters (ASO-safe names with personality definitions)
    "Elisa the Ice Fairy"
    "Spider Fighter"
    "Yellow Buddy"
    "Chirpy Birdie"
    "Bubble Buddy"
    "Funny Bunny"
    "Super Metal Hero"
    "Piggy Friend"
    "Blu Pup"
    "Rescue Pup Crew"
    "Ocean Dreamer Moa"
    "Super Jump Hero"
    "Swamp Buddy Hero"
    "Boots Knight Pal"
    "Frost Friend Sid"
    "Adventure Dora Pal"
    "Snowman Buddy Olaf-style"
    "Spark Buddy"
    "Mystery Pup Buddy"
    "Sneaky Cat Tom"
    "Clever Mouse Jerry"
    "Shell Heroes Crew"
)

# Topics from StorySelectionView.swift categoryKey mapping
TOPICS=(
    # Bedtime category
    "bedtime"
    "sleep"
    # Sibling category
    "sibling"
    "sibling issues"
    # Screen Time category
    "screen time"
    "digital safety"
    # Emotional category
    "feeling sad"
    "feelings"
    "anxiety"
    "emotional regulation"
    # Behavioral category
    "behavior"
    "attention"
    "behavior attention"
    "behavior_attention"
    "adhd"
    "numbers"
    "math"
    "homework"
    # Friendship category
    "friendship"
    "kindness"
    "sharing"
    "manners"
    # Confidence category
    "confidence"
    "independence"
    "bravery"
    "time"
    # Nutrition category
    "food"
    "health"
    "body parts"
    "body"
    # Transitions category
    "transitions"
    "change"
    # Imagination category
    "creativity"
    "imagination"
    "play"
    "colors"
    "rainbow"
    "music"
    "shapes"
    "animals"
    "nature"
    "space"
    "ocean"
    "fairy tales"
)

LANGS=("de" "en" "es" "fr" "tr")
MINUTES=10
SKIP_EXISTING=false
SPECIFIC_TOPIC=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --topic)
            SPECIFIC_TOPIC="$2"
            shift 2
            ;;
        --skip-existing)
            SKIP_EXISTING=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--topic TOPIC] [--skip-existing]"
            exit 1
            ;;
    esac
done

# Filter topics if specific topic is requested
if [ -n "$SPECIFIC_TOPIC" ]; then
    TOPICS=("$SPECIFIC_TOPIC")
fi

TOTAL=$((${#CHARACTERS[@]} * ${#TOPICS[@]} * ${#LANGS[@]}))
CURRENT=0
SUCCESS=0
FAILED=0
SKIPPED=0

echo "🚀 Generating stories for ${#CHARACTERS[@]} characters, ${#TOPICS[@]} topics in ${#LANGS[@]} languages"
echo "📊 Total: $TOTAL stories"
if [ "$SKIP_EXISTING" = true ]; then
    echo "⏭️  Skipping existing stories"
fi
echo ""

# Function to check if story exists
story_exists() {
    local CHAR="$1"
    local TOPIC="$2"
    local LANG="$3"
    
    # Convert character name to slug
    local CHAR_SLUG=$(echo "$CHAR" | tr '[:upper:]' '[:lower:]' | sed 's/ /_/g')
    local TOPIC_SLUG=$(echo "$TOPIC" | tr '[:upper:]' '[:lower:]' | sed 's/ /_/g')
    local STORY_PATH="mino/Content/${LANG}/stories/${CHAR_SLUG}/${TOPIC_SLUG}.json"
    
    [ -f "$STORY_PATH" ]
}

for CHAR in "${CHARACTERS[@]}"; do
    for TOPIC in "${TOPICS[@]}"; do
        for LANG in "${LANGS[@]}"; do
            CURRENT=$((CURRENT + 1))
            
            # Check if story already exists
            if [ "$SKIP_EXISTING" = true ] && story_exists "$CHAR" "$TOPIC" "$LANG"; then
                echo "[$CURRENT/$TOTAL] ⏭️  $CHAR - $TOPIC ($LANG) - already exists"
                SKIPPED=$((SKIPPED + 1))
                continue
            fi
            
            echo "[$CURRENT/$TOTAL] $CHAR - $TOPIC ($LANG)"
            
            if python backend/scripts/generate_compose_story.py \
                --character "$CHAR" \
                --topic "$TOPIC" \
                --lang "$LANG" \
                --minutes $MINUTES 2>&1 | grep -q "✅ Saved"; then
                SUCCESS=$((SUCCESS + 1))
                echo "  ✅ Success"
            else
                FAILED=$((FAILED + 1))
                echo "  ❌ Failed"
            fi
            
            # Small delay to avoid rate limiting
            sleep 2
        done
    done
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary:"
echo "   ✅ Success: $SUCCESS"
echo "   ❌ Failed: $FAILED"
echo "   ⏭️  Skipped: $SKIPPED"
echo "   📝 Total: $TOTAL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

