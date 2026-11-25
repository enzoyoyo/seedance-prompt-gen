#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${SEEDANCE_REPO_URL:-https://github.com/enzoyoyo/seedance-prompt-gen.git}"
DEFAULT_INSTALL_DIR="${SEEDANCE_SKILL_DIR:-$HOME/.local/share/seedance-prompt-gen}"

MODE_FLAG="--apply"
COMMANDS_ONLY=""
TARGET_HOME="$HOME"

usage() {
  cat <<'EOF'
Usage: bash install.sh [options]

Options:
  --dry-run        Preview detected hosts and planned symlinks/wrappers without writing
  --apply          Install skill symlinks and thin slash-command wrappers (default)
  --commands-only  Check or install slash-command wrappers only
  --home DIR       Override target home directory (useful for isolated testing)
  -h, --help       Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE_FLAG="--dry-run"
      shift
      ;;
    --apply)
      MODE_FLAG="--apply"
      shift
      ;;
    --commands-only)
      COMMANDS_ONLY="--commands-only"
      shift
      ;;
    --home)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Missing value for --home" >&2
        exit 2
      fi
      TARGET_HOME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 (3.10+) is required." >&2
  exit 1
fi

SOURCE_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [[ -n "$SOURCE_PATH" && -e "$SOURCE_PATH" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
fi
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/SKILL.md" && -f "$SCRIPT_DIR/scripts/install_commands.py" ]]; then
  SKILL_DIR="$SCRIPT_DIR"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "Error: git is required to clone $REPO_URL." >&2
    exit 1
  fi
  SKILL_DIR="$DEFAULT_INSTALL_DIR"
  if [[ -d "$SKILL_DIR/.git" ]]; then
    echo "Updating existing checkout in $SKILL_DIR ..."
    git -C "$SKILL_DIR" pull --ff-only
  elif [[ -e "$SKILL_DIR" ]]; then
    echo "Error: $SKILL_DIR already exists and is not a git repository." >&2
    exit 1
  else
    mkdir -p "$(dirname "$SKILL_DIR")"
    echo "Cloning $REPO_URL -> $SKILL_DIR ..."
    git clone --depth 1 "$REPO_URL" "$SKILL_DIR"
  fi
fi

ARGS=("$MODE_FLAG" "--home" "$TARGET_HOME")
if [[ -n "$COMMANDS_ONLY" ]]; then
  ARGS+=("$COMMANDS_ONLY")
fi

echo "Running installer from $SKILL_DIR ($MODE_FLAG) ..."
python3 "$SKILL_DIR/scripts/install_commands.py" "${ARGS[@]}"
