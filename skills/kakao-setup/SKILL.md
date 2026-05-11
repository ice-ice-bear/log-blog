---
name: kakao-setup
description: Set up KakaoTalk integration prerequisites for /logblog:kakao-post on macOS. Installs kakaocli via Homebrew, walks through Xcode + Full Disk Access requirements, derives the KAKAOCLI_KEY (SQLCipher DB decryption key) via auto-auth or SHA-512 brute-force fallback, persists the key to the user's shell rc file, optionally installs the kakaotalk-chat-analyzer wrapper, and verifies the full chain. Use before the first /logblog:kakao-post run on a new machine, or when KAKAOCLI_KEY is missing or stale.
---

# Log-Blog: KakaoTalk Integration Setup

You are setting up everything `/logblog:kakao-post` depends on. The pipeline is:

```
KakaoTalk Mac app (logged in)
        │
        ▼ SQLCipher-encrypted local DB
   kakaocli (Homebrew CLI, requires KAKAOCLI_KEY)
        │
        ▼ JSON
   kakao-chat (kakaotalk-chat-analyzer wrapper)
        │
        ▼
   /logblog:kakao-post
```

This skill installs and configures the first three layers. The fourth — `/logblog:kakao-post` — is already installed by virtue of being part of this plugin.

**Project root**: The directory where you are running Claude Code (the log-blog repo).
**Platform**: macOS only. KakaoTalk doesn't ship a Linux/Windows desktop client and the SQLCipher DB path is macOS-specific.

---

## Phase 1: Environment Diagnosis

Run these checks in parallel and report a status table:

```bash
sw_vers -productName
sw_vers -productVersion
brew --version 2>/dev/null | head -1
xcode-select -p 2>/dev/null
ls -d /Applications/KakaoTalk.app 2>/dev/null && echo "KakaoTalk: installed" || echo "KakaoTalk: NOT installed"
which kakaocli && kakaocli --version 2>&1 | head -1 || echo "kakaocli: NOT installed"
test -n "$KAKAOCLI_KEY" && echo "KAKAOCLI_KEY: set (len=${#KAKAOCLI_KEY})" || echo "KAKAOCLI_KEY: NOT SET"
ls -d ~/Documents/github/kakaotalk-chat-analyzer 2>/dev/null && echo "analyzer repo: present" || echo "analyzer repo: not at default path"
```

| Check | Pass | Fail action |
|---|---|---|
| macOS | Show product + version | Stop. Tell user this skill is macOS-only |
| Homebrew | Show version | Stop. Tell user: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` |
| Xcode select path | Path is `/Applications/Xcode.app/Contents/Developer` | Will fix in Phase 2 |
| KakaoTalk.app | Installed | Stop. Tell user to install from Mac App Store and **log in** before running this skill again |
| kakaocli | Note version | Will install in Phase 3 |
| KAKAOCLI_KEY | Note "already set" — ask user if they want to re-derive | Will derive in Phase 5 |
| analyzer repo | Note path | Will clone in Phase 4 |

Then check Full Disk Access for the user's terminal app. There is no scriptable way to check this — surface it as a manual step:

> "**IMPORTANT — Full Disk Access required.**
>
> KakaoTalk's local DB sits in `~/Library/...` which macOS protects. Open:
>
> System Settings → Privacy & Security → Full Disk Access
>
> Add your terminal app (Terminal, iTerm2, Warp, Ghostty, etc.) AND your editor if running Claude Code from inside one (VS Code, Cursor, Zed). After granting access, **fully quit and relaunch the terminal/editor** for the change to take effect.
>
> If you skip this, every `kakaocli` call will fail with permission errors, even with the key set correctly.
>
> Done? (y/n)"

If user says no, stop and tell them to come back after granting access.

---

## Phase 2: Xcode Full Installation

`kakaocli` is a Swift binary built from source by Homebrew. **Command Line Tools alone are NOT enough** — it needs the full Xcode app.

Check:
```bash
xcode-select -p
ls -d /Applications/Xcode.app 2>/dev/null
```

If `xcode-select -p` returns `/Library/Developer/CommandLineTools` (CLT only) and `/Applications/Xcode.app` does not exist:

> "Full Xcode is required (Command Line Tools alone won't build kakaocli).
>
> 1. Open the Mac App Store and install Xcode (~10GB, this takes a while)
> 2. Launch Xcode once to accept the initial setup
> 3. Then run these to point the toolchain at the full Xcode:
>
>    `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
>    `sudo xcodebuild -license accept`
>
> Done? (y/n)"

Wait for user confirmation. Verify after:

```bash
xcode-select -p
# Expected: /Applications/Xcode.app/Contents/Developer
```

If it still shows CLT path, repeat the `sudo xcode-select -s ...` step with the user.

---

## Phase 3: Install kakaocli via Homebrew

```bash
brew tap silver-flight-group/tap
brew install silver-flight-group/tap/kakaocli
```

If `brew install` fails with a Swift build error, the most common causes are:
- Xcode not selected (re-run Phase 2)
- Xcode license not accepted (`sudo xcodebuild -license accept`)
- Outdated Xcode (update from App Store)

Verify:

```bash
kakaocli --version
kakaocli --help | head -20
```

You should see version output and a subcommand list including `auth`, `chats`, `messages`, `status`.

---

## Phase 4: Install the kakaotalk-chat-analyzer wrapper (recommended)

`/logblog:kakao-post` invokes `kakao-chat` (the wrapper that adds `unread`, batch JSON dump, etc. on top of `kakaocli`). Install it now so the user can run `kakao-chat` directly without `uv run --directory` prefixes everywhere.

Default install path: `~/Documents/github/kakaotalk-chat-analyzer`. Ask the user before changing it.

```bash
ANALYZER_PARENT="$HOME/Documents/github"
mkdir -p "$ANALYZER_PARENT"
cd "$ANALYZER_PARENT"
git clone https://github.com/ice-ice-bear/kakaotalk-chat-analyzer
cd kakaotalk-chat-analyzer
uv sync
```

If the `git clone` fails because the user doesn't have access (private repo), ask them for the path to their existing clone or fork.

After install, expose `kakao-chat` on PATH. The cleanest option is a tiny zsh function in `~/.zshrc`:

```bash
# Append to ~/.zshrc (idempotent — check first):
ANALYZER_PATH="$HOME/Documents/github/kakaotalk-chat-analyzer"
if ! grep -q "kakao-chat()" ~/.zshrc 2>/dev/null; then
  cat >> ~/.zshrc <<EOF

# kakaotalk-chat-analyzer wrapper (added by /logblog:kakao-setup)
kakao-chat() {
  (cd "$ANALYZER_PATH" && uv run kakao-chat "\$@")
}
EOF
  echo "Added kakao-chat() function to ~/.zshrc"
else
  echo "kakao-chat() already in ~/.zshrc — skipping"
fi
```

If the user is on bash, replace `~/.zshrc` with `~/.bashrc`. Confirm shell with `echo $SHELL`.

Tell the user:
> "Reload your shell to pick up the new function: `source ~/.zshrc`. Or open a new terminal tab."

---

## Phase 5: Derive KAKAOCLI_KEY

The key is the SQLCipher DB decryption key, derived from the user's KakaoTalk **User ID** + machine UUID via PBKDF2.

### Phase 5A: Try auto-auth first (works for ~70% of users)

```bash
kakaocli auth
```

This attempts to brute-force the User ID by hashing integers and comparing to the account hash from the local DB header. It has a 10-second timeout (kakaocli v0.6.0+) and silently fails for User IDs above ~22M.

If `kakaocli auth` succeeds, it prints the secureKey. Capture it:

```bash
DERIVED_KEY=$(kakaocli auth 2>&1 | grep -oE 'Secure key: [a-f0-9]+' | awk '{print $3}')
echo "Derived key length: ${#DERIVED_KEY}"
# Expected: 256 hex chars
```

If `DERIVED_KEY` is 256 chars, **skip to Phase 6** (persist the key).

If empty or wrong length, the auto-auth timed out. Move to Phase 5B.

### Phase 5B: Manual brute-force fallback

This is needed when the User ID exceeds kakaocli's 10-second auto-auth budget (~22M+).

Step 1 — get the account hash from the DB header:

```bash
kakaocli status 2>&1 | grep -i "Account hash"
# Output: "Account hash: <128-char hex>"
ACCOUNT_HASH=$(kakaocli status 2>&1 | grep -oE 'Account hash: [a-f0-9]+' | awk '{print $3}')
echo "Account hash captured: ${#ACCOUNT_HASH} chars (expect 128)"
```

Step 2 — also capture the Device UUID for Phase 5C:

```bash
DEVICE_UUID=$(kakaocli status 2>&1 | grep -oE 'Device UUID: [A-F0-9-]+' | awk '{print $3}')
echo "Device UUID captured: ${#DEVICE_UUID} chars (expect 36 with dashes)"
```

Step 3 — Python brute-force the User ID against the account hash. This uses pure stdlib so no extra deps:

```bash
USER_ID=$(python3 -c "
import hashlib, time, sys
target = '$ACCOUNT_HASH'
target_bytes = bytes.fromhex(target)
start = time.time()
for i in range(500_000_000):
    if hashlib.sha512(str(i).encode()).digest() == target_bytes:
        print(i)
        sys.exit(0)
    if i % 10_000_000 == 0 and i > 0:
        print(f'  {i/1_000_000:.0f}M checked... ({time.time()-start:.0f}s)', file=sys.stderr)
print('NOT_FOUND', file=sys.stderr)
sys.exit(1)
")
echo "User ID found: $USER_ID"
```

Time estimate: 1-3 minutes per 100M IDs on Apple Silicon. If the search exceeds 500M without finding a match, increase the upper bound (the script's `range(500_000_000)`) — most users fall well below 200M.

If the script returns NOT_FOUND, double-check that:
- KakaoTalk is actually logged in (`kakaocli status` should show your account)
- Full Disk Access is granted to the terminal that ran `kakaocli status` (Phase 1)
- The account hash captured is exactly 128 hex chars

### Phase 5C: Derive the secureKey from User ID + UUID

```bash
KAKAOCLI_KEY=$(python3 -c "
import hashlib, base64
uuid = '$DEVICE_UUID'
user_id = $USER_ID

data = uuid.encode()
hashed = base64.b64encode(hashlib.sha1(data).digest() + hashlib.sha256(data).digest()).decode()

parts = ['A', hashed, '|', 'F', uuid[:5], 'H', str(user_id), '|', uuid[7:]]
hawawa = 'F'.join(parts)
salt = uuid[int(len(uuid) * 0.3):]
dk = hashlib.pbkdf2_hmac('sha256', hawawa[::-1].encode(), salt.encode(), 100000, dklen=128)
print(dk.hex())
")
echo "Derived KAKAOCLI_KEY length: ${#KAKAOCLI_KEY} (expect 256)"
```

If length is 256, proceed to Phase 6. If not, something went wrong with UUID or User ID — re-run Phase 5B and capture the values again.

---

## Phase 6: Persist KAKAOCLI_KEY

Add to the user's shell rc file. Detect shell first:

```bash
RC_FILE="$HOME/.zshrc"
[ "$(basename "$SHELL")" = "bash" ] && RC_FILE="$HOME/.bashrc"
echo "Will write to: $RC_FILE"
```

Idempotent append (skip if already set):

```bash
if grep -q "^export KAKAOCLI_KEY=" "$RC_FILE" 2>/dev/null; then
  echo "KAKAOCLI_KEY already set in $RC_FILE"
  echo "If you want to replace it, edit the line manually."
else
  echo "" >> "$RC_FILE"
  echo "# kakaocli DB decryption key (added by /logblog:kakao-setup)" >> "$RC_FILE"
  echo "export KAKAOCLI_KEY=\"$KAKAOCLI_KEY\"" >> "$RC_FILE"
  echo "Appended KAKAOCLI_KEY to $RC_FILE"
fi
```

Tell the user:
> "Reload shell to pick up the env var: `source $RC_FILE` — or open a new terminal tab. Existing shells won't see the variable until they reload."

---

## Phase 7: Verification — End-to-End Smoke Test

Reload the env var in the current shell (so the rest of this skill can verify):

```bash
source "$RC_FILE"
test -n "$KAKAOCLI_KEY" && echo "KAKAOCLI_KEY is set in this shell (len=${#KAKAOCLI_KEY})" || echo "STILL NOT SET — open a new terminal and re-run from Phase 7"
```

### Smoke test 1: kakaocli direct

```bash
kakaocli chats --json --limit 3 --key "$KAKAOCLI_KEY" 2>&1 | head -20
```

Expected: a JSON array of 3 chat entries with fields `id`, `display_name`, `member_count`, `unread_count`, `last_message_at`.

If you get `Error: SQL error: prepare: file is not a database`:
- The key is wrong. Re-run Phase 5.

If you get a permission error:
- Full Disk Access not granted, or terminal not relaunched after granting. Go back to Phase 1.

### Smoke test 2: kakao-chat wrapper

```bash
kakao-chat chats --unread-only --min-members 100 2>&1 | head -10
```

Expected: lines like `[<chat_id>] (display_name) (N members) [unread: M]`.

If `kakao-chat: command not found`:
- The shell function from Phase 4 hasn't been picked up. Run `source $RC_FILE` and try again. If still failing, check that the analyzer repo path in the function is correct.

### Smoke test 3: end-to-end JSON dump

```bash
kakao-chat unread --min-members 100 --max-chats 1 --since 24h --json > /tmp/kakao-smoke.json 2>/tmp/kakao-smoke.err
echo "exit=$?"
wc -c /tmp/kakao-smoke.json
head -c 500 /tmp/kakao-smoke.json
echo ""
[ -s /tmp/kakao-smoke.err ] && echo "stderr:" && cat /tmp/kakao-smoke.err
```

Expected: a JSON object with `chat_count: 1` and at least one chat in `chats`. If empty (just `{"chat_count": 0, "chats": []}`), it means the user has no unread chats meeting the filter — that's fine for the smoke test, the chain is working.

---

## Phase 8: Final Status Report

Print a status table to the user:

```
✓ macOS detected ({version})
✓ Homebrew available
✓ Xcode full installation, license accepted
✓ KakaoTalk Mac app installed (and assumed logged in)
✓ Full Disk Access granted (manually confirmed)
✓ kakaocli installed (v{version})
✓ kakaotalk-chat-analyzer cloned at {path}
✓ kakao-chat() shell function added to {rc_file}
✓ KAKAOCLI_KEY derived ({256 chars}) and persisted to {rc_file}
✓ Smoke test: kakaocli chats returns {N} chats
✓ Smoke test: kakao-chat unread returns {N} unread chats

Setup complete. Run /logblog:kakao-post to mine open-chat URLs into blog posts.
```

If any check failed, list it as `✗` and the corresponding remediation.

---

## Common Pitfalls (record from prior runs)

- **CLT-only Xcode** — `brew install kakaocli` will appear to start but fail with "swift: command not found" or similar mid-build. Phase 2 catches this.
- **Full Disk Access not relaunched** — Granting access in System Settings is not enough; the terminal/editor must be fully quit and reopened (Cmd-Q, then relaunch). A simple "close window" doesn't reload the entitlement.
- **kakaocli auto-auth timeout** — Default is 10s; for User IDs above ~22M it silently returns no key. The brute-force in Phase 5B is the workaround. Don't try to raise kakaocli's timeout — it doesn't expose a flag, and the Python loop is faster than kakaocli's internal hash function call.
- **Wrong key length** — The derived key must be exactly **256 hex chars** (128 bytes hex-encoded). Anything shorter means PBKDF2 didn't run with `dklen=128`. Don't use `--verbose` output of `kakaocli auth` to capture the key — it can truncate. Always derive via the Python script in Phase 5C.
- **macOS keychain doesn't help here** — The KakaoTalk DB key is NOT in the macOS keychain; it's derived per-machine from User ID + IOPlatformUUID. Don't waste time looking for a `security find-generic-password` shortcut.
- **`open.kakao.com` and `kko.to` URLs** — These are internal KakaoTalk links and are filtered out of `kakao-chat extract` output by default. If they appear in the JSON, you're on a stale version of the analyzer; `cd ~/Documents/github/kakaotalk-chat-analyzer && git pull && uv sync`.
- **Multiple Mac accounts** — The Device UUID is per-machine, but the User ID is per-account. If the user has more than one KakaoTalk account on the same Mac, they need to repeat Phase 5 per account and store keys in separate env var names (`KAKAOCLI_KEY_WORK`, `KAKAOCLI_KEY_PERSONAL`).
- **macOS upgrade resets Full Disk Access** — After a major macOS update (Sonoma → Sequoia, etc.) re-grant Full Disk Access. The setup will start failing silently otherwise.
