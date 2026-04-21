# Heartwood

> Grow applications ring by ring — from a vague idea to a working app, with no layer skipped.

Heartwood is an open-source, multi-layer requirements-elicitation and codegen framework for developers, vibe coders, and small teams who use tools like Claude Code, Cursor, and Antigravity to build applications. It solves a specific problem: the initial brief is always incomplete, and LLMs silently fill the gaps with assumptions that only surface as bugs three layers deep.

Instead of letting those assumptions leak, Heartwood forces them to the surface — one ring at a time.

---

## Why "Heartwood"?

Heartwood is the dense, structural core of a tree, formed from the growth rings laid down in earlier years. It carries the load. Every ring matters, and it has to be laid down in the right order.

That's what this project does. Each layer is a ring: foundations, UI, API, data, implementation. The strength of what you end up building depends on every ring being laid down properly, in order, with nothing skipped.

---

## The problem Heartwood solves

You get a one-paragraph brief. "Build a todo app where teams can share lists." You hand it to an LLM. You get a working prototype in an hour. Three days later you realize:

- There's no real auth model — the LLM invented one.
- RBAC was never discussed — the LLM picked admin/user and moved on.
- The mock never showed the empty state, error states, or permission-denied states. Now you have to retrofit them everywhere.
- The database schema and the API contract disagree in subtle ways because each was generated from a different implicit understanding of the requirements.

The problem isn't the LLM. The problem is that nobody forced the hidden requirements into the conversation. Heartwood does that.

---

## The framework — five rings

```
Ring 0 — Foundations    (who, what, where, how big, how sensitive)
Ring 1 — UI Mock        (every screen, every state, in HTML)
Ring 2 — API Contract   (business logic, endpoints, payloads)
Ring 3 — Data Model     (schema, relationships, constraints)
Ring 4 — Implementation (real UI, real backend, real database)
```

Each ring is a conversational session with a specialized agent that walks an internal checklist, asks the hidden questions, and produces a reviewable artifact. The artifact from one ring is the locked input to the next.

**Ring 0 — Foundations.** Cross-cutting decisions: identity, tenancy, roles, data sensitivity, compliance, scale, accessibility, platform, integrations, business model. Output: `foundations.md`.

**Ring 1 — UI Mock.** Screen inventory, per-screen specs including every unhappy state, then an HTML mock that renders them all. Output: `ui-spec.md` + a working HTML mock you can click through.

**Ring 2 — API Contract.** Stack choices, endpoint design, request/response payloads, a Swagger-style visual contract. Output: `api-spec.md` + a clickable but non-operational API viewer.

**Ring 3 — Data Model.** Schema design fitted to the mock and API, validated against best practices. Output: `data-model.md` + migration scaffolding.

**Ring 4 — Implementation.** Real UI replicated from the mock in a stack of the user's choice (React, Next, Vite, etc.), wired to the API and database. Output: a real, working codebase.

**Rings 0 and 1 are the initial release.** Rings 2, 3, and 4 are on the roadmap. See [ROADMAP.md](./ROADMAP.md).

---

## How each ring works

Every ring follows the same architecture, which is the whole point — once you've built one, the rest are re-skins.

1. **Checklist as coverage map.** The agent has a large internal checklist (40+ items for Ring 0, 100+ per-screen for Ring 1). The checklist is for tracking coverage, not for scripting questions.
2. **Compression over interrogation.** The agent infers aggressively from the brief, proposes defaults, batches related questions, and only hard-asks on load-bearing items. A good session is 10–20 explicit questions, not 80.
3. **Three states per item.** Every checklist item ends up as a **decision** (explicit user answer), an **assumption** (agent-filled default), or **skipped** (N/A based on a gating answer). Nothing is left floating.
4. **Tool-calls for state updates.** The agent uses `record_decision`, `record_assumption`, and `mark_skipped` as real tool calls — not text parsing. This is what keeps long sessions coherent.
5. **Assumptions review at handoff.** When the ring finishes, the user sees every assumption in a dedicated review screen (not a chat turn) and accepts or overrides each one. This is the single most important UX detail — it's what prevents the user from rubber-stamping.
6. **Backward edges are allowed.** Users remember things mid-session. The agent updates state in place and flags downstream items that depended on the changed answer.

The full architecture, checklists, and ready-to-use system prompts for Rings 0 and 1 are in [docs/architecture.md](./docs/architecture.md).

---

## Project structure

```
heartwood/
├── README.md
├── ROADMAP.md
├── CONTRIBUTING.md
├── docs/
│   ├── architecture.md            # Ring 0 + Ring 1 architecture + prompts
│   ├── checklists/
│   │   ├── ring-0-foundations.md
│   │   └── ring-1-ui-spec.md
│   └── prompts/
│       ├── ring-0-system-prompt.md
│       └── ring-1-system-prompt.md
├── apps/
│   └── web/                       # Next.js chatbot UI (example)
├── packages/
│   ├── agent-core/                # state model, tool definitions, session engine
│   ├── ring-0/                    # foundations agent
│   ├── ring-1/                    # UI spec agent + mock generator
│   └── shared/                    # types, utils
└── examples/
    └── todo-app/                  # sample session transcripts + artifacts
```

(Monorepo layout is a suggestion. Fork it however fits your stack.)

---

## Getting started

> **Status:** early / pre-alpha. The architecture doc and prompts are stable. The reference web app is being built. Expect the API to change.

### Prerequisites

- Node.js 20+
- An API key for an LLM provider that supports streaming + native tool-calling (Anthropic Claude, OpenAI GPT-4+, or compatible)
- `pnpm` (or `npm` / `yarn`)

### Install

```bash
git clone https://github.com/YOUR-ORG/heartwood.git
cd heartwood
pnpm install
cp .env.example .env
# add your LLM API key to .env
pnpm dev
```

Open `http://localhost:3000` and start a new session.

### Your first session

1. Paste your initial brief into the new-session screen. One paragraph is fine. One sentence is fine too.
2. Heartwood starts Ring 0. Answer the questions; push back on defaults you don't like.
3. When Ring 0 finishes, review the assumptions. Accept, override, or send the agent back for a follow-up.
4. Once `foundations.md` is locked, Ring 1 begins. Same loop — answer, review, confirm.
5. At the end of Ring 1 you have `ui-spec.md` and a working HTML mock you can click through.
6. Rings 2–4 are coming. For now, hand the artifacts to Claude Code or Cursor and build from there.

---

## Use with your existing codegen tool

Heartwood is designed to feed into, not replace, tools like Claude Code, Cursor, Antigravity, Windsurf, Aider, and similar. The artifacts (`foundations.md`, `ui-spec.md`, the HTML mock) are plain files you can hand to any of those tools as context. The whole point is to give codegen tools the requirements they were always missing.

---

## Design principles

The project is opinionated. These are the opinions:

- **Every hidden requirement should be asked about, once, in the right layer.** Auth belongs in Ring 0, not Ring 4.
- **Unhappy paths are first-class.** Every UI spec must cover empty, loading, error, permission-denied, and over-limit states. Mocks that only render the happy path are lying.
- **Assumptions are visible, not silent.** If the agent filled in a default, the user sees it before the ring closes.
- **Review is explicit, not implicit.** Per-row accept/override beats "does this look right?" every time.
- **Artifacts are plain markdown + HTML.** No proprietary format. You can read them, diff them, version them in git, and hand them to any tool.
- **Rings are contracts, but not walls.** Backward edges are allowed when a later ring reveals that an earlier decision was wrong.

---

## Roadmap

**v0.1 — Ring 0 + Ring 1 (current focus).** Foundations elicitation, UI spec elicitation, HTML mock generation, assumptions review UI, session persistence.

**v0.2 — Ring 2.** API contract agent, Swagger-style visual contract generator.

**v0.3 — Ring 3.** Data model agent with schema validation.

**v0.4 — Ring 4.** Implementation layer: replicate the mock in a real stack (React / Next / Vite) wired to the API and database.

**v1.0.** All five rings end-to-end, with persistent project state across rings and the ability to reopen any ring without restarting.

Details in [ROADMAP.md](./ROADMAP.md).

---

## Contributing

Heartwood is open source under the MIT license. Contributions are welcome — especially in these areas:

- **Checklists.** Real-world briefs that surface items the current checklists miss. These are gold.
- **Prompt tuning.** The Ring 0 and Ring 1 system prompts are a starting point, not a finished product. If you run sessions and find the agent over-asking, under-asking, or missing categories, open a PR.
- **Eval suite.** We need a small set of real briefs with expected outcomes to measure prompt changes. Contributions to `examples/` are very welcome.
- **Ring 2–4 scaffolding.** Apply the same architecture to API, data, and implementation layers.
- **Alternative model providers.** Heartwood should work with any model that supports streaming + tool-calling. Adapters for new providers are welcome.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the contribution workflow, code style, and PR checklist.

### What NOT to contribute

- Pre-built templates for specific app types ("a SaaS dashboard template"). Heartwood is about elicitation, not templates. Templates encode assumptions — which is exactly what we're trying to make visible, not bake in.
- New rings. The five-ring structure is intentional. If you think a ring is missing, open an issue for discussion first.

---

## FAQ

**Is this a replacement for Claude Code / Cursor / Antigravity?**
No. It's a pre-step. Heartwood produces the artifacts those tools should have been getting all along.

**Why not just use Figma for the mock?**
Figma is great for designers. Heartwood's mock is in HTML because it's faster for LLMs to generate, it forces concreteness (real interactive states, not static frames), and it can be handed directly to the next ring as input.

**Why five rings instead of three?**
The original design was three. Splitting foundations (Ring 0) out of UI (Ring 1) is what makes cross-cutting concerns — auth, tenancy, roles — stop leaking. Splitting implementation (Ring 4) out of data (Ring 3) is what makes the real UI build cleanly from the spec.

**Can I skip a ring?**
You can, and it will hurt you. The rings exist because each one surfaces a category of decision the others don't. Skipping Ring 0 is how you end up retrofitting auth. Skipping Ring 1's unhappy-state requirements is how you end up with a mock that lies.

**What if my app is really simple and doesn't need all this?**
Heartwood is overkill for a single-user weekend project. It's aimed at apps complex enough that hidden requirements bite — which turns out to be most apps the moment they have more than one user.

**Does it work with local models?**
In principle, yes — any model with streaming + tool-calling will work. Quality of elicitation scales with model capability, so very small local models won't perform as well on the compression-and-inference behavior the agents rely on.

---

## Credits

Heartwood exists because too many vibe-coded projects collapse under the weight of assumptions nobody wrote down. If that's ever happened to you, this project is for you. PRs welcome.
