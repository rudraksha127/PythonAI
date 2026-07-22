# 🔐 Next Step: Login / Authentication Feature

## Goal

Add a secure login/authentication system to the PythonAI CLI tool so users can authenticate before using certain commands (e.g., `ask`, `train`, `probe`), or switch between different user profiles/API keys.

---

## 📝 Prompt to Continue

> Copy-paste this into Codebuff to continue:

```
Please implement a login/authentication feature for the PythonAI project. Here's what I need:

### Requirements

1. **CLI Login Command** — Add a `python -m src.cli login` command that:
   - Prompts the user for username/email and password (hide password input)
   - Stores credentials securely (hashed) in a local config file (`~/.pythonai/config.json`)
   - Supports `--check` flag to show if user is currently logged in
   - Supports `--logout` flag to clear stored session

2. **Auth Module** — Create `src/auth/` package with:
   - `auth.py` — Core authentication logic (password hashing with bcrypt or hashlib, token generation, session management)
   - `config.py` — Read/write config file at `~/.pythonai/config.json`
   - `decorators.py` — `@requires_auth` decorator to protect CLI commands
   - `__init__.py` — Package init with clean exports

3. **Protected Commands** — Protect `ask`, `train`, and `eval` commands so they require login:
   - Show a helpful error message if user is not logged in
   - Add `--no-auth` flag to skip auth check for local/offline use

4. **Secure Storage** — Store credentials securely:
   - Hash passwords with SHA-256 + salt or bcrypt
   - Store only the hash, never plaintext
   - Keep config file permissions restricted (owner-only read/write)

5. **Config File Format** (`~/.pythonai/config.json`):
   ```json
   {
     "user": {
       "username": "john",
       "password_hash": "sha256$salt$hash",
       "token": "session-token-here",
       "logged_in_at": "2026-05-21T10:00:00"
     },
     "settings": {
       "offline_mode": false,
       "default_model": "qwen2.5-coder:14b"
     }
   }
   ```

6. **Test Coverage** — Add tests in `tests/test_auth.py`:
   - Test password hashing and verification
   - Test config file read/write
   - Test `@requires_auth` decorator
   - Test login/logout flow

### Implementation Notes

- Use only stdlib + common packages already in `requirements.txt`
- Follow existing project conventions (see `src/cli.py` for CLI patterns)
- Keep it simple — no need for a backend server, this is local-only auth
- Use `getpass.getpass()` for hidden password input
- Store config in user home directory, not in the project folder
```

---

## 🧩 Files to Create / Modify

| File | Action |
|------|--------|
| `src/auth/__init__.py` | **Create** — Package init |
| `src/auth/auth.py` | **Create** — Core auth logic |
| `src/auth/config.py` | **Create** — Config file manager |
| `src/auth/decorators.py` | **Create** — Auth decorators |
| `src/cli.py` | **Modify** — Add `login` subcommand + protect existing commands |
| `tests/test_auth.py` | **Create** — Auth unit tests |
| `docs/NEXT_LOGIN_FEATURE.md` | **Modify** — Mark as complete after implementation |

---

## ✅ Current Status

[ ] Not started  
[ ] In progress  
[x] Completed  

---

> ✅ **Implemented on 2026-05-21** — Login system fully working with 24/24 tests passing.
