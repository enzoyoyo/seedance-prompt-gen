#!/bin/bash
# Finder launches with a minimal PATH; add the usual Node locations first.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if [ -s "$HOME/.nvm/nvm.sh" ] && ! command -v node >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"
fi
cd "$(dirname "$0")" || exit 1
if ! command -v node >/dev/null 2>&1; then
  echo "找不到 node。请先安装 Node.js，或在终端里运行：cd \"$(pwd)\" && npm start"
  read -r -p "按回车关闭"
  exit 1
fi
if [ ! -d node_modules/three ]; then
  npm ci --no-audit --no-fund || npm install --no-audit --no-fund
fi
exec npm start
