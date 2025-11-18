#!/bin/bash
# Generate missing videos for 14 visible characters
# Only generates videos that are missing (6 essential actions)

set -e

cd "$(dirname "$0")/../.." || exit 1
source backend/venv/bin/activate

# Essential actions (6 actions)
ESSENTIAL_ACTIONS="wave,talking,raise_hand,hand_on_hip,lean_closer,side_glance"

# Character names and their specific background styles (for 14 visible characters)
declare -A CHARACTER_BACKGROUNDS=(
    ["mino"]="space adventure theme with twinkling stars, colorful planets in soft pastel hues, cozy space station interior with friendly alien decorations, gentle nebula clouds in purple and blue, warm space lighting, preschool-friendly bright and cheerful cosmic atmosphere"
    ["luna"]="magical dreamy forest with soft moonlit glades, twinkling stars visible through tree branches, cozy mushroom houses with warm glowing windows, pastel purple and blue tones, gentle fairy lights dancing, soft fireflies, preschool-friendly enchanting nighttime wonderland"
    ["tiko"]="playful forest playground with colorful trees, soft green grass, gentle sunlight filtering through leaves creating dappled shadows, friendly woodland creatures visible in background, bright green and yellow tones, natural wooden play elements, preschool-friendly adventurous forest atmosphere"
    ["bubu"]="calm and soothing indoor space with soft pastel walls in lavender and light blue, cozy reading nook with plush cushions and soft blankets, gentle warm lighting from a reading lamp, peaceful atmosphere with soft blue and lavender tones, preschool-friendly comforting and safe environment"
    ["sunny"]="bright and cheerful sunny meadow with colorful wildflowers in yellow, pink, and blue, clear blue sky with fluffy white clouds, warm golden sunlight creating soft shadows, playful butterflies fluttering, vibrant yellow and orange tones, preschool-friendly joyful and energetic atmosphere"
    ["koko"]="forest playground with natural wooden elements, soft earth tones of brown and green, gentle tree canopy overhead providing dappled shade, adventure-themed but safe and cozy, natural rocks and logs, preschool-friendly brave explorer atmosphere with nature elements"
    ["tom"]="playful home setting with soft furniture in gray and brown, friendly home decorations, warm and mischievous atmosphere, gray and brown tones, home-themed props, preschool-friendly home adventure with playful mischief"
    ["jerry"]="cozy small space with soft miniature elements, friendly small decorations, warm and clever atmosphere, brown and beige tones, miniature-themed props, preschool-friendly miniature adventure with clever solutions"
    ["elsa"]="ice castle with soft pastel colors in blue and white, gentle snowflakes falling softly, crystal-like structures with warm glowing lights, magical winter wonderland with blue and white tones, soft ice formations, preschool-friendly enchanting frozen palace atmosphere"
    ["ninjaturtles"]="urban adventure setting with soft city elements, friendly urban decorations, bright and team-oriented atmosphere, green and orange tones, team-themed props, preschool-friendly team adventure with cooperation feel"
    ["spiderman"]="city playground with friendly urban elements, soft city skyline in background with colorful buildings, bright and safe urban environment, red and blue tones, friendly street elements, preschool-friendly heroic city adventure atmosphere"
    ["minion"]="playful laboratory with colorful gadgets in bright yellow and blue, soft bright yellow and blue tones, friendly scientific elements like test tubes and beakers, cheerful and energetic atmosphere, fun science decorations, preschool-friendly fun and educational environment"
    ["tweety"]="sunny garden with colorful flowers in red, yellow, and pink, soft birdhouse visible in background, gentle breeze moving leaves, warm yellow and green tones, friendly garden elements, preschool-friendly cheerful and nature-filled atmosphere"
    ["spongebob"]="underwater playground with soft coral reefs in pink, orange, and purple, friendly sea creatures like fish and starfish in background, gentle ocean currents creating soft movement, bright blue and yellow tones, preschool-friendly aquatic adventure with ocean life"
)

# Function to check if video exists
video_exists() {
    local char=$1
    local action=$2
    local video_file="mino/Assets/characters/${char}/${char}_${action}.mp4"
    [ -f "$video_file" ]
}

# Function to get missing actions for a character
get_missing_actions() {
    local char=$1
    local missing=""
    
    for action in wave talking raise_hand hand_on_hip lean_closer side_glance; do
        if ! video_exists "$char" "$action"; then
            if [ -z "$missing" ]; then
                missing="$action"
            else
                missing="$missing,$action"
            fi
        fi
    done
    
    echo "$missing"
}

# Parse arguments
SPECIFIC_CHARACTER=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --character)
            SPECIFIC_CHARACTER="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--character CHARACTER] [--dry-run]"
            echo ""
            echo "Generates missing videos for 14 visible characters (6 essential actions)"
            echo ""
            echo "Options:"
            echo "  --character CHARACTER  Generate videos for specific character only"
            echo "  --dry-run               Show commands without executing"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Generate all missing videos"
            echo "  $0 --character tiko                  # Generate missing videos for Tiko only"
            echo "  $0 --dry-run                          # Show commands without executing"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Characters to process
if [ -n "$SPECIFIC_CHARACTER" ]; then
    CHARACTERS=("$SPECIFIC_CHARACTER")
else
    CHARACTERS=("mino" "luna" "tiko" "bubu" "sunny" "koko" "tom" "jerry" "elsa" "ninjaturtles" "spiderman" "minion" "tweety" "spongebob")
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 Generating Missing Videos for 14 Visible Characters"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TOTAL_MISSING=0
TOTAL_SUCCESS=0
TOTAL_FAILED=0

# Process each character
for char in "${CHARACTERS[@]}"; do
    # Check if character directory exists
    if [ ! -d "mino/Assets/characters/${char}" ]; then
        echo "⚠️  Character directory not found: ${char}"
        echo ""
        continue
    fi
    
    # Get missing actions
    missing_actions=$(get_missing_actions "$char")
    
    if [ -z "$missing_actions" ]; then
        echo "✅ ${char}: All videos exist"
        echo ""
        continue
    fi
    
    # Count missing
    missing_count=$(echo "$missing_actions" | tr ',' '\n' | wc -l | tr -d ' ')
    TOTAL_MISSING=$((TOTAL_MISSING + missing_count))
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎬 ${char}: Missing ${missing_count} video(s)"
    echo "📋 Actions: ${missing_actions}"
    echo "🎨 Background: ${CHARACTER_BACKGROUNDS[$char]:0:100}..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Get background style
    background_style="${CHARACTER_BACKGROUNDS[$char]}"
    
    # Build command
    CMD="python backend/scripts/generate_character_videos.py --character \"${char}\" --actions \"${missing_actions}\" --background-style \"${background_style}\""
    
    if [ "$DRY_RUN" = true ]; then
        echo "Command: $CMD"
        echo ""
    else
        if eval "$CMD" 2>&1 | tee "/tmp/video_gen_${char}.log" | tail -20 | grep -q "✅.*Success\|📊 Generation Summary"; then
            TOTAL_SUCCESS=$((TOTAL_SUCCESS + missing_count))
            echo "✅ Successfully generated ${missing_count} video(s) for ${char}"
        else
            TOTAL_FAILED=$((TOTAL_FAILED + missing_count))
            echo "❌ Failed to generate some videos for ${char}"
            echo "   Check log: /tmp/video_gen_${char}.log"
        fi
        
        # Small delay to avoid rate limiting
        sleep 3
    fi
    echo ""
done

if [ "$DRY_RUN" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Total missing: ${TOTAL_MISSING}"
    echo "✅ Successful: ${TOTAL_SUCCESS}"
    echo "❌ Failed: ${TOTAL_FAILED}"
    echo ""
fi



