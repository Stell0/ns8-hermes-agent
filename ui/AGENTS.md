# ui Guidelines

- This subtree is the embedded NS8 admin UI. Preserve the current stack unless the task is a frontend migration: Vue 2, Vue CLI, Vue Router, Vuex, Carbon, and `@nethserver/ns8-ui-lib`.
- The settings page is now agent-focused plus shared dashboard publishing. Keep it focused on one shared `base_virtualhost` field plus listing agents, creating and editing agents, deleting agents, and toggling start or stop state.
- The backend payload for `configure-module` is `{ "base_virtualhost": "", "agents": [...] }`. There are no hidden fields, shared gateway flags, or OpenViking settings to preserve.
- `get-configuration` returns `{ "base_virtualhost": "", "agents": [...] }`, where `status` is the desired persisted state and `runtime_status` is the current systemd runtime state. Round-trip `base_virtualhost` plus the desired `status` back to `configure-module`.
- When user-facing text changes, update `public/metadata.json` and the translation files together.