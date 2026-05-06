# HandsOff

HandsOff gives your AI agent its own Android phone.

You spin up a remote Android device on AWS, connect it to your laptop over Tailscale, and your agent (Claude Code, Cursor, etc.) gets a set of MCP tools to tap, swipe, type, install apps, take screenshots — anything you'd do on a real phone, the agent can do, while you watch live in your browser.

## What you get

- A `t4g.medium` EC2 instance running [ReDroid](https://github.com/remote-android/redroid-doc) (containerized Android) in your own AWS account
- A live screen mirror in your browser via [scrcpy-web](https://github.com/NetrisTV/ws-scrcpy)
- Private networking through [Tailscale](https://tailscale.com/) — no public ports beyond SSH
- An MCP server your agent connects to for device control

## Installation

### For Humans

You will need:

- An **AWS account** with the AWS CLI installed and authenticated (`aws configure` or `aws sso login`)
- A **Tailscale account** with the Tailscale client installed and logged in on your laptop
- An **agent harness** that speaks MCP — Claude Code, Cursor, AmpCode, etc.

First, install the HandsOff skill so your agent picks up the device-control knowledge it'll need after setup:

```bash
npx skills add altalt-org/handsoff
```

Then copy-paste this prompt into your agent:

```
Install and configure HandsOff for me by following the instructions here:
https://raw.githubusercontent.com/altalt-org/HandsOff/refs/heads/main/docs/installation.md
```

The agent will check your prerequisites, provision the EC2 instance, install dependencies, deploy HandsOff, set up Tailscale, and wire MCP into your harness.

You can read the [Installation Guide](docs/installation.md) yourself, but seriously — let the agent do it. There are a lot of steps and humans fat-finger AWS commands.

### For LLM Agents

Fetch the installation guide and follow it:

```bash
curl -fsSL https://raw.githubusercontent.com/altalt-org/HandsOff/refs/heads/main/docs/installation.md
```

The guide is self-contained. Read it through before starting, then execute step by step.

## After installation

Start a new agent session so MCP picks up the new server. Your agent will then have tools like `mcp__handsoff__screenshot`, `mcp__handsoff__open_app`, `mcp__handsoff__type_text`, `mcp__handsoff__app_install`, and more. Ask it to do something — install a Korean food-delivery app and order dinner, log into KakaoTalk, scrape an app that has no public API, whatever.

You can watch the device live at `http://<tailscale-ip>:8080` in your browser. Pick **H264 Converter** in the decoder dropdown for best performance.

## Teardown

Ask your agent to tear it down when you're done, then remove the machine from your Tailscale admin console.

## Contributing a new skill

If you build a workflow on top of HandsOff that other users would benefit from — installing a specific app, exposing a service, configuring a regional setup — contribute it as a **reference** under the bundled `handsoff` skill.

1. Read [`skills/handsoff/CONTRIBUTING.md`](skills/handsoff/CONTRIBUTING.md) to decide whether your workflow belongs as a reference under the existing skill, or as a brand-new top-level skill.
2. Add your `.md` file under `skills/handsoff/references/` (no YAML frontmatter — that's reserved for `SKILL.md`) and register it in the routing table in [`skills/handsoff/SKILL.md`](skills/handsoff/SKILL.md).
3. Verify locally that the skill still installs as one unit: `npx skills add . --list` from the repo root should show only the `handsoff` skill.
4. Open the PR using the **Add a skill reference** template — pick it from the GitHub template dropdown, or append `?template=add-skill-reference.md` to the PR URL. The template's checklist catches the common mistakes (stray frontmatter, vague routing triggers, leaked secrets).

## Links

- [Installation Guide](docs/installation.md)
- [GitHub](https://github.com/altalt-org/HandsOff)
- [scrcpy-web (live screen)](https://github.com/NetrisTV/ws-scrcpy)
- [ReDroid](https://github.com/remote-android/redroid-doc)
