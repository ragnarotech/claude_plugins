# Changelog

All notable changes to the Claude Code Launcher will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-16

### Added
- Initial release of Claude Code Launcher
- `install.sh` - One-time curl-able installer with OS detection and shell alias setup
- `bootstrap.sh` - Pre-flight certificate validation and GitLab-based version checking
- `launch-claude-code.sh` - Main launcher with stunnel MTLS tunnel, dynamic port allocation, and auto npm install of Claude Code
- Certificate expiration warnings (configurable threshold, default 30 days)
- Automatic update checking via GitLab tags API or raw version.txt fallback
- Prompted and auto-update modes with backup of previous versions
- Graceful degradation when GitLab is unreachable (air-gapped support)
- Configurable update check intervals to reduce API calls
- Robust cleanup via trap handlers on EXIT, INT, and TERM signals
- Shell alias examples for bash and zsh
