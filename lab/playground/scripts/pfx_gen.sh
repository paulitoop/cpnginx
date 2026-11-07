#!/bin/bash
set -euo pipefail

show_help() {
    echo "Usage: $0 <type> <cert_name> [--san <dns_name>] [--pin <pin>] [--keyid <id>]"
    echo ""
    echo "Full certificate pipeline:"
    echo "  1. Create certificate request"
    echo "  2. Wait for signed certificate"
    echo "  3. Install certificate to uMy and bind to container"
    echo "  4. Export certificate to PFX"
    echo ""
    echo "Arguments:"
    echo "  type         client | server"
    echo "  cert_name    Internal certificate name (folder/container/file name)"
    echo "  --san        Required for server certificate, DNS name for SAN/CN"
    echo "  --pin        PIN for key container / PFX (default: 12345678)"
    echo "  --keyid      SubjectKeyID for export (optional, auto-detected by default)"
    echo ""
    echo "Examples:"
    echo "  $0 server cpnginx-test-server-25032026 --san nginx.example.test"
    echo "  $0 client cpnginx-client-test"
    exit 1
}

if [[ $# -lt 2 ]]; then
    show_help
fi

CERT_TYPE="$1"
CERT_NAME="$2"
shift 2

if [[ "$CERT_TYPE" != "client" && "$CERT_TYPE" != "server" ]]; then
    echo "ERROR: first argument must be 'client' or 'server'"
    exit 1
fi

PFX_PIN="12345678"
SUBJECT_KEY_ID=""
SAN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pin)
            [[ $# -ge 2 ]] || { echo "ERROR: --pin requires a value"; exit 1; }
            PFX_PIN="$2"
            shift 2
            ;;
        --keyid)
            [[ $# -ge 2 ]] || { echo "ERROR: --keyid requires a value"; exit 1; }
            SUBJECT_KEY_ID="$2"
            shift 2
            ;;
        --san)
            [[ $# -ge 2 ]] || { echo "ERROR: --san requires a value"; exit 1; }
            SAN="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            show_help
            ;;
    esac
done

if [[ "$CERT_TYPE" == "server" && -z "$SAN" ]]; then
    echo "ERROR: --san is required for server certificates"
    echo "Example:"
    echo "  $0 server cpnginx-test-server-25032026 --san nginx.example.test"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$CERT_TYPE" == "server" ]]; then
    CERT_DIR="$PROJECT_ROOT/server/certs/$CERT_NAME"
    KEYS_DIR="$PROJECT_ROOT/server/keys"
    CERT_USAGE="1.3.6.1.5.5.7.3.1"   # Server Auth
    SUBJECT_DN="C=RU,O=Test O,OU=Test OU,CN=$SAN"
else
    CERT_DIR="$PROJECT_ROOT/client/certs/$CERT_NAME"
    KEYS_DIR="$PROJECT_ROOT/client/keys"
    CERT_USAGE="1.3.6.1.5.5.7.3.2"   # Client Auth
    SUBJECT_DN="C=RU,O=Test O,OU=Test OU,CN=$CERT_NAME"
fi

if [[ -d "$CERT_DIR" ]]; then
    echo "ERROR: Certificate with name '$CERT_NAME' already exists"
    exit 1
fi

mkdir -p "$CERT_DIR"
mkdir -p "$KEYS_DIR"

REQ_FILE="$CERT_DIR/$CERT_NAME.req"
CER_FILE="$CERT_DIR/$CERT_NAME.cer"
PFX_FILE="$KEYS_DIR/$CERT_NAME.pfx"

CRYPTCP="/opt/cprocsp/bin/amd64/cryptcp"
CERTMGR="/opt/cprocsp/bin/amd64/certmgr"
CSPTEST="/opt/cprocsp/bin/amd64/csptest"
RUN_AS_USER="root"

echo "=== Certificate Pipeline ==="
echo "Type            : $CERT_TYPE"
echo "Certificate name: $CERT_NAME"
if [[ "$CERT_TYPE" == "server" ]]; then
    echo "SAN / CN        : $SAN"
fi
echo "Request file    : $REQ_FILE"
echo "Certificate file: $CER_FILE"
echo "PFX file        : $PFX_FILE"
echo ""

echo "=== Step 1: Creating certificate request ==="

CRYPTCP_CMD=(
    sudo "$CRYPTCP"
    -creatrqst "$REQ_FILE"
    -dn "$SUBJECT_DN"
    -provtype 80
    -provname "Crypto-Pro GOST R 34.10-2012 Cryptographic Service Provider"
    -exprt
    -both
    -ku
    -certusage "$CERT_USAGE"
)

if [[ "$CERT_TYPE" == "server" ]]; then
    CRYPTCP_CMD+=(
        -altname "$SAN"
    )
fi

CRYPTCP_CMD+=(
    -cont "$CERT_NAME"
    -pin "$PFX_PIN"
)

"${CRYPTCP_CMD[@]}"

touch "$CER_FILE"

echo ""
echo "✔ Certificate request created:"
echo "  $REQ_FILE"
echo ""
echo "Open the signing page:"
echo "  https://testgost2012.cryptopro.ru/certsrv/certrqxt.asp"
echo ""
echo "Upload this file:"
echo "  $REQ_FILE"
echo ""
echo "Save the signed certificate to:"
echo "  $CER_FILE"
echo ""

while true; do
    read -r -p "Have you placed the signed certificate into the file above? [y/N]: " ANSWER

    case "$ANSWER" in
        y|Y)
            if [[ -s "$CER_FILE" ]]; then
                echo "✔ Signed certificate file exists and is not empty."
                break
            else
                echo "ERROR: File is missing or empty:"
                echo "  $CER_FILE"
                echo "Please place the signed certificate there and try again."
                echo ""
            fi
            ;;
        n|N|"")
            echo "Waiting. Please sign the certificate and place it here:"
            echo "  $CER_FILE"
            echo ""
            ;;
        *)
            echo "Please answer y or n."
            ;;
    esac
done

echo ""
echo "=== Step 2: Reading available containers ==="

mapfile -t CONTAINERS < <(
    sudo -u "$RUN_AS_USER" "$CSPTEST" -keyset -info -enum_containers -unique 2>/dev/null \
    | sed 's/\r$//' \
    | grep '|' \
    | awk -F'|' 'NF >= 2 {print $0}'
)

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
    echo "ERROR: No valid containers found."
    exit 1
fi

echo "Available containers:"
echo ""

for i in "${!CONTAINERS[@]}"; do
    printf "  [%d] %s\n" "$((i + 1))" "${CONTAINERS[$i]}"
done

echo ""
while true; do
    read -r -p "Select container number: " CONTAINER_INDEX

    if [[ "$CONTAINER_INDEX" =~ ^[0-9]+$ ]] && \
       [[ "$CONTAINER_INDEX" -ge 1 ]] && \
       [[ "$CONTAINER_INDEX" -le "${#CONTAINERS[@]}" ]]; then
        break
    fi

    echo "Invalid selection. Enter a number from 1 to ${#CONTAINERS[@]}."
done

SELECTED_LINE="${CONTAINERS[$((CONTAINER_INDEX - 1))]}"
SELECTED_CONTAINER="${SELECTED_LINE#*|}"

echo ""
echo "Selected container:"
echo "  $SELECTED_CONTAINER"
echo ""

echo "=== Step 3: Installing certificate and binding to container ==="

TMP_INSTALL_LOG="$(mktemp)"

sudo -u "$RUN_AS_USER" "$CERTMGR" \
    -inst \
    -file "$CER_FILE" \
    -cont "$SELECTED_CONTAINER" \
    -store uMy \
    -pin "$PFX_PIN" 2>&1 | tee "$TMP_INSTALL_LOG"

SUBJECT_KEY_ID=$(
    awk -F': ' '/SubjectKeyID/ {print $2; exit}' "$TMP_INSTALL_LOG"
)

SERIAL=$(
    awk -F': ' '/Serial/ {print $2; exit}' "$TMP_INSTALL_LOG"
)

THUMBPRINT=$(
    awk -F': ' '/SHA1 Thumbprint/ {print $2; exit}' "$TMP_INSTALL_LOG"
)

PRIVATE_KEY_LINK=$(
    awk -F': ' '/PrivateKey Link/ {print $2; exit}' "$TMP_INSTALL_LOG"
)

rm -f "$TMP_INSTALL_LOG"

echo ""
echo "=== Step 4: Installation summary ==="
echo "Serial         : ${SERIAL:-NOT FOUND}"
echo "Thumbprint     : ${THUMBPRINT:-NOT FOUND}"
echo "SubjectKeyID   : ${SUBJECT_KEY_ID:-NOT FOUND}"
echo "PrivateKey Link: ${PRIVATE_KEY_LINK:-NOT FOUND}"

if [[ -z "${SUBJECT_KEY_ID:-}" ]]; then
    echo ""
    echo "ERROR: Could not extract SubjectKeyID from installation output."
    exit 1
fi

if [[ -z "${PRIVATE_KEY_LINK:-}" || "${PRIVATE_KEY_LINK}" != Yes* ]]; then
    echo ""
    echo "WARNING: PrivateKey Link is not confirmed as 'Yes'."
    echo "PFX export may fail or produce incomplete result."
fi

echo ""
echo "=== Step 5: Exporting certificate to PFX. Write password for PFX container ==="
sudo -u "$RUN_AS_USER" "$CERTMGR" \
    -export \
    -pfx \
    -keyid "$SUBJECT_KEY_ID" \
    -dest "$PFX_FILE" \
    -pin "$PFX_PIN"
