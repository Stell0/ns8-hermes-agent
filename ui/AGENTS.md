# ui Guidelines

- This subtree is the embedded NS8 admin UI. Preserve the current stack unless frontend migration is the task: Vue 2, Vue CLI, Vue Router, Vuex, Carbon, and `@nethserver/ns8-ui-lib`.
- Keep the embedded-shell pattern: `App.vue` reads context from `window.parent`, task execution goes through the NS8 UI task helpers, and routing and state live under `src/router/` and `src/store/`.
- Use the existing Yarn-based toolchain and build assumptions. Keep compatibility with `yarn.lock`, `vue.config.js`, and the legacy `NODE_OPTIONS=--openssl-legacy-provider` requirement used locally and in CI.
- The current UI is a small multi-view scaffold (`status`, `settings`, `about`), not the one-page Hermes manager described in stale docs. Extend or clean up the existing scaffold directly instead of introducing a second frontend architecture.
- When backend action names, payloads, metadata, or user-facing text change, update the corresponding view code, `public/metadata.json`, and translation files together.
- The `settings` view is now agent-focused. Keep the table, row-action menu, modal creation flow, and `configure-module`/`get-configuration` wiring aligned when adding fields.
- Modal save and delete are immediate `configure-module` operations; the page save button re-submits the current in-memory agent list.
- Agent `status` is now a real persisted desired state and `get-configuration` returns the actual runtime status from systemd.
- The backend also persists hidden tenant fields `account`, `user`, and `agent_id`. The current UI must preserve and round-trip those fields without exposing them in the create modal yet.