#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Claude Code Launcher - Bootstrap
# ============================================================================
# Pre-flight checks before launching Claude Code. Validates certificates,
# checks for script updates via GitLab API, and handles version management.
#
# Usage:
#   bootstrap.sh                    # Normal launch (validate + update check + launch)
#   bootstrap.sh --skip-update-check  # Skip version check, launch immediately
#   bootstrap.sh --force-update       # Force download latest version without prompting
#   bootstrap.sh --check-only         # Only check for updates, don't launch
#   bootstrap.sh --validate-certs     # Only validate certificates, don't launch
#
# Exit Codes:
#   0 - Success
#   1 - Certificate validation failed
#   2 - Update check failed (critical)
#   3 - User declined required update
#   4 - Missing prerequisites
# ============================================================================

# Script Version
BOOTSTRAP_VERSION="1.0.0"

# Configuration
INSTALL_DIR="${CLAUDE_LAUNCHER_DIR:-${HOME}/.claude-launcher}"
CERT_DIR="${CLAUDE_CERT_DIR:-${HOME}/certificates}"
REPO_BASE_URL="${CLAUDE_LAUNCHER_REPO:-https://gitlab.internal.domain/claude-tools/claude-code-launcher}"
GITLAB_PROJECT_ID="${CLAUDE_LAUNCHER_PROJECT_ID:-}"
GITLAB_TOKEN="${CLAUDE_LAUNCHER_GITLAB_TOKEN:-}"
UPDATE_CHECK_INTERVAL="${CLAUDE_LAUNCHER_UPDATE_CHECK_INTERVAL:-0}"
AUTO_UPDATE="${CLAUDE_LAUNCHER_AUTO_UPDATE:-false}"
CERT_EXPIRY_WARN_DAYS=30

# Files
VERSION_FILE="${INSTALL_DIR}/version.txt"
LAST_CHECK_FILE="${INSTALL_DIR}/.last-update-check"
UPDATE_LOG="${INSTALL_DIR}/update.log"
LAUNCHER_SCRIPT="${INSTALL_DIR}/launch-claude-code.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CHECK='\033[0;32m\xE2\x9C\x93\033[0m'
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

log_ok() {
    echo -e "[${CHECK}] $*"
}

log_update() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $*" >> "${UPDATE_LOG}" 2>/dev/null || true
}

# ============================================================================
# Argument Parsing
# ============================================================================
SKIP_UPDATE_CHECK=false
FORCE_UPDATE=false
CHECK_ONLY=false
VALIDATE_CERTS_ONLY=false
PASSTHROUGH_ARGS=()

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-update-check)
                SKIP_UPDATE_CHECK=true
                shift
                ;;
            --force-update)
                FORCE_UPDATE=true
                shift
                ;;
            --check-only)
                CHECK_ONLY=true
                shift
                ;;
            --validate-certs)
                VALIDATE_CERTS_ONLY=true
                shift
                ;;
            *)
                PASSTHROUGH_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

# ============================================================================
# Certificate Validation
# ============================================================================
validate_certificates() {
    log_info "Checking certificates..."

    local cert_file="${CERT_DIR}/${USER}.crt"
    local key_file="${CERT_DIR}/${USER}.key"
    local has_errors=false

    # Check certificate file
    if [[ -f "${cert_file}" ]]; then
        log_ok "Certificate found: ${cert_file}"
    else
        log_error "Certificate file not found: ${cert_file}"
        log_error "Contact security team to obtain your MTLS certificate"
        has_errors=true
    fi

    # Check key file
    if [[ -f "${key_file}" ]]; then
        log_ok "Key found: ${key_file}"
    else
        log_error "Key file not found: ${key_file}"
        log_error "Contact security team to obtain your MTLS key"
        has_errors=true
    fi

    if [[ "${has_errors}" == "true" ]]; then
        return 1
    fi

    # Check key permissions
    local perms
    perms=$(stat -c %a "${key_file}" 2>/dev/null || stat -f %Lp "${key_file}" 2>/dev/null || echo "unknown")
    if [[ "${perms}" == "600" ]] || [[ "${perms}" == "400" ]]; then
        log_ok "Key permissions: ${perms}"
    else
        log_warn "Key file permissions (${perms}) are too open. Recommend: chmod 600 ${key_file}"
    fi

    # Check certificate expiration (requires openssl)
    if command -v openssl &> /dev/null && [[ -f "${cert_file}" ]]; then
        local expiry_date
        expiry_date=$(openssl x509 -enddate -noout -in "${cert_file}" 2>/dev/null | cut -d= -f2 || echo "")

        if [[ -n "${expiry_date}" ]]; then
            local expiry_epoch
            local now_epoch
            expiry_epoch=$(date -d "${expiry_date}" +%s 2>/dev/null || date -j -f "%b %d %H:%M:%S %Y %Z" "${expiry_date}" +%s 2>/dev/null || echo "0")
            now_epoch=$(date +%s)

            if [[ "${expiry_epoch}" -gt 0 ]]; then
                local days_remaining=$(( (expiry_epoch - now_epoch) / 86400 ))

                if [[ ${days_remaining} -lt 0 ]]; then
                    log_error "Certificate has EXPIRED!"
                    log_error "Contact security team to renew: security@3vectors.com"
                    return 1
                elif [[ ${days_remaining} -lt ${CERT_EXPIRY_WARN_DAYS} ]]; then
                    local expiry_formatted
                    expiry_formatted=$(date -d "${expiry_date}" '+%Y-%m-%d' 2>/dev/null || echo "${expiry_date}")
                    log_warn "Certificate expires in ${days_remaining} days (${expiry_formatted})"
                    log_warn "Contact security team to renew: security@3vectors.com"

                    if [[ "${VALIDATE_CERTS_ONLY}" != "true" ]]; then
                        read -rp "Continue anyway? [Y/n]: " response
                        if [[ "${response}" =~ ^[Nn] ]]; then
                            log_info "Exiting at user request"
                            return 1
                        fi
                    fi
                else
                    local expiry_formatted
                    expiry_formatted=$(date -d "${expiry_date}" '+%Y-%m-%d' 2>/dev/null || echo "${expiry_date}")
                    log_ok "Certificate valid until: ${expiry_formatted}"
                fi
            fi
        fi
    fi

    return 0
}

# ============================================================================
# Version Management
# ============================================================================
get_local_version() {
    if [[ -f "${VERSION_FILE}" ]]; then
        cat "${VERSION_FILE}" | tr -d '[:space:]'
    else
        echo "0.0.0"
    fi
}

should_check_for_updates() {
    # Always check if interval is 0
    if [[ "${UPDATE_CHECK_INTERVAL}" -eq 0 ]]; then
        return 0
    fi

    # Check if last check file exists
    if [[ ! -f "${LAST_CHECK_FILE}" ]]; then
        return 0
    fi

    local last_check
    last_check=$(cat "${LAST_CHECK_FILE}" 2>/dev/null || echo "0")
    local now
    now=$(date +%s)
    local elapsed=$(( now - last_check ))

    if [[ ${elapsed} -ge ${UPDATE_CHECK_INTERVAL} ]]; then
        return 0
    fi

    return 1
}

get_remote_version() {
    local api_url=""
    local auth_header=""

    # Build GitLab API URL
    if [[ -n "${GITLAB_PROJECT_ID}" ]]; then
        api_url="${REPO_BASE_URL%/}/api/v4/projects/${GITLAB_PROJECT_ID}/repository/tags"
    else
        # Fallback: try to fetch version.txt directly from raw
        local raw_url="${REPO_BASE_URL%-/}/-/raw/main/version.txt"
        local remote_version
        if [[ -n "${GITLAB_TOKEN}" ]]; then
            remote_version=$(curl -fsSL --connect-timeout 10 --max-time 15 \
                -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
                "${raw_url}" 2>/dev/null | tr -d '[:space:]')
        else
            remote_version=$(curl -fsSL --connect-timeout 10 --max-time 15 \
                "${raw_url}" 2>/dev/null | tr -d '[:space:]')
        fi

        if [[ -n "${remote_version}" ]] && [[ "${remote_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "${remote_version}"
            return 0
        fi
        return 1
    fi

    # Set auth header if token available
    if [[ -n "${GITLAB_TOKEN}" ]]; then
        auth_header="-H PRIVATE-TOKEN: ${GITLAB_TOKEN}"
    fi

    # Query GitLab tags API for latest version
    local tags_json
    if [[ -n "${auth_header}" ]]; then
        tags_json=$(curl -fsSL --connect-timeout 10 --max-time 15 \
            -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
            "${api_url}?order_by=version&sort=desc&per_page=1" 2>/dev/null)
    else
        tags_json=$(curl -fsSL --connect-timeout 10 --max-time 15 \
            "${api_url}?order_by=version&sort=desc&per_page=1" 2>/dev/null)
    fi

    if [[ -z "${tags_json}" ]]; then
        return 1
    fi

    # Extract version from tag name (strip leading 'v' if present)
    local tag_name
    tag_name=$(echo "${tags_json}" | python3 -c "
import json, sys
try:
    tags = json.load(sys.stdin)
    if tags and len(tags) > 0:
        print(tags[0].get('name', '').lstrip('v'))
except:
    pass
" 2>/dev/null)

    if [[ -n "${tag_name}" ]] && [[ "${tag_name}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "${tag_name}"
        return 0
    fi

    return 1
}

version_gt() {
    # Returns 0 if $1 > $2 using version comparison
    test "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" != "$1"
}

perform_update() {
    local remote_version="$1"
    local local_version
    local_version=$(get_local_version)

    log_info "Downloading v${remote_version}..."
    log_update "Starting update from v${local_version} to v${remote_version}"

    # Download new launcher to staging location
    local staging_file="${INSTALL_DIR}/launch-claude-code.sh.staging"
    local raw_url="${REPO_BASE_URL%-/}/-/raw/main/launch-claude-code.sh"

    local download_args=(-fsSL --connect-timeout 15 --max-time 60 -o "${staging_file}")
    if [[ -n "${GITLAB_TOKEN}" ]]; then
        download_args+=(-H "PRIVATE-TOKEN: ${GITLAB_TOKEN}")
    fi

    if ! curl "${download_args[@]}" "${raw_url}" 2>/dev/null; then
        log_error "Failed to download update"
        log_update "FAILED: Download failed for v${remote_version}"
        rm -f "${staging_file}"
        return 2
    fi

    # Create backup of current script
    local backup_name="launch-claude-code.sh.backup-$(date '+%Y%m%d-%H%M%S')"
    log_info "Backing up current version..."
    cp "${LAUNCHER_SCRIPT}" "${INSTALL_DIR}/${backup_name}"
    log_update "Backed up to ${backup_name}"

    # Replace current script with new version
    mv "${staging_file}" "${LAUNCHER_SCRIPT}"
    chmod +x "${LAUNCHER_SCRIPT}"

    # Update version file
    echo "${remote_version}" > "${VERSION_FILE}"

    # Also update bootstrap if available
    local bootstrap_raw="${REPO_BASE_URL%-/}/-/raw/main/bootstrap.sh"
    local bootstrap_staging="${INSTALL_DIR}/bootstrap.sh.staging"
    local bootstrap_args=(-fsSL --connect-timeout 15 --max-time 60 -o "${bootstrap_staging}")
    if [[ -n "${GITLAB_TOKEN}" ]]; then
        bootstrap_args+=(-H "PRIVATE-TOKEN: ${GITLAB_TOKEN}")
    fi

    if curl "${bootstrap_args[@]}" "${bootstrap_raw}" 2>/dev/null; then
        cp "${INSTALL_DIR}/bootstrap.sh" "${INSTALL_DIR}/bootstrap.sh.backup-$(date '+%Y%m%d-%H%M%S')"
        mv "${bootstrap_staging}" "${INSTALL_DIR}/bootstrap.sh"
        chmod +x "${INSTALL_DIR}/bootstrap.sh"
        log_info "Bootstrap script also updated"
    else
        rm -f "${bootstrap_staging}"
    fi

    log_info "Update complete!"
    log_update "SUCCESS: Updated to v${remote_version}"

    return 0
}

check_for_updates() {
    log_info "Checking for updates..."

    # Record check timestamp
    date +%s > "${LAST_CHECK_FILE}" 2>/dev/null || true

    local local_version
    local_version=$(get_local_version)

    local remote_version
    if ! remote_version=$(get_remote_version); then
        log_warn "Failed to check for updates: GitLab API unreachable"
        log_info "Continuing with current version (v${local_version})"
        return 0
    fi

    if [[ "${local_version}" == "${remote_version}" ]]; then
        log_ok "Running latest version (v${local_version})"
        return 0
    fi

    if version_gt "${remote_version}" "${local_version}"; then
        log_warn "Update available: v${local_version} -> v${remote_version}"
        log_warn "Release notes: ${REPO_BASE_URL%-/}/-/releases/v${remote_version}"

        if [[ "${FORCE_UPDATE}" == "true" ]] || [[ "${AUTO_UPDATE}" == "true" ]]; then
            perform_update "${remote_version}"
            return $?
        fi

        read -rp "Update now? [Y/n]: " response
        if [[ ! "${response}" =~ ^[Nn] ]]; then
            perform_update "${remote_version}"
            local update_result=$?
            if [[ ${update_result} -eq 0 ]]; then
                log_info "Restarting with updated version..."
                exec "${INSTALL_DIR}/bootstrap.sh" "${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"}"
            fi
            return ${update_result}
        else
            log_info "Update skipped. Continuing with v${local_version}"
        fi
    else
        log_ok "Running latest version (v${local_version})"
    fi

    return 0
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    parse_args "$@"

    echo -e "${BLUE}[INFO]${NC} Claude Code Launcher Bootstrap v${BOOTSTRAP_VERSION}"

    # Always validate certificates
    if ! validate_certificates; then
        if [[ "${VALIDATE_CERTS_ONLY}" == "true" ]]; then
            exit 1
        fi
        log_error "Certificate validation failed. Cannot proceed."
        exit 1
    fi

    # If validate-certs only, we're done
    if [[ "${VALIDATE_CERTS_ONLY}" == "true" ]]; then
        log_info "Certificate validation complete"
        exit 0
    fi

    # Check for updates (unless skipped)
    if [[ "${SKIP_UPDATE_CHECK}" != "true" ]]; then
        if should_check_for_updates || [[ "${FORCE_UPDATE}" == "true" ]]; then
            check_for_updates
        else
            log_info "Skipping update check (checked recently)"
        fi
    fi

    # If check-only or force-update, we're done
    if [[ "${CHECK_ONLY}" == "true" ]]; then
        log_info "Check complete"
        exit 0
    fi

    if [[ "${FORCE_UPDATE}" == "true" ]]; then
        log_info "Update check complete"
        exit 0
    fi

    # Verify launcher script exists
    if [[ ! -x "${LAUNCHER_SCRIPT}" ]]; then
        log_error "Launcher script not found or not executable: ${LAUNCHER_SCRIPT}"
        log_error "Run the installer again to fix: curl -fsSL <repo-url>/install.sh | bash"
        exit 4
    fi

    # Launch Claude Code
    log_info "Launching Claude Code..."
    exec "${LAUNCHER_SCRIPT}" "${PASSTHROUGH_ARGS[@]+"${PASSTHROUGH_ARGS[@]}"}"
}

main "$@"
