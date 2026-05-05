# Contributing a reference to the `handsoff` skill

The `handsoff` skill uses **progressive disclosure** — `SKILL.md` is small and always-loaded; deeper workflows live as plain `.md` files under `references/` and load only when `SKILL.md` routes Claude to them.

## When to add a reference vs. a new skill

Add a **reference** under `references/` if:

- It's a workflow performed *on top of* a HandsOff device (installing an app, configuring a service, exposing a port).
- Loading it always-on would be wasteful — only a subset of users will ever need it.

Open a **new top-level skill** (sibling folder under `skills/`) instead if:

- It stands alone — doesn't assume a HandsOff device or its MCP tools.
- It needs its own `name` / `description` to be discoverable by Claude independently of `handsoff`.

## How to add a reference

1. Create `skills/handsoff/references/<your-name>.md`.
   - **No YAML frontmatter.** Frontmatter would make `npx skills` treat the file as a separate skill.
   - Lead with a single H1 followed by a `>` blockquote that states scope + the stop/hand-off condition.
2. Edit [`SKILL.md`](SKILL.md) → add a row to the **Bundled references — read on demand** table. The "Read when" cell is the routing signal — make it specific.
3. Verify locally that the skill still installs as one unit:
   ```bash
   npx skills add . --list
   ```
   You should see **one** skill named `handsoff`. If your new file shows up as a separate skill, you have stray frontmatter.
4. Open a PR using the **Add a skill reference** template:
   - From the GitHub PR creation page, pick it from the template dropdown, OR
   - Append `?template=add-skill-reference.md` to your PR URL.

## Style for reference docs

- Write for an agent reader, not a human reader. Be directive ("Run X", "Stop and ask the user Y").
- State explicit STOP points where human input is required (logins, API keys, destructive choices).
- Include a failure-mode table for the common breakages.
- End with a "what's next / out of scope" pointer so the agent knows when to hand off.
