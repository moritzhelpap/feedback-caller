# Memory Vault Project — Context & Plan

## What We're Building

A personal knowledge/memory system for a BCG management consultant to reduce cognitive load and speed up work product creation.

**Core idea:** Automatically capture inputs from all daily work platforms into a central, searchable vault. Use Claude AI to process and structure that content so it can be queried when drafting meeting agendas, status updates, emails, or presentations.

---

## The Person

- Management consultant at BCG
- Daily inputs: Outlook email, Microsoft Teams (meetings + chats), Slack, Claude AI chats, PowerPoint slides, Excel files
- Goal: stop re-explaining context to Claude every time; have a "second brain" that Claude can read from to help create content
- Non-technical — solution must be low-maintenance and mostly automated
- Uses M365 / Microsoft ecosystem (BCG standard)

---

## Tool Choice: Obsidian

**Why Obsidian:**
- Free, works on Windows, Mac, iOS, Android
- Notes are plain Markdown files (future-proof, no vendor lock-in)
- Powerful linking between notes (builds a connected knowledge graph over time)
- Plugin ecosystem — including AI plugins that connect to Claude
- You own and control all your data

**Rejected alternatives considered:**
- Custom code repo — too much maintenance for a non-technical user
- Claude Projects — 80% solution but limited automation
- Notion — good but harder to plug into automation flows

---

## Architecture

### Storage & Sync
- Vault folder lives on **BCG OneDrive** (M365 — usually IT-approved)
- OneDrive syncs automatically → same vault on phone and computer
- *Check with BCG IT/InfoSec before routing any client-related content through flows*

### Folder Structure
```
vault/
├── Inbox/          ← raw captures land here (automated)
├── Clients/        ← one note per client
├── Projects/       ← one note per engagement
├── Meetings/       ← dated notes, one per meeting
├── People/         ← stakeholders, with linked context
├── Frameworks/     ← consulting toolkit (2x2s, MECE, etc.)
├── Daily/          ← daily journal / brain dump
└── Templates/      ← reusable note templates
```

### Two-Stage Capture System

```
Stage 1: Raw Capture
[Outlook] ──────────────────────────────┐
[Teams messages] ───────────────────────┤
[Teams meeting transcripts] ────────────┤──→ [Inbox/ folder]
[Calendar events] ──────────────────────┤
[Claude chats] ─────────────────────────┘

Stage 2: Daily Claude Review
[Inbox/] → Claude reads raw content → summarises, tags, links → files into proper folders
```

Without Stage 2, you just get a pile of raw text. The Claude review turns capture into usable memory.

---

## Automation Plan by Source

| Source | Method | Effort | Feasibility |
|---|---|---|---|
| Sent emails (Outlook) | Power Automate flow | ~30 min setup | High |
| Teams messages / mentions | Power Automate flow | ~30 min setup | High |
| Teams meeting transcripts | Native Teams transcription → OneDrive | Built-in setting | High |
| Calendar events | Power Automate: new meeting → note template | ~20 min setup | High |
| Claude chats | Obsidian Web Clipper browser extension (1-click) | 5 min install | Medium |
| Slack | Zapier — check if BCG-approved first | Varies | Medium |
| Slides / Excel | Link to OneDrive file + write summary note manually | Manual | Low (text doesn't translate) |

**Primary automation tool: Microsoft Power Automate** (included in M365 license)

---

## AI Integration in Obsidian

**Recommended plugin:** "Smart Connections" or "Copilot" (community plugins)
- Add your Anthropic API key
- Claude can read across the entire vault
- Ask: "Draft an agenda for my meeting with [Client X]" → Claude reads relevant notes and drafts it

---

## Implementation Order

1. **Create new GitHub repo** (name suggestion: `memory-vault` or `second-brain` — set to Private)
2. **Set up vault** — folder structure + note templates on OneDrive
3. **Install Obsidian** on phone and computer, point at OneDrive vault
4. **First Power Automate flow** — sent emails → Inbox/ (proves the pattern)
5. **Add more flows** one at a time (Teams, calendar)
6. **Install Obsidian Web Clipper** for Claude chat capture
7. **Build daily Claude review prompt** to process Inbox/ into structured notes

---

## Important BCG Caveats

- Keep vault on **BCG OneDrive**, not personal cloud
- **Check with BCG IT/InfoSec** before routing client emails or meeting content through Power Automate flows — DLP policies apply
- Some Power Automate flows may require IT admin approval in your tenant
- Client data should follow BCG data classification rules

---

## Next Steps (for new Claude Code session)

When starting a fresh session in the new repo, paste this file as context and ask Claude to:

1. Create the starter vault folder structure with template Markdown files
2. Write step-by-step Power Automate setup guides (with screenshots instructions) for each flow
3. Write the daily Claude review prompt for processing the Inbox folder
4. Write an Obsidian setup guide for a non-technical user

---

*Generated from conversation on 2026-05-23. Original session: feedback-caller repo.*
