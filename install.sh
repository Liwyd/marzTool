#!/bin/bash
set -e

REPO="liwyd/marzTool"
INSTALL_DIR="/opt/martool"
PYTHON_MIN="3.10"

echo "========================================"
echo "  MarzTool Installer"
echo "========================================"
echo ""

check_python() {
    if command -v python3 &>/dev/null; then
        PY=python3
    elif command -v python &>/dev/null; then
        PY=python
    else
        echo "Python 3 not found. Installing..."
        apt-get update -qq
        apt-get install -y -qq python3 python3-pip python3-venv > /dev/null 2>&1
        PY=python3
    fi
    VER=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "  Python: $VER ($PY)"
}

install_deps() {
    echo "  Installing dependencies..."
    $PY -m pip install --quiet --break-system-packages requests 2>/dev/null || \
    $PY -m pip install --quiet requests
    echo "  Dependencies installed."
}

setup_master() {
    echo ""
    echo "--- Master Setup ---"
    echo "  Master runs an HTTP API server on port 8888."
    echo "  Nodes will connect to this server for config."
    echo ""
    read -p "  Master API port [8888]: " PORT
    PORT=${PORT:-8888}
    echo "  Master will run on port $PORT"
    echo ""
    echo "  Starting master mode..."
    echo "  Run 'python3 marzTool.py' to configure, then 'python3 marzTool.py --master' to start."
    echo ""
}

setup_node() {
    echo ""
    echo "--- Node Setup ---"
    echo "  Node connects to a master server."
    echo ""
    read -p "  Master URL (e.g. http://master-ip:8888): " MASTER_URL
    read -p "  Node name (for identification): " NODE_NAME
    NODE_NAME=${NODE_NAME:-"node1"}
    echo "  Node will connect to: $MASTER_URL"
    echo "  Node name: $NODE_NAME"
    echo ""
    echo "  Run 'python3 marzTool.py' to configure, then 'python3 marzTool.py --auto' to start."
    echo ""
}

echo "Select installation type:"
echo ""
echo "  1.  Standalone (default) - single server, no master/node"
echo "  2.  Master - runs API server, aggregates data from nodes"
echo "  3.  Node - connects to master, receives config, pushes data"
echo ""
read -p "  Choose [1]: " INSTALL_TYPE
INSTALL_TYPE=${INSTALL_TYPE:-1}

echo ""
echo "Checking Python..."
check_python

echo ""
echo "Installing MarzTool..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull --quiet
else
    echo "  Cloning repository..."
    git clone --quiet "https://github.com/$REPO.git" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""
install_deps

case $INSTALL_TYPE in
    2)
        setup_master
        ;;
    3)
        setup_node
        ;;
    *)
        echo ""
        echo "  Standalone mode. Run 'python3 marzTool.py' to start."
        ;;
esac

echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "  Location: $INSTALL_DIR"
echo "  Run:      python3 marzTool.py"
echo ""
