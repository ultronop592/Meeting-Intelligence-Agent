# Contributing to Meeting Intelligence Agent

Thank you for your interest in contributing! This document explains how to get started, what we expect from contributions, and how the project is organized.

---

## 🏗️ Project Structure

Before contributing, familiarize yourself with the architecture described in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the phase roadmap in [`README.md`](README.md).

---

## 🚀 Getting Started

1. **Fork** the repository and clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Meeting-Intelligence-Agent.git
   cd Meeting-Intelligence-Agent
   ```

2. **Set up the backend** (Python 3.12+):
   ```bash
   python -m venv Backend/venv
   # Windows
   Backend\venv\Scripts\activate
   # macOS / Linux
   source Backend/venv/bin/activate

   pip install -r Backend/requirements.txt
   ```

3. **Copy the env file** and fill in test values:
   ```bash
   cp .env.example .env
   # Minimum for tests:
   # DATABASE_URL=sqlite+aiosqlite:///:memory:
   # SECRET_KEY=any-32-char-string
   # GROQ_API_KEY=test-key
   ```

4. **Run the tests** to confirm everything works:
   ```bash
   cd Backend
   python -m pytest tests/ -q
   # Expected: 244 passed, 0 failed
   ```

---

## 🔄 Development Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   # or: fix/bug-description, docs/section-name, test/coverage-area
   ```

2. **Make your changes** following the guidelines below.

3. **Write or update tests** — all PRs must keep the test suite passing.

4. **Run the full test suite** before pushing:
   ```bash
   cd Backend && python -m pytest tests/ -q --tb=short
   ```

5. **Run the eval suite** if you touched pipeline logic:
   ```bash
   make eval
   ```

6. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `test:` adding or fixing tests
   - `refactor:` code change without feature/fix
   - `chore:` build, deps, config changes
   - `perf:` performance improvement

7. **Open a Pull Request** against `main` with:
   - A clear description of what changed and why
   - Any benchmark metric changes (before/after)
   - Screenshots or logs if relevant

---

## 📋 Development Guidelines

### Backend (Python / FastAPI)

- **All new pipeline nodes** must be instrumented with OpenTelemetry spans (see [`core/observability.py`](Backend/core/observability.py))
- **All new outbound actions** (Jira, Slack, email, calendar) must pass through `PolicyGate` before executing
- **All new API endpoints** must have SlowAPI rate limiting applied
- **PII must never appear in logs** — use `pii_redactor.py` in all logging paths
- **New evaluation metrics** belong in the relevant `eval/phase*.py` script

### Security

- Never hardcode API keys, secrets, or passwords — use environment variables
- New credential types must be stored using the existing `encryption.py` Fernet implementation
- All security-relevant decisions must be written to `SecurityAuditLog`

### Tests

- Minimum: one test per new public function or API endpoint
- Use the existing fixtures in [`tests/conftest.py`](Backend/tests/conftest.py) — don't re-create DB setup
- Mock all external API calls (Groq, Jira, Slack, etc.) — tests must run offline
- Do not lower the 244-test baseline — only add or fix

### Documentation

- Update `README.md` if you add a new Make target, env variable, or major feature
- Update `docs/ARCHITECTURE.md` if you change the system topology
- Add a `CHANGELOG.md` entry for every PR (see format below)

---

## 📝 Changelog Format

Add an entry to [`CHANGELOG.md`](CHANGELOG.md) under `## [Unreleased]`:

```markdown
### Added
- Brief description of new feature (#PR-number)

### Fixed
- Brief description of bug fix (#PR-number)

### Changed
- Brief description of changed behavior (#PR-number)
```

---

## 🐛 Reporting Issues

- Search [existing issues](https://github.com/ultronop592/Meeting-Intelligence-Agent/issues) first
- Use the appropriate issue template (bug report / feature request)
- Include: Python version, OS, reproduction steps, and relevant logs

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
