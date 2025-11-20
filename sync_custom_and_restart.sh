#!/usr/bin/env bash
set -euo pipefail

### CONFIG – adjust if your paths/service name differ
MYCODO_CUSTOM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYCODO_ROOT="/opt/Mycodo"
MYCODO_SERVICE="mycodo"

# Source → Destination mappings
declare -A SYNC_DIRS=(
  ["custom_functions"]="${MYCODO_ROOT}/mycodo/functions/custom_functions"
  ["custom_inputs"]="${MYCODO_ROOT}/mycodo/inputs/custom_inputs"
  ["custom_outputs"]="${MYCODO_ROOT}/mycodo/outputs/custom_outputs"
)

echo "Using Mycodo-custom root: ${MYCODO_CUSTOM_ROOT}"
echo "Using Mycodo root:        ${MYCODO_ROOT}"
echo

# Optional: require root (since we'll restart the service and write into /var)
if [[ "$EUID" -ne 0 ]]; then
  echo "Please run as root (e.g. with sudo)." >&2
  exit 1
fi

# Ensure destination directories exist
for SRC in "${!SYNC_DIRS[@]}"; do
  DEST="${SYNC_DIRS[$SRC]}"
  if [[ ! -d "$DEST" ]]; then
    echo "Creating destination directory: $DEST"
    mkdir -p "$DEST"
  fi
done

echo "Syncing custom modules into Mycodo ..."

for SRC in "${!SYNC_DIRS[@]}"; do
  SRC_PATH="${MYCODO_CUSTOM_ROOT}/${SRC}"
  DEST_PATH="${SYNC_DIRS[$SRC]}"

  if [[ ! -d "$SRC_PATH" ]]; then
    echo "Warning: Source directory does not exist, skipping: $SRC_PATH"
    continue
  fi

  echo "  -> ${SRC_PATH}  →  ${DEST_PATH}"

  # Copy all .py files recursively, flattening to destination root
  # This ensures that scripts nested in folders (e.g. "alicat mfc/script.py")
  # are placed directly into the custom_inputs/outputs folder where Mycodo can find them.
  find "${SRC_PATH}" -name "*.py" -type f ! -name "__*" -exec cp -u {} "${DEST_PATH}/" \;
done

echo
echo "Restarting Mycodo service: ${MYCODO_SERVICE}"

# Stop & start or just restart; restart is usually enough
systemctl restart "${MYCODO_SERVICE}"

echo "Done. Mycodo custom modules synced and service restarted."
