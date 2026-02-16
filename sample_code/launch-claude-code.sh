#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Claude Code Launcher with Stunnel MTLS
# ============================================================================
# This script sets up an stunnel with MTLS authentication and launches
# Claude Code against a LiteLLM/Bedrock backend through the secure tunnel.
#
# Requirements:
# - stunnel installed
# - User certificates in ~/certificates/${USER}.{crt,key}
# - Backend inference endpoint (LiteLLM)
# - Node.js and npm (for Claude Code installation)
# ============================================================================

# Script Version
SCRIPT_VERSION="1.0.0"

# Configuration
BACKEND_HOST="${CLAUDE_BACKEND_HOST:-inference.internal.domain}"
BACKEND_PORT="${CLAUDE_BACKEND_PORT:-443}"
CERT_DIR="${CLAUDE_CERT_DIR:-${HOME}/certificates}"
CERT_FILE="${CERT_DIR}/${USER}.crt"
KEY_FILE="${CERT_DIR}/${USER}.key"
TEMP_DIR=""
STUNNEL_PID=""
LOCAL_PORT=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Logging Functions
# ============================================================================
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# ============================================================================
# Cleanup Function
# ============================================================================
cleanup() {
    local exit_code=$?
    log_info "Cleaning up..."

    # Kill stunnel if it's running
    if [[ -n "${STUNNEL_PID}" ]] && kill -0 "${STUNNEL_PID}" 2>/dev/null; then
        log_info "Terminating stunnel (PID: ${STUNNEL_PID})"
        kill "${STUNNEL_PID}" 2>/dev/null || true
        # Give it a moment to terminate gracefully
        sleep 1
        # Force kill if still running
        if kill -0 "${STUNNEL_PID}" 2>/dev/null; then
            log_warn "Force killing stunnel"
            kill -9 "${STUNNEL_PID}" 2>/dev/null || true
        fi
    fi

    # Remove temporary directory
    if [[ -n "${TEMP_DIR}" ]] && [[ -d "${TEMP_DIR}" ]]; then
        log_info "Removing temporary directory: ${TEMP_DIR}"
        rm -rf "${TEMP_DIR}"
    fi

    if [[ ${exit_code} -eq 0 ]]; then
        log_info "Cleanup complete"
    else
        log_error "Script exited with code ${exit_code}"
    fi
}

# Set up cleanup trap for normal exits and crashes
trap cleanup EXIT
trap 'exit 130' INT  # Handle Ctrl+C
trap 'exit 143' TERM # Handle termination

# ============================================================================
# Claude Code Installation
# ============================================================================
ensure_claude_code_installed() {
    if command -v claude &> /dev/null; then
        log_info "Claude Code is already installed: $(command -v claude)"
        return 0
    fi

    log_warn "Claude Code (claude) not found in PATH. Attempting npm install..."

    # Check for npm
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed. Install Node.js/npm first, then re-run this script."
        log_error "  Ubuntu/Debian: sudo apt-get install nodejs npm"
        log_error "  macOS:         brew install node"
        log_error "  Or use nvm:    https://github.com/nvm-sh/nvm"
        exit 1
    fi

    log_info "Installing Claude Code via npm..."
    if npm install -g @anthropic-ai/claude-code; then
        log_info "Claude Code installed successfully"
    else
        log_warn "Global install failed (may need sudo). Trying with sudo..."
        if sudo npm install -g @anthropic-ai/claude-code; then
            log_info "Claude Code installed successfully with sudo"
        else
            log_error "Failed to install Claude Code. Install manually:"
            log_error "  npm install -g @anthropic-ai/claude-code"
            exit 1
        fi
    fi

    # Verify installation
    if ! command -v claude &> /dev/null; then
        log_error "Claude Code was installed but 'claude' command is not in PATH."
        log_error "You may need to add the npm global bin directory to your PATH:"
        log_error "  export PATH=\"\$(npm prefix -g)/bin:\$PATH\""
        exit 1
    fi

    log_info "Claude Code is ready: $(command -v claude)"
}

# ============================================================================
# Validation Functions
# ============================================================================
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check for stunnel
    if ! command -v stunnel &> /dev/null; then
        log_error "stunnel is not installed. Install with: sudo apt-get install stunnel4"
        exit 1
    fi

    # Ensure Claude Code is installed (handles npm install if needed)
    ensure_claude_code_installed

    # Check for curl
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed"
        exit 1
    fi

    # Check for certificate files
    if [[ ! -f "${CERT_FILE}" ]]; then
        log_error "Certificate file not found: ${CERT_FILE}"
        exit 1
    fi

    if [[ ! -f "${KEY_FILE}" ]]; then
        log_error "Key file not found: ${KEY_FILE}"
        exit 1
    fi

    # Check certificate file permissions
    if [[ "$(stat -c %a "${KEY_FILE}")" != "600" ]] && [[ "$(stat -c %a "${KEY_FILE}")" != "400" ]]; then
        log_warn "Key file permissions are not restrictive. Recommend: chmod 600 ${KEY_FILE}"
    fi

    log_info "All prerequisites satisfied"
}

# ============================================================================
# Stunnel Setup
# ============================================================================
setup_stunnel() {
    log_info "Setting up stunnel..."

    # Create temporary directory for stunnel config
    TEMP_DIR=$(mktemp -d -t claude-stunnel-XXXXXX)
    log_info "Created temporary directory: ${TEMP_DIR}"

    # Find available local port
    LOCAL_PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
    log_info "Using local port: ${LOCAL_PORT}"

    # Create stunnel configuration
    local config_file="${TEMP_DIR}/stunnel.conf"
    cat > "${config_file}" << EOF
; Stunnel configuration for Claude Code MTLS
foreground = yes
debug = 5
output = ${TEMP_DIR}/stunnel.log

[claude-inference]
client = yes
accept = 127.0.0.1:${LOCAL_PORT}
connect = ${BACKEND_HOST}:${BACKEND_PORT}
cert = ${CERT_FILE}
key = ${KEY_FILE}
verify = 2
CAfile = /etc/ssl/certs/ca-certificates.crt
checkHost = ${BACKEND_HOST}
EOF

    log_info "Stunnel configuration created at: ${config_file}"

    # Start stunnel in background
    log_info "Starting stunnel..."
    stunnel "${config_file}" &
    STUNNEL_PID=$!

    log_info "Stunnel started with PID: ${STUNNEL_PID}"

    # Wait for stunnel to initialize
    sleep 2

    # Verify stunnel is still running
    if ! kill -0 "${STUNNEL_PID}" 2>/dev/null; then
        log_error "Stunnel failed to start. Check logs at: ${TEMP_DIR}/stunnel.log"
        cat "${TEMP_DIR}/stunnel.log"
        exit 1
    fi

    log_info "Stunnel is running"
}

# ============================================================================
# Connection Verification
# ============================================================================
verify_connection() {
    log_info "Verifying connection to backend inference endpoint..."

    local endpoint="http://127.0.0.1:${LOCAL_PORT}/v1/models"
    local max_attempts=5
    local attempt=1

    while [[ ${attempt} -le ${max_attempts} ]]; do
        log_info "Connection attempt ${attempt}/${max_attempts}"

        if curl -s -f -m 10 "${endpoint}" > /dev/null 2>&1; then
            log_info "Successfully connected to OpenAI-compatible endpoint"

            # Show available models
            log_info "Available models:"
            curl -s "${endpoint}" | python3 -m json.tool 2>/dev/null || echo "  (unable to parse model list)"

            return 0
        fi

        log_warn "Connection attempt failed"
        sleep 2
        ((attempt++))
    done

    log_error "Failed to verify connection after ${max_attempts} attempts"
    log_error "Endpoint: ${endpoint}"
    log_error "Check stunnel logs at: ${TEMP_DIR}/stunnel.log"
    cat "${TEMP_DIR}/stunnel.log"
    exit 1
}

# ============================================================================
# Launch Claude Code
# ============================================================================
launch_claude_code() {
    log_info "Launching Claude Code..."

    # Set environment variables for Claude Code
    export ANTHROPIC_API_URL="http://127.0.0.1:${LOCAL_PORT}/v1"
    export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy-key-for-proxy}"

    log_info "API URL: ${ANTHROPIC_API_URL}"

    # Launch Claude Code
    # Pass through any arguments provided to this script
    claude "$@"

    local claude_exit=$?
    log_info "Claude Code exited with code: ${claude_exit}"

    return ${claude_exit}
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    log_info "Starting Claude Code launcher with MTLS..."
    log_info "User: ${USER}"
    log_info "Backend: ${BACKEND_HOST}:${BACKEND_PORT}"

    check_prerequisites
    setup_stunnel
    verify_connection
    launch_claude_code "$@"

    log_info "Claude Code session completed"
}

# Run main function with all script arguments
main "$@"
