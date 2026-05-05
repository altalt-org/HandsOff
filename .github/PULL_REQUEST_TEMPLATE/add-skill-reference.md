---
name: Add a skill reference
about: Contribute a new on-demand reference doc under skills/handsoff/references/
title: 'skill: add <name> reference'
labels: skill
---

<!--
This template is for adding a new reference doc under
`skills/handsoff/references/`. References are loaded *only when needed* by
the top-level `handsoff` SKILL.md, so they should be self-contained
walkthroughs of one specific workflow.

Pick this template by opening your PR with the URL suffix
?template=add-skill-reference.md, or via the GitHub "Create pull request"
template dropdown.
-->

## What this reference covers

<!-- One sentence describing the workflow this doc walks an agent through. -->

## Scope boundary

<!-- What's out of scope? Where does the doc stop and hand off? Be explicit
about the "done" condition so future agents don't keep going. -->

## Why this is a reference, not a top-level skill

<!-- Quick justification — usually: specialized workflow, only relevant for a
subset of users, or builds on top of the core handsoff skill. If it's
genuinely independent of handsoff, propose a separate top-level skill
folder instead. -->

## Checklist

- [ ] Created `skills/handsoff/references/<name>.md`
- [ ] **No YAML frontmatter** in the reference file — only `SKILL.md` files get frontmatter, otherwise the `npx skills` CLI will install it as a separate top-level skill
- [ ] First line under the H1 is a `>` blockquote stating scope and the stop/hand-off condition
- [ ] Added a row to the "Bundled references — read on demand" table in [`skills/handsoff/SKILL.md`](../../skills/handsoff/SKILL.md) with a specific "Read when …" trigger
- [ ] Trigger phrasing is narrow enough that Claude won't mis-route to it on unrelated handsoff tasks
- [ ] Verified locally that the skill still installs as one unit:
      `npx skills add . --list` (run from repo root) should show **only** the `handsoff` skill — no extras
- [ ] No secrets, bearer tokens, or device serials committed in the reference

## Testing notes

<!-- How did you exercise the new reference? E.g. "Ran the full flow against
a fresh redroid container; both verification probes returned 200." -->
