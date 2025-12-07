#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements.txt

os=$(uname -s)
arch=$(uname -m)
url=""
if [ "$os" = "Linux" ]; then
  url="https://m645b3e1bb36e-mrap.mrap.accesspoint.tos-global.volces.com/linux/amd64/tosutil"
elif [ "$os" = "Darwin" ] && [ "$arch" = "arm64" ]; then
  url="https://m645b3e1bb36e-mrap.mrap.accesspoint.tos-global.volces.com/darwin/arm64/tosutil"
else
  echo "Unsupported platform: $os $arch"
  exit 1
fi
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$url" -o tosutil
elif command -v wget >/dev/null 2>&1; then
  wget -O tosutil "$url"
else
  echo "Neither curl nor wget found"
  exit 1
fi
chmod +x tosutil
./tosutil config -i "your_access_key" -k "your_secret_key" -e tos-cn-beijing.volces.com -re cn-beijing
