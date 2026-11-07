#!/bin/bash

# Script to convert PFX file to ZIP archive and Base64 encode it
# Usage: ./convert_pfx.sh <pfx_file>

set -e

# Function to display help
show_help() {
    echo "Usage: $0 <pfx_file>"
    echo ""
    echo "Converts PFX file to ZIP archive and encodes to Base64."
    echo ""
    echo "Arguments:"
    echo "  pfx_file    Path to PFX file (relative or absolute)"
    echo ""
    echo "Example:"
    echo "  $0 cpnginx-playground-server-18032026.pfx"
    echo "  $0 ./cpnginx-playground-server-18032026.pfx"
    echo "  $0 /path/to/cpnginx-playground-server-18032026.pfx"
    exit 1
}

# Parse arguments
if [ -z "$1" ]; then
    show_help
fi

INPUT="$1"

# Get the current working directory
WORK_DIR="$(pwd)"

# Determine PFX file path
if [[ "$INPUT" == /* ]]; then
    # Absolute path
    PFX_FILE="$INPUT"
else
    # Relative path from current directory
    PFX_FILE="$WORK_DIR/$INPUT"
fi

# Normalize the path
PFX_FILE="$(realpath -m "$PFX_FILE" 2>/dev/null || echo "$PFX_FILE")"

# Extract base name without extension
BASE_NAME=$(basename "$PFX_FILE" .pfx)

# Output paths - same directory as PFX file
OUTPUT_DIR="$(dirname "$PFX_FILE")"
ZIP_FILE="$OUTPUT_DIR/$BASE_NAME.pfx.zip"
B64_FILE="$OUTPUT_DIR/$BASE_NAME.pfx.zip.b64"

echo "=== PFX Conversion Script ==="
echo "PFX file: $PFX_FILE"
echo "Output ZIP: $ZIP_FILE"
echo "Output B64: $B64_FILE"
echo "Working directory: $WORK_DIR"
echo ""

# Check if PFX file exists
if [ ! -f "$PFX_FILE" ]; then
    echo "ERROR: PFX file not found: $PFX_FILE"
    exit 1
fi

# Step 1: Create ZIP archive
echo "=== Step 1: Creating ZIP archive ==="
cd "$OUTPUT_DIR"
zip "$BASE_NAME.pfx.zip" "$BASE_NAME.pfx"
echo "ZIP file created: $ZIP_FILE"
echo ""

# Step 2: Encode to Base64
echo "=== Step 2: Encoding to Base64 ==="
base64 "$BASE_NAME.pfx.zip" > "$BASE_NAME.pfx.zip.b64"
echo "Base64 file created: $B64_FILE"
echo ""

echo "=== Conversion Complete ==="
echo "Final output: $B64_FILE"
echo ""
echo "To decode and extract:"
echo "  base64 -d $B64_FILE > $ZIP_FILE"
echo "  unzip $ZIP_FILE"
