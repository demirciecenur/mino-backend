#!/bin/bash
# Manual story generation commands for all character-topic combinations
# Usage: Run each command individually or use this as a reference

# Characters (from CharacterSelectionView.swift - fallback + derivative ASO-safe names)
CHARACTERS=(
    # Original characters (fallback)
    "Mino"
    "Luna"
    "Tiko"
    "Bubu"
    "Sunny"
    "Koko"
    "Spider Fighter"
    "Elisa the Ice Fairy"
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

# Topics
TOPICS=(
    "bedtime"
    "sleep"
    "sibling_issues"
    "screen_time"
    "digital_safety"
    "feeling_sad"
    "feelings_emotions"
    "anxiety"
    "emotional_regulation"
    "behavior"
    "attention"
    "adhd"
    "learn_numbers"
    "learn_math"
    "homework"
    "friendship"
    "kindness"
    "sharing"
    "manners"
    "confidence"
    "independence"
    "bravery"
    "time"
    "healthy_eating"
    "health"
    "body_parts"
    "body_awareness"
    "transitions"
    "change"
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
    "fairy_tales"
)

# Languages
LANGS=("tr" "en")

# Generate commands
echo "# Total combinations: $((${#CHARACTERS[@]} * ${#TOPICS[@]} * ${#LANGS[@]}))"
echo "# Characters: ${#CHARACTERS[@]}"
echo "# Topics: ${#TOPICS[@]}"
echo "# Languages: ${#LANGS[@]}"
echo ""
echo "# Commands to run:"
echo ""

for CHAR in "${CHARACTERS[@]}"; do
    for TOPIC in "${TOPICS[@]}"; do
        for LANG in "${LANGS[@]}"; do
            # Escape spaces in topic for command
            TOPIC_ESCAPED=$(echo "$TOPIC" | sed 's/ /\\ /g')
            echo "python backend/scripts/generate_compose_story.py --character \"$CHAR\" --topic \"$TOPIC_ESCAPED\" --lang $LANG --minutes 10"
        done
    done
done

