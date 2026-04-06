#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "========================================================"
echo "      🛡️ Code-Sentinel v1 - Linux Installation Script    "
echo "========================================================"

# 1. Check for Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "[Error] Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[Info] Found Python $PYTHON_VERSION"

# 2. Navigate to the agent-python directory
if [ -d "agent-python" ]; then
    cd agent-python
else
    echo "[Error] 'agent-python' directory not found. Please run this script from the root of the repository."
    exit 1
fi

# Store the absolute path for the wrapper script later
AGENT_DIR=$(pwd)

# 3. Create and activate a virtual environment
echo -e "\n[Step 1] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 4. Install dependencies
echo -e "\n[Step 2] Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Check if Ollama is installed, install if missing
echo -e "\n[Step 3] Checking for Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "[Info] Ollama not found. Installing Ollama via official script..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "[Info] Ollama is already installed."
fi

# Ensure Ollama is running in the background before pulling models
echo "[Info] Ensuring Ollama service is running..."
if ! curl -s -f -o /dev/null "http://localhost:11434/api/tags"; then
    echo "[Info] Starting Ollama in the background..."
    ollama serve > /dev/null 2>&1 &
    # Give it a few seconds to initialize
    sleep 5
fi

# 6. Pull the required models
echo -e "\n[Step 4] Pulling required Qwen models..."
echo "Pulling qwen2.5-coder:0.5b (Worker model)..."
ollama pull qwen2.5-coder:0.5b
echo "Pulling qwen2.5-coder:14b (Orchestrator model, ~8GB)..."
ollama pull qwen2.5-coder:14b

# 7. Download the embedding model for offline use
echo -e "\n[Step 5] Downloading embedding model for offline use..."
python3 -c "from core.paths import download_to_program_files; download_to_program_files()" || echo "[Warning] Failed to download embedding model."

# 8. Create the global terminal command
echo -e "\n[Step 6] Creating global 'codesentinel' command..."
mkdir -p "$HOME/.local/bin"
WRAPPER_SCRIPT="$HOME/.local/bin/codesentinel"

# 8. Create the global terminal command with auto-updating
echo -e "\n[Step 6] Creating global 'codesentinel' command..."
mkdir -p "$HOME/.local/bin"
WRAPPER_SCRIPT="$HOME/.local/bin/codesentinel"

cat << EOF > "$WRAPPER_SCRIPT"
#!/usr/bin/env bash
# Wrapper script to launch CodeSentinel from anywhere

# 1. Check if the directory still exists (handles folder moves gracefully)
if [ ! -d "$AGENT_DIR" ]; then
    echo "Error: CodeSentinel directory not found at $AGENT_DIR"
    echo "If you moved the folder, please re-run install.sh in the new location."
    exit 1
fi

cd "$AGENT_DIR" || exit 1
source .venv/bin/activate

# 2. Auto-heal dependencies if requirements.txt was updated
if [ requirements.txt -nt .venv ]; then
    echo "[Code-Sentinel] Detected changes in requirements.txt. Updating dependencies..."
    pip install -r requirements.txt
    touch .venv # Update the venv folder timestamp so it doesn't trigger again
fi

# 3. Launch the app
python cli.py "\$@"
EOF

chmod +x "$WRAPPER_SCRIPT"
echo "[Info] Created global command at $WRAPPER_SCRIPT"

echo -e "\n========================================================"
echo " 🎉 Installation Complete! "
echo "========================================================"
echo "You can now launch the app from anywhere by typing:"
echo ""
echo "  codesentinel"
echo ""
echo "Note: If it says 'command not found', you need to add ~/.local/bin to your PATH."
echo "You can do this by running:"
echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
echo "  source ~/.bashrc"
echo "========================================================"
