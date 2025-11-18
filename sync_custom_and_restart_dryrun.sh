#!/usr/bin/env bash
set -euo pipefail

### CONFIG – adjust if your paths/service name differ
MYCODO_CUSTOM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYCODO_ROOT="/opt/Mycodo"
MYCODO_SERVICE="mycodo"

# Source → Destination mappings
declare -A SYNC_DIRS=(
  ["custom_functions"]="${MYCODO_ROOT}/mycodo/custom_functions"
  ["custom_inputs"]="${MYCODO_ROOT}/mycodo/custom_inputs"
  ["custom_outputs"]="${MYCODO_ROOT}/mycodo/custom_outputs"
)

echo "============================================"
echo "DRY RUN MODE - No changes will be made"
echo "============================================"
echo
echo "Using Mycodo-custom root: ${MYCODO_CUSTOM_ROOT}"
echo "Using Mycodo root:        ${MYCODO_ROOT}"
echo

# Check if running as root
if [[ "$EUID" -ne 0 ]]; then
  echo "NOTE: Not running as root. For actual sync, you'll need sudo." >&2
  echo
fi

echo "Checking destination directories..."
for SRC in "${!SYNC_DIRS[@]}"; do
  DEST="${SYNC_DIRS[$SRC]}"
  if [[ -d "$DEST" ]]; then
    echo "  ✓ Destination exists: $DEST"
  else
    echo "  ✗ Would create: $DEST"
  fi
done

echo
echo "Files that would be synced:"
echo

for SRC in "${!SYNC_DIRS[@]}"; do
  SRC_PATH="${MYCODO_CUSTOM_ROOT}/${SRC}"
  DEST_PATH="${SYNC_DIRS[$SRC]}"

  if [[ ! -d "$SRC_PATH" ]]; then
    echo "Warning: Source directory does not exist, would skip: $SRC_PATH"
    continue
  fi

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Source: ${SRC_PATH}"
  echo "Destination: ${DEST_PATH}"
  echo

  # Use rsync --dry-run to show what would be done
  # --update: only sync files that are newer in source
  # No --delete: won't remove any files from destination
  if [[ -d "$DEST_PATH" ]]; then
    echo "Files that would be updated or added:"
    rsync -avin --update "${SRC_PATH}/" "${DEST_PATH}/" || true
  else
    echo "All files would be copied (new destination):"
    rsync -avin --update "${SRC_PATH}/" "${DEST_PATH}/" || true
  fi
  echo
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "After syncing, would restart service: ${MYCODO_SERVICE}"
echo "Command: systemctl restart ${MYCODO_SERVICE}"
echo
echo "============================================"
echo "DRY RUN COMPLETE - No changes were made"
echo "============================================"
echo
echo "To perform the actual sync, run:"
echo "  sudo ./sync_custom_and_restart.sh"
