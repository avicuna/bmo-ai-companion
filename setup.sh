#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Pi Local Assistant Setup Script${NC}"

# 1. Install System Dependencies (The "Hidden" Requirements)
echo -e "${YELLOW}[1/6] Installing System Tools (apt)...${NC}"
sudo apt update
sudo apt install -y python3-tk libasound2-dev libportaudio2 libatlas-base-dev cmake build-essential espeak-ng git

# 2. Create Folders
echo -e "${YELLOW}[2/6] Creating Folders...${NC}"
mkdir -p piper
mkdir -p sounds/greeting_sounds
mkdir -p sounds/thinking_sounds
mkdir -p sounds/ack_sounds
mkdir -p sounds/error_sounds
mkdir -p faces/idle
mkdir -p faces/listening
mkdir -p faces/thinking
mkdir -p faces/speaking
mkdir -p faces/error
mkdir -p faces/warmup

# 3. Download Piper (Architecture Check)
echo -e "${YELLOW}[3/6] Setting up Piper TTS...${NC}"
ARCH=$(uname -m)
if [ "$ARCH" == "aarch64" ]; then
    # FIXED: Using the specific 2023.11.14-2 release known to work on Pi
    wget -O piper.tar.gz https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz
    tar -xvf piper.tar.gz -C piper --strip-components=1
    rm piper.tar.gz
else
    echo -e "${RED}⚠️  Not on Raspberry Pi (aarch64). Skipping Piper download.${NC}"
fi

# 4. Download Voice Model
echo -e "${YELLOW}[4/6] Downloading Voice Model...${NC}"
cd piper
wget -nc -O en_GB-semaine-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx
wget -nc -O en_GB-semaine-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json
cd ..

# 5. Install Python Libraries
echo -e "${YELLOW}[5/6] Installing Python Libraries...${NC}"
# Check if venv exists, if not create it
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Pull AI Models (Moondream only — Claude runs via API)
echo -e "${YELLOW}[6/7] Checking AI Models...${NC}"
if command -v ollama &> /dev/null; then
    echo "Pulling Moondream (vision model)..."
    ollama pull moondream
    echo -e "${GREEN}✅ Moondream loaded. Claude Haiku will be used via API for text.${NC}"
else
    echo -e "${RED}❌ Ollama not found. Install it: curl -fsSL https://ollama.com/install.sh | sh${NC}"
fi

# 7. OpenWakeWord Model
if [ ! -f "wakeword.onnx" ]; then
    echo -e "${YELLOW}Downloading default 'Hey Jarvis' wake word...${NC}"
    curl -L -o wakeword.onnx https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/hey_jarvis_v0.1.onnx
fi

# 8. Check for Anthropic API Key
echo -e "${YELLOW}[7/7] Checking Claude API Key...${NC}"
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}⚠️  ANTHROPIC_API_KEY not set!${NC}"
    echo -e "${YELLOW}Set it with: export ANTHROPIC_API_KEY='your-key-here'${NC}"
    echo -e "${YELLOW}Or add to ~/.bashrc for persistence.${NC}"
else
    echo -e "${GREEN}✅ ANTHROPIC_API_KEY is set.${NC}"
fi

# 9. Check for ElevenLabs API Key
echo -e "${YELLOW}[8/8] Checking ElevenLabs API Key...${NC}"
if [ -z "$ELEVEN_API_KEY" ]; then
    echo -e "${RED}⚠️  ELEVEN_API_KEY not set!${NC}"
    echo -e "${YELLOW}Set it with: export ELEVEN_API_KEY='your-key-here'${NC}"
    echo -e "${YELLOW}BMO will use Piper TTS (generic voice) as fallback.${NC}"
else
    echo -e "${GREEN}✅ ELEVEN_API_KEY is set.${NC}"
fi

echo -e "${GREEN}✨ Setup Complete!${NC}"
echo -e "${GREEN}Run: source venv/bin/activate && python agent.py${NC}"
echo -e "${YELLOW}Make sure these env vars are exported before running:${NC}"
echo -e "${YELLOW}  ANTHROPIC_API_KEY (required)${NC}"
echo -e "${YELLOW}  ELEVEN_API_KEY (for BMO voice, optional)${NC}"
