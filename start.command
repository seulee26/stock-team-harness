#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if [ -f service/launch.py ]; then
  exec python3 service/launch.py "$@"
fi
exec python3 launch.py "$@"
