#!/bin/bash
# Memory monitoring script wrapper for the Python Flask API
# This script provides a convenient way to run the Python memory monitor

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/monitor_memory.py"

# Default values
API_URL="${API_URL:-http://localhost:8126}"
INTERVAL="${INTERVAL:-5}"
MODE="${MODE:-continuous}"

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --single, -s          Run a single memory check (default: continuous)"
    echo "  --continuous, -c     Run continuous monitoring (default)"
    echo "  --simple             Use simple memory endpoint"
    echo "  --interval SECONDS   Set monitoring interval (default: 5)"
    echo "  --api-url URL        Set API URL (default: http://localhost:8126)"
    echo "  --log FILE           Log output to JSON file"
    echo "  --json               Output in JSON format (single mode only)"
    echo "  --help, -h           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --continuous --interval 5"
    echo "  $0 --single --simple"
    echo "  $0 --continuous --log memory_log.json"
}

# Parse arguments
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --single|-s)
            MODE="single"
            shift
            ;;
        --continuous|-c)
            MODE="continuous"
            shift
            ;;
        --simple)
            ARGS+=("--simple")
            shift
            ;;
        --interval)
            INTERVAL="$2"
            ARGS+=("--interval" "$2")
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            ARGS+=("--api-url" "$2")
            shift 2
            ;;
        --log)
            ARGS+=("--log" "$2")
            shift 2
            ;;
        --json)
            ARGS+=("--json")
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: Python monitoring script not found at $PYTHON_SCRIPT"
    exit 1
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH"
    exit 1
fi

# Run the Python script
if [ "$MODE" = "continuous" ]; then
    python3 "$PYTHON_SCRIPT" --continuous "${ARGS[@]}"
else
    python3 "$PYTHON_SCRIPT" "${ARGS[@]}"
fi

