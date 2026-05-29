# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest `main` | Yes |
| Previous commits | Best effort |

## Reporting a Vulnerability

**Do not disclose security vulnerabilities in public issues.**

If you discover a security vulnerability in ainews, please report it privately:

1. **GitHub Private Vulnerability Reporting** (preferred): Use [GitHub's security advisory form](https://github.com/dbowm91/ainews/security/advisories/new)
2. **Email**: If GitHub reporting is unavailable, contact the maintainer via the email on their GitHub profile

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgement**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix or mitigation**: Depends on severity, typically within 2 weeks for critical issues

## Scope

The following are in scope for security reports:

- The ainews application code
- Docker and deployment configurations
- Documentation that includes executable commands or configurations
- Example configurations bundled with the repository

## Out of Scope

- Third-party dependencies (report these to the respective projects)
- Issues requiring physical access to the server
- Social engineering attacks

## Security Best Practices for Deployment

See [docs/security.md](docs/security.md) for detailed deployment security guidance, including:

- Environment variable security
- Redis hardening
- Database permissions
- Network security
- Secret scanning
