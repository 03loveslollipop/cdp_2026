#!/usr/bin/env bash

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

echo "=== Initializing Python Environment ==="

# Check for Conda / Anaconda / Miniconda
if command -v conda >/dev/null 2>&1; then
    echo "Conda detected."
    if [ ! -d "$ENV_DIR" ]; then
        echo "Creating Conda environment at $ENV_DIR..."
        conda create --prefix "$ENV_DIR" python=3 -y
    else
        echo "Conda environment directory already exists at $ENV_DIR."
    fi

    echo "Activating Conda environment..."
    eval "$(conda shell.bash hook 2>/dev/null)"
    conda activate "$ENV_DIR" 2>/dev/null || source "$ENV_DIR/bin/activate" 2>/dev/null
else
    echo "Conda not found. Falling back to Python venv."
    
    PYTHON_CMD=""
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python"
    else
        echo "Error: Neither python3 nor python executable found." >&2
        return 1 2>/dev/null || exit 1
    fi

    if [ ! -d "$ENV_DIR" ]; then
        echo "Creating venv environment at $ENV_DIR using $PYTHON_CMD..."
        $PYTHON_CMD -m venv "$ENV_DIR"
    else
        echo "venv environment directory already exists at $ENV_DIR."
    fi

    echo "Activating venv environment..."
    source "$ENV_DIR/bin/activate"
fi

# Check and install dependencies from requirements.txt
if [ -f "$REQ_FILE" ]; then
    echo "Checking and installing dependencies from requirements.txt..."
    python -m pip install --upgrade pip setuptools wheel --quiet 2>/dev/null || true
    python -m pip install -r "$REQ_FILE"
else
    echo "requirements.txt not found. Skipping dependency installation."
fi

echo "=== Environment setup complete! ==="

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo ""
    echo "Note: To keep the environment activated in your current shell session, run:"
    echo "  source ./setup.sh"
fi
