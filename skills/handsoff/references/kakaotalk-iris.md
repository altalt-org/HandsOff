# Iris on handsoff — install & setup

> Reference doc loaded on demand by the `handsoff` skill. Scope: install KakaoTalk, deploy the Iris bot framework on top of it, expose Iris through the handsoff reverse proxy, verify the install. Out of scope: how to use Iris's endpoints. Once the Step 5 verification probe passes, stop and hand off — let the user (or another skill) drive Iris from there.

## Prerequisites

- `handsoff` MCP server connected (provides `app_install`, `push_file`, `adb_shell`, `expose_service`, `system_button`, `set_agent_keyboard`, etc.).
- Target device is rooted (`su root` works). Verify before installing Iris.
- The user has logged into a real KakaoTalk account on the device — see Step 1 for the hand-off protocol. KakaoTalk login is interactive (phone + SMS) and **must not be automated**.
- A bearer token for the handsoff reverse proxy (the public host is `https://handsoff.gethandsoff.com`). The user provides it; never hardcode it into committed code.

## Step 1 — Install KakaoTalk, then STOP and hand off to the user

Standard play-store-style install through APKPure. Iris targets KakaoTalk's on-device SQLite, so the package must be `com.kakao.talk`.

```
mcp__handsoff__app_install(package="com.kakao.talk", source="apkpure")
```

This pulls the XAPK split-bundle and installs everything in one shot.

### STOP. Do not proceed past this point until the user confirms they are logged in.

After install, **end your turn** with a clear message to the user. Do not attempt to drive the login UI, do not call `open_app`, do not poll. Login requires the user's phone, an SMS code, and several human decisions, including the device-mode choice below. Trying to "help" through it will burn time and risk locking the account.

The message to the user must explain three things:

1. **Action required:** open the handsoff web console and log into KakaoTalk there.
2. **By default, the device will be set up in tablet mode.** KakaoTalk allows one mobile device, one tablet, and one computer signed in to the same account simultaneously. Tablet mode means the user keeps using the **same** KakaoTalk account on their phone and PC normally — nothing on those devices is disturbed.
3. **The "Use with main device" checkbox is CHECKED by default — leave it checked unless they want to displace their current main phone.** With it checked (the default), this handsoff device joins as a secondary alongside the existing main phone — nothing on the main phone gets logged out. **Unchecking it logs the user out of their current main device** and promotes this handsoff device to main. That's almost never what they want; flag this clearly so they make the choice deliberately.

Then wait. Resume only when the user replies that login is complete.

## Step 2 — Install Iris (NOT a normal APK install)

Iris is **not** installed as a regular app. It runs as a root-owned `app_process` directly from the APK file under `/data/local/tmp`. There is no launcher icon and `pm install` is not used.

**Use the patched fork, not upstream.** Upstream `dolidolih/Iris` v0.30 has a bug where `/ws` silently drops every inbound text message whose `attachment` column is empty (an unhandled `JSONException` aborts the broadcast). The fork at [`predict-woo/Iris-patch`](https://github.com/predict-woo/Iris-patch) fixes this. Same `app_process` invocation — just pull the APK from the fork's releases.

Resolve the latest release via `gh`:

```bash
gh release view --repo predict-woo/Iris-patch --json tagName,assets,name
```

Push the APK to `/data/local/tmp/Iris.apk`:

```
mcp__handsoff__push_file(
  source_url="https://github.com/predict-woo/Iris-patch/releases/download/<TAG>/Iris.apk",
  device_path="/data/local/tmp/Iris.apk",
  executable=False
)
```

Verify the MD5 against the published `Iris.apk.MD5` asset (`mcp__handsoff__adb_shell("md5sum /data/local/tmp/Iris.apk")`).

## Step 3 — Start Iris as root

The official `iris_control` script runs:

```
su root sh -c 'CLASSPATH=/data/local/tmp/Iris.apk app_process / party.qwer.iris.Main'
```

A naive `nohup ... &` from `adb shell` does **not** survive — the Android shell session ends and kills the process. Use `setsid` to detach properly:

```
mcp__handsoff__adb_shell("""
  su root sh -c 'setsid sh -c "CLASSPATH=/data/local/tmp/Iris.apk app_process / party.qwer.iris.Main > /data/local/tmp/iris.log 2>&1" < /dev/null > /dev/null 2>&1 &'
""")
```

Verify it's alive:

```
ps -ef | grep app_process | grep party.qwer.iris.Main
tail /data/local/tmp/iris.log
```

You should see `DBObserver started`, `Notification Poller started`, `Bot user_id is detected: <id>`, and a few `SLF4J(W): No SLF4J providers were found` warnings (harmless — slf4j just falls back to no-op). Iris does **not** log an explicit "listening on :3000" line; the HTTP server (default `botHttpPort`) binds silently. Confirm the port is actually up by hitting `/config` in Step 5 Probe A, not by grepping the log. Iris auto-creates `/data/local/tmp/config.json` on first boot.

## Step 4 — Expose Iris through the handsoff proxy

```
mcp__handsoff__expose_service(android_port=3000, path_prefix="iris", name="Iris Dashboard")
```

The proxy returns an internal URL like `http://0.0.0.0:8000/services/iris/`. Externally, handsoff is fronted by a TLS reverse proxy on standard ports — reachable as:

```
https://handsoff.gethandsoff.com/services/iris/
```

Port 8000 is **not** open publicly; the public frontend forwards `/services/*` to the internal proxy. Don't tell the user to use `:8000` from outside.

## Step 5 — Ask the user for an API key, then verify

All requests through the public URL require a bearer token. The agent does **not** have it and **cannot** generate one — the user mints it from the handsoff web console.

After Step 4 exposes the service, **stop and ask the user for an API key**, with two specifics in the message:

1. Tell them the API key is generated from the **handsoff web console** (the same console they used for KakaoTalk login). They create it there and paste the value back to you.
2. Make clear it will be used as `Authorization: Bearer <key>` against the public URL — it's a password equivalent.

Wait for the user to reply with the key. Once you have it, run two probes — one to confirm proxy/auth/Iris, one to confirm KakaoTalk is actually logged in.

**Probe A — proxy + auth + Iris liveness:**

```bash
curl -s -H "Authorization: Bearer $KEY" \
  https://handsoff.gethandsoff.com/services/iris/config
```

Expect `200` with JSON like `{"bot_name":"Iris","bot_http_port":3000,"bot_id":<N>,...}`. Anything else (401, 404, hang) — debug before continuing. **A `200` here does NOT prove KakaoTalk is logged in** — `/config` is just a file read and returns even when the user hasn't signed in.

**Probe B — KakaoTalk login state:**

Two equivalent ways:

1. Check `bot_id` from Probe A's response — `0` (or missing) means no login; any non-zero integer means Iris read a real `user_id` from KakaoTalk's DB, which only exists after login.
2. Hit `/aot`:

   ```bash
   curl -s -H "Authorization: Bearer $KEY" \
     https://handsoff.gethandsoff.com/services/iris/aot
   ```

   Expect `{"success":true,"aot":{"access_token":"...","refresh_token":"...","token_type":"bearer","d_id":"..."}}`. `success:false`, null tokens, or empty `aot` means KakaoTalk login is incomplete — send the user back to the web console to finish.

Both probes green → setup is done.

### After verification, recommend rotating the key (don't force it)

The key the user pasted into chat has now been read by the agent and may live in conversation transcripts, terminal scrollback, or shell history. After verification succeeds, **suggest** to the user:

> "Verification passed. For your actual bot/app usage I'd recommend going back to the web console, deleting this key, and generating a fresh one to use from there — that way the key you actually rely on hasn't been pasted into a chat. Totally your call though; the current key works fine."

Phrasing matters: it's a recommendation, not a requirement. If the user declines, drop it and continue. Do not nag.

Treat any key you hold like a password — don't log it, don't commit it, don't include it in summaries you write to disk.

## Step 6 (optional, ask first) — KakaoTalk setting tweak for unattended image sends

**Do NOT do this automatically.** After Step 5 succeeds, ask the user whether they want this applied — then act on their answer.

Why it might matter: Iris's image-send path fires `ACTION_SEND_MULTIPLE` to KakaoTalk. If KakaoTalk's _Image Resolution_ setting is `Original` (the default), KakaoTalk pops a confirmation modal ("may contain EXIF data such as location metadata") on every send, which blocks unattended bot use. Flipping the setting to `Standard resolution` once makes future image sends complete with no UI prompt.

How to ask the user (something like):

> "Setup is verified. Optional follow-up: KakaoTalk's default _Image Resolution_ is `Original`, which makes it pop a confirmation modal every time the bot tries to send an image. If you plan to send images via Iris, I can flip this to `Standard resolution` for you (it's purely a KakaoTalk setting change — text sends work either way). Want me to apply it?"

If the user says **yes**:

> Drive KakaoTalk → More tab → Settings (gear) → **Data and Storage** → **Image Resolution** → change `Original` to `Standard resolution`.

Then finish with the home-button rule below.

If the user says **no** (or says they only need text), skip it and move on. Do not re-prompt.

## House-keeping after every turn

1. `mcp__handsoff__system_button(button="home")` — leave KakaoTalk in the background. KakaoTalk suppresses notifications for whichever chat is open in the foreground, which silently breaks Iris's notification-based name harvesting. Pressing Home avoids this trap regardless of whether the current task touched names.
2. `mcp__handsoff__set_agent_keyboard(active=False)` — restore the on-screen keyboard for the human user.

Both are cheap and idempotent; do them unconditionally before ending the turn.

## Failure modes during setup

| Symptom                       | Likely cause                                            | Fix                                                    |
| ----------------------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| Iris process gone after start | Used `nohup ... &` from `adb shell`; session closed it. | Use the `setsid` form in Step 3.                       |
| Public URL returns 404 / hang | Service not exposed, or wrong path prefix.              | Re-run `expose_service(3000, "iris")`.                 |
| Public URL returns 401 / 403  | Missing or wrong bearer token.                          | Use `Authorization: Bearer <token>` per request.       |
| `/aot` returns null tokens    | KakaoTalk login didn't complete on the device.          | Send the user back to the web console to finish login. |
| MD5 mismatch on pushed APK    | Network truncation during `push_file`.                  | Re-push and re-check.                                  |

## Using Iris after setup

Endpoint shapes, query patterns, message-send payloads, the `/ws` event format, and other usage details are **not** in this skill. Once the verification probe passes, fetch the companion doc and follow it:

https://raw.githubusercontent.com/predict-woo/Iris-patch/refs/heads/main/SKILLS.md

That file is the source of truth for how to drive the running Iris server.

## References

- Iris repo (use this — patched fork): https://github.com/predict-woo/Iris-patch
- Releases (use this): https://github.com/predict-woo/Iris-patch/releases
- Upstream (reference only, do **not** install): https://github.com/dolidolih/Iris
