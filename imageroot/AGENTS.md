# imageroot Guidelines

- This subtree is the installed NS8 module payload. Keep it aligned to the checked-in per-agent Hermes dashboard implementation.
- There is no OpenViking runtime, no hidden backend runtime, no shared target, and no `AGENTS_LIST` registry anymore.
- The runtime contract is now: one configured agent equals one metadata file, one generated Hermes env file, one generated Hermes secrets env file, one Podman-managed Hermes home volume, one `hermes@<id>.service`, one `hermes-dashboard@<id>.service`, one `hermes-pod-<id>` pod, one rootless `hermes-<id>` gateway container, and one rootless `hermes-dashboard-<id>` dashboard container.
- Keep restart ownership in systemd: `hermes@<id>.service` and `hermes-dashboard@<id>.service` handle restart policy, and the Podman pod/container launches should not add container-level `--restart` policies.
- Preserve named-volume ownership semantics: keep `--userns=keep-id`, keep one Hermes home volume per agent, and do not regress the runtime into shared or root-owned agent homes across restarts.
- Preserve the NS8 action model already used here: numbered executable action steps, JSON stdin for actions, JSON stdout for reads, and schema files beside the actions.
- `environment` is shared NS8 state. Merge only managed keys and preserve core-managed values such as `HERMES_AGENT_HERMES_IMAGE`.
- Keep module-wide secrets in `secrets.env`. Keep generated per-agent Hermes secrets in `agent_<id>_secrets.env`.
- Keep shared smarthost discovery in `discover-smarthost`, keep per-agent env and secrets generation in `sync-agent-runtime`, and keep strict first-seed-only home seeding in `configure-module/75seed-agent-home`. That seed step must use the generated public `agent_<id>.env`, mount checked-in templates read-only, and preserve existing `SOUL.md` plus `.env` content in the volume.
- Shared dashboard publishing is controlled by `base_virtualhost` plus shared `lets_encrypt`. If you change route payload fields or cleanup behavior, update Traefik-facing actions, tests, UI, and docs together.
- Do not inject the shared `environment` file directly into containers. Containers should consume the generated per-agent env files only.