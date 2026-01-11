#!/bin/bash

cd "$(dirname "$0")"

# Run setup if venv doesn't exist
if [ ! -d "venv" ]; then
    bash setup.sh
fi

source venv/bin/activate
python main.py "$@"
