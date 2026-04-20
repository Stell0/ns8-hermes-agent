# Repository Guidelines

- Keep changes within the current scaffold unless the task explicitly expands scope: NS8 module runtime under `imageroot/`, embedded admin UI under `ui/`, the wrapper images under `containers/`, and basic CI and test scaffolding.
- Prefer the smallest coherent change and keep related docs, tests, and build files in sync. Do as much as is needed, as little as possible.
- Put long reference material in normal docs, not in AGENTS. Use `README.md` for current status and operator-facing behavior, `STRUCTURE.md` for file maps, and `NS8-MODULE.md` for NS8 lifecycle details.
- Only `imageroot/` and `ui/` currently justify local AGENTS files. Do not add more unless a subtree gains genuinely different conventions.
- When asked to commit, use the `commit` skill
- before non-trivial code changes, invoke the `researcher` agent to search the relevant `*_RESOURCE_MAP.md` files, browse the authoritative docs, and gather similar code patterns or prior art.
- after code changes that affect runtime behavior, auth, secrets, input handling, networking, containers, or external API calls, invoke the `security-expert` agent to inspect attack surface and either apply minimal mitigations or report the residual risk clearly.
- after code changes, invoke the `tester` agent to add or update focused unit tests and Robot Framework integration coverage as appropriate, then run the relevant test commands.
- After code changes that may affect documentation, invoke the `docs-maintainer` custom agent to review checked-in Markdown files. Keep `README.md` current for humans, and keep `AGENTS.md` files plus `STRUCTURE.md` current for agents and implementation accuracy.
- after implementation, refactor, tester-driven follow-up edits, invoke the `code-reviewer` agent to check that the final patch stays minimal, readable, clean, and easy to maintain.