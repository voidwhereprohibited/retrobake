# Security Policy

RetroBake takes security seriously. It handles text you type, talks to a free AI service, and runs build tools on your computer, so we design every part to be safe by default.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub: go to the repository's **Security** tab and click **Report a vulnerability**
(<https://github.com/voidwhereprohibited/retrobake/security/advisories/new>).

Please include what you found, how to reproduce it, and which version and operating system you used.
We aim to acknowledge reports within 7 days and to share a fix plan within 30 days. We will credit you in the release notes unless you ask us not to.

## Supported versions

RetroBake is in early development. Only the latest release (and `main`) receives security fixes.

## How RetroBake protects you

1. **Input cleanup** - everything you type has length limits and odd or control characters removed. Your text is treated as data only. It is never run as code or pasted into build commands.
2. **AI guarding** - your answers are placed inside a fixed prompt template to block prompt injection. Safe mode is on, and every AI result (image size and type, name length and characters) is checked before use.
3. **Sandboxed builds** - ROMs are built only from RetroBake's own tested templates, in a temporary folder, with no shell, no network, and strict size and time limits.
4. **Safe releases** - releases are built by GitHub Actions, published with SHA-256 checksums and signatures, and the code is scanned with CodeQL, Dependabot and pip-audit.
5. **Your responsibility** - you are responsible for what you create and share with RetroBake.

## Out of scope

- Games you create and share yourself.
- Problems in third-party emulators such as RetroArch (please report those upstream).
