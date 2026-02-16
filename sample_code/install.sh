#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Claude Code Launcher - Installer
# ============================================================================
# One-time installation script. Downloads bootstrap.sh and launch-claude-code.sh
# from GitLab and sets up the claude-code command.
#
# Usage:
#   curl -fsSL https://gitlab.internal.domain/claude-tools/claude-code-launcher/-/raw/main/install.sh | bash
#
# Or download and inspect first:
#   curl -fsSL <url>/install.sh -o install.sh && chmod +x install.sh && ./install.sh
# ============================================================================

# Script Version
INSTALLER_VERSION="1.0.0"

# Configuration
REPO_BASE_URL="${CLAUDE_LAUNCHER_REPO:-https://gitlab.internal.domain/claude-tools/claude-code-launcher/-/raw/main}"
INSTALL_DIR="${CLAUDE_LAUNCHER_DIR:-${HOME}/.claude-launcher}"
CERT_DIR="${CLAUDE_CERT_DIR:-${HOME}/certificates}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $*"
}

# ============================================================================
# OS Detection
# ============================================================================
detect_os() {
    local os=""
    case "$(uname -s)" in
        Linux*)  os="linux" ;;
        Darwin*) os="macos" ;;
        *)       os="unknown" ;;
    esac
    echo "${os}"
}

# ============================================================================
# Prerequisite Check
# ============================================================================
check_prerequisites() {
    log_step "Checking prerequisites..."

    local missing=()

    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi

    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_error "Install them before running this installer."

        local os
        os=$(detect_os)
        if [[ "${os}" == "linux" ]]; then
            log_error "  Ubuntu/Debian: sudo apt-get install ${missing[*]}"
            log_error "  RHEL/CentOS:   sudo yum install ${missing[*]}"
        elif [[ "${os}" == "macos" ]]; then
            log_error "  macOS: brew install ${missing[*]}"
        fi

        exit 3
    fi

    log_info "All prerequisites found"
}

# ============================================================================
# Download Function with Retry
# ============================================================================
download_file() {
    local url="$1"
    local dest="$2"
    local description="$3"
    local max_attempts=3
    local attempt=1

    while [[ ${attempt} -le ${max_attempts} ]]; do
        log_info "Downloading ${description}... (attempt ${attempt}/${max_attempts})"

        if curl -fsSL --connect-timeout 15 --max-time 60 -o "${dest}" "${url}"; then
            log_info "Downloaded ${description} successfully"
            return 0
        fi

        log_warn "Download attempt ${attempt} failed"
        sleep 2
        ((attempt++))
    done

    log_error "Failed to download ${description} after ${max_attempts} attempts"
    log_error "URL: ${url}"
    return 1
}

# ============================================================================
# Shell Profile Detection
# ============================================================================
detect_shell_profile() {
    local shell_name
    shell_name=$(basename "${SHELL:-/bin/bash}")

    case "${shell_name}" in
        zsh)
            if [[ -f "${HOME}/.zshrc" ]]; then
                echo "${HOME}/.zshrc"
            else
                echo "${HOME}/.zprofile"
            fi
            ;;
        bash)
            if [[ -f "${HOME}/.bashrc" ]]; then
                echo "${HOME}/.bashrc"
            elif [[ -f "${HOME}/.bash_profile" ]]; then
                echo "${HOME}/.bash_profile"
            else
                echo "${HOME}/.bashrc"
            fi
            ;;
        *)
            # Default to bashrc
            echo "${HOME}/.bashrc"
            ;;
    esac
}

# ============================================================================
# Alias Setup
# ============================================================================
setup_alias() {
    local profile
    profile=$(detect_shell_profile)
    local alias_line="alias claude-code=\"\${HOME}/.claude-launcher/bootstrap.sh\""
    local marker="# Claude Code Launcher"

    log_step "Setting up shell alias..."

    # Check if alias already exists
    if [[ -f "${profile}" ]] && grep -q "${marker}" "${profile}" 2>/dev/null; then
        log_info "Shell alias already configured in ${profile}"
        return 0
    fi

    # Append alias to profile
    {
        echo ""
        echo "${marker}"
        echo "${alias_line}"
    } >> "${profile}"

    log_info "Added 'claude-code' alias to ${profile}"
    log_warn "Run 'source ${profile}' or open a new terminal to use the alias"
}

# ============================================================================
# Certificate Check
# ============================================================================
check_certificates() {
    log_step "Checking certificates..."

    local cert_file="${CERT_DIR}/${USER}.crt"
    local key_file="${CERT_DIR}/${USER}.key"

    if [[ ! -d "${CERT_DIR}" ]]; then
        log_warn "Certificate directory not found: ${CERT_DIR}"
        log_warn "Create it and add your certificates before running claude-code:"
        log_warn "  mkdir -p ${CERT_DIR}"
        log_warn "  # Copy your .crt and .key files there"
        log_warn "  chmod 600 ${CERT_DIR}/${USER}.key"
        return 0
    fi

    if [[ -f "${cert_file}" ]]; then
        log_info "Certificate found: ${cert_file}"
    else
        log_warn "Certificate not found: ${cert_file}"
        log_warn "Contact security team to obtain your MTLS certificate"
    fi

    if [[ -f "${key_file}" ]]; then
        log_info "Key found: ${key_file}"
        local perms
        perms=$(stat -c %a "${key_file}" 2>/dev/null || stat -f %Lp "${key_file}" 2>/dev/null || echo "unknown")
        if [[ "${perms}" != "600" ]] && [[ "${perms}" != "400" ]]; then
            log_warn "Key file permissions (${perms}) are too open. Fixing..."
            chmod 600 "${key_file}"
            log_info "Key file permissions set to 600"
        else
            log_info "Key permissions OK (${perms})"
        fi
    else
        log_warn "Key not found: ${key_file}"
        log_warn "Contact security team to obtain your MTLS key"
    fi
}

# ============================================================================
# Main Installation
# ============================================================================
main() {
    local os
    os=$(detect_os)

    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Claude Code Launcher - Installer v${INSTALLER_VERSION}${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    log_info "Detected OS: ${os}"
    log_info "Installing to: ${INSTALL_DIR}"
    echo ""

    if [[ "${os}" == "unknown" ]]; then
        log_error "Unsupported operating system: $(uname -s)"
        log_error "This installer supports Linux and macOS only."
        exit 1
    fi

    # Check prerequisites
    check_prerequisites

    # Create installation directory
    log_step "Creating installation directory..."
    mkdir -p "${INSTALL_DIR}"
    log_info "Directory created: ${INSTALL_DIR}"

    # Download scripts
    log_step "Downloading launcher scripts..."

    if ! download_file "${REPO_BASE_URL}/bootstrap.sh" "${INSTALL_DIR}/bootstrap.sh" "bootstrap.sh"; then
        log_error "Installation failed: could not download bootstrap.sh"
        exit 1
    fi

    if ! download_file "${REPO_BASE_URL}/launch-claude-code.sh" "${INSTALL_DIR}/launch-claude-code.sh" "launch-claude-code.sh"; then
        log_error "Installation failed: could not download launch-claude-code.sh"
        exit 1
    fi

    if ! download_file "${REPO_BASE_URL}/version.txt" "${INSTALL_DIR}/version.txt" "version.txt"; then
        log_warn "Could not download version.txt, creating default"
        echo "1.0.0" > "${INSTALL_DIR}/version.txt"
    fi

    # Set executable permissions
    log_step "Setting permissions..."
    chmod +x "${INSTALL_DIR}/bootstrap.sh"
    chmod +x "${INSTALL_DIR}/launch-claude-code.sh"
    log_info "Scripts are now executable"

    # Set up shell alias
    setup_alias

    # Check certificates
    check_certificates

    # Run bootstrap to validate setup
    log_step "Validating installation..."
    if "${INSTALL_DIR}/bootstrap.sh" --validate-certs 2>/dev/null; then
        log_info "Validation passed"
    else
        log_warn "Validation had warnings (this is OK if certificates are not yet installed)"
    fi

    # Summary
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    log_info "Installation directory: ${INSTALL_DIR}"
    log_info "Scripts installed:"
    log_info "  - ${INSTALL_DIR}/bootstrap.sh"
    log_info "  - ${INSTALL_DIR}/launch-claude-code.sh"
    log_info "  - ${INSTALL_DIR}/version.txt"
    echo ""
    log_info "To get started:"
    log_info "  1. Source your shell profile or open a new terminal"
    log_info "  2. Run: claude-code"
    echo ""
    log_info "Or run directly: ${INSTALL_DIR}/bootstrap.sh"
    echo ""
}

main "$@"
