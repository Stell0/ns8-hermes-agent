# Hermes Agent Resource Map

*Last verified: 2026-04-06.* Hermes Agent is the open-source, self-improving agent by Nous Research, with official docs at `hermes-agent.nousresearch.com/docs`, the main codebase in `NousResearch/hermes-agent`, and the current latest release listed as `v0.7.0` dated 2026-04-03. ([hermes-agent.nousresearch.com][1])

## 1) Canonical entry points

### Official website

* [Hermes Agent website](https://hermes-agent.nousresearch.com/) — best first stop for high-level overview, installer, positioning, and main navigation. ([hermes-agent.nousresearch.com][1])

### Official documentation

* [Docs home](https://hermes-agent.nousresearch.com/docs/) — canonical documentation hub.
* [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation/)
* [Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/)
* [Learning Path](https://hermes-agent.nousresearch.com/docs/getting-started/learning-path/) — useful to route the agent to the right docs path fast. ([hermes-agent.nousresearch.com][2])

### Official source repository

* [Main repository: NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — source of truth for code, issues, PRs, releases, and implementation details. ([GitHub][3])

### Official release feed

* [GitHub Releases](https://github.com/NousResearch/hermes-agent/releases) — primary source for “what changed recently” and version-by-version trend tracking. Latest visible release is `v0.7.0` on 2026-04-03. ([GitHub][4])

### Official GitHub org

* [Nous Research on GitHub](https://github.com/NousResearch) — useful to discover adjacent official repos related to Hermes Agent. ([GitHub][5])

## 2) Official/community channels worth following

### Community / discussion

* [Discord](https://discord.gg) — linked from the official docs navigation.
* [GitHub Discussions](https://github.com/NousResearch/hermes-agent/discussions) — useful for community Q&A and emerging usage patterns. ([hermes-agent.nousresearch.com][2])

## 3) Official repositories to track

### Core

* [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — main product repo. This is the repo to inspect for setup, gateway internals, tools, container behavior, configuration, skills, and runtime architecture. ([GitHub][3])

### Adjacent official repos

* [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) — official side project focused on evolutionary self-improvement for Hermes Agent. Useful when the question is about self-optimization/evolutionary loops rather than the main runtime. ([GitHub][8])
* [NousResearch/hermes-paperclip-adapter](https://github.com/NousResearch/hermes-paperclip-adapter) — official adapter repo for running Hermes Agent as a managed employee inside Paperclip. Useful for integration questions. ([GitHub][9])

## 4) Documentation map by topic

### Getting started / first setup

Use these first:

* [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation/)
* [Quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/)
* [Learning Path](https://hermes-agent.nousresearch.com/docs/getting-started/learning-path/) ([hermes-agent.nousresearch.com][10])

### Configuration / models / providers

Use these when the question is about config files, environment variables, providers, fallback routing, or endpoint wiring:

* [Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/)
* [AI Providers](https://hermes-agent.nousresearch.com/docs/integrations/providers/)
* [Provider Routing](https://hermes-agent.nousresearch.com/docs/user-guide/features/provider-routing/) ([hermes-agent.nousresearch.com][11])

### Messaging gateway / bots / platform adapters

Use these when the question is about Telegram, Discord, Slack, WhatsApp, Signal, Mattermost, Matrix, email, SMS, or gateway runtime:

* [Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
* [Email adapter](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/email)
* [Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard/) — relevant when the user asks for a browser-based admin UI.
* Platform-specific pages under the messaging section. The docs list Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Home Assistant, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, and Webhooks. ([hermes-agent.nousresearch.com][12])

### Docker / containerized deployment

Use these when the question is about standalone container mode, volumes, persistence, or Docker-based operation:

* [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)
* [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile) ([hermes-agent.nousresearch.com][13])

### Architecture / internals / codebase analysis

Use these when the question is “how does Hermes work internally?” or when the task is source-code archaeology:

* [Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/)
* [Main repo](https://github.com/NousResearch/hermes-agent)
* [AGENTS.md](https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md) — especially useful for repo-specific implementation conventions and profile/HERMES_HOME behavior. ([hermes-agent.nousresearch.com][14])

### Tools / skills / MCP / memory

Use these when the question is about extending Hermes or understanding what capabilities it already has:

* [Tools & Toolsets](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/)
* [Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)
* [Skills docs / hub entry](https://hermes-agent.nousresearch.com/docs/skills/)
* [MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/)
* [Use MCP with Hermes](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes)
* [Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
* [Memory Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/)
* [Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files/)
* [Personality / SOUL.md](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/) ([hermes-agent.nousresearch.com][15])

### Sessions / CLI / troubleshooting

Use these for operational questions:

* [CLI Interface](https://hermes-agent.nousresearch.com/docs/user-guide/cli/)
* [Sessions](https://hermes-agent.nousresearch.com/docs/user-guide/sessions/)
* [FAQ & Troubleshooting](https://hermes-agent.nousresearch.com/docs/reference/faq/)
* [Tips & Best Practices](https://hermes-agent.nousresearch.com/docs/guides/tips/) ([hermes-agent.nousresearch.com][16])

## 5) Code paths the agent should inspect for technical questions

### For “How do I configure Hermes gateway as a standalone container?”

Start here:

1. [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/) — shows `docker run` examples for first-run interactive setup and persistent `gateway run` mode.
2. [Messaging Gateway docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) — explains the gateway concept and setup flow.
3. [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/) — explains `config.yaml`, `.env`, and general config layout.
4. [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile) — for exact image behavior. ([hermes-agent.nousresearch.com][13])

### For “Analyze Hermes Agent Dockerfile and identify what folder should be mounted as volumes”

Inspect:

* [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile) — sets `HERMES_HOME=/opt/data` and declares `VOLUME [ "/opt/data" ]`.
* [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/) — states `/opt/data` is the single source of truth and should be backed by the host’s `~/.hermes/`.
* [AGENTS.md](https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md) — explains profile-safe use of `HERMES_HOME`. ([GitHub][17])

### For “What exactly lives in the mounted data directory?”

Use:

* [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/) — explicitly lists `.env`, `config.yaml`, `SOUL.md`, `sessions/`, `memories/`, `skills/`, `cron/`, `hooks/`, `logs/`, `skins/`.
* [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/) — adds `auth.json` and clarifies config precedence and file roles. ([hermes-agent.nousresearch.com][13])

### For gateway runtime internals

Inspect:

* [gateway/run.py](https://github.com/NousResearch/hermes-agent/blob/main/gateway/run.py) — gateway entry point.
* `gateway/platforms/*` in the main repo — platform-specific adapters.
* [Gateway docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
* [Architecture docs](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/) ([GitHub][18])

### For concrete config examples

Inspect:

* [cli-config.yaml.example](https://github.com/NousResearch/hermes-agent/blob/main/cli-config.yaml.example)
* [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/) ([GitHub][19])

## 6) Fast routing table for an answering agent

### Query: “what are the latest trends about Hermes Agent?”

Check in this order:

1. [GitHub Releases](https://github.com/NousResearch/hermes-agent/releases)
2. [GitHub Issues](https://github.com/NousResearch/hermes-agent/issues)
3. [GitHub Pull Requests](https://github.com/NousResearch/hermes-agent/pulls)
4. [@NousResearch on X](https://x.com/NousResearch)
5. [@Teknium on X](https://x.com/Teknium) ([GitHub][4])

### Query: “what’s the latest trend about agentic engineering?”

Use Hermes-adjacent sources first:

1. [Hermes GitHub Releases](https://github.com/NousResearch/hermes-agent/releases) — product direction.
2. [Hermes Issues/PRs](https://github.com/NousResearch/hermes-agent/issues) — implementation pain points and active roadmap signals.
3. [@Teknium on X](https://x.com/Teknium) — best high-signal stream for practical agent engineering discussions tied to Hermes.
4. [@NousResearch on X](https://x.com/NousResearch) — broader product/research positioning. ([GitHub][4])

### Query: “What’s happening in AI automation?”

Use:

1. [@NousResearch on X](https://x.com/NousResearch)
2. [@Teknium on X](https://x.com/Teknium)
3. [Hermes releases](https://github.com/NousResearch/hermes-agent/releases)
4. [Adjacent official repos](https://github.com/NousResearch) such as self-evolution and adapters. ([X (formerly Twitter)][6])

### Query: “How do I configure Hermes gateway as a standalone container?”

Use:

1. [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)
2. [Messaging Gateway docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
3. [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/)
4. [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile) ([hermes-agent.nousresearch.com][13])

### Query: “Analyze Hermes Agent Dockerfile and identify what folder should be mounted as volumes”

Use:

1. [Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile)
2. [Docker docs](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)
3. [AGENTS.md](https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md) ([GitHub][17])

## 7) Minimal operational facts an agent should know

* Hermes Agent has two main entry modes: terminal UI (`hermes`) and messaging gateway (`hermes gateway run` / gateway mode). ([GitHub][3])
* The messaging gateway is a single background process that connects to configured platforms, manages sessions, and runs cron jobs. ([hermes-agent.nousresearch.com][12])
* In Docker mode, `/opt/data` is the persistent state directory, and the docs map it to the host `~/.hermes/`. ([hermes-agent.nousresearch.com][13])
* Hermes configuration is split primarily between `config.yaml` for non-secret settings and `.env` for secrets. ([hermes-agent.nousresearch.com][20])
* Hermes supports profiles via `HERMES_HOME`, and code/docs explicitly warn against hardcoding `~/.hermes` paths. ([GitHub][21])
* The docs currently present Hermes as supporting a broad platform set including Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, and others. ([hermes-agent.nousresearch.com][12])

## 8) Suggested default source priority for an answering agent

1. Official docs page for the specific feature.
2. Main repo source file for exact implementation details.
3. GitHub Releases for recent changes.
4. GitHub Issues/PRs for edge cases, regressions, and roadmap signals.
5. `@NousResearch` and `@Teknium` on X for recent announcements, release commentary, and trend signals. ([hermes-agent.nousresearch.com][2])

## 9) Copy-paste source list

* [https://hermes-agent.nousresearch.com/](https://hermes-agent.nousresearch.com/)
* [https://hermes-agent.nousresearch.com/docs/](https://hermes-agent.nousresearch.com/docs/)
* [https://hermes-agent.nousresearch.com/docs/getting-started/installation/](https://hermes-agent.nousresearch.com/docs/getting-started/installation/)
* [https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart/)
* [https://hermes-agent.nousresearch.com/docs/getting-started/learning-path/](https://hermes-agent.nousresearch.com/docs/getting-started/learning-path/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/configuration/](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/)
* [https://hermes-agent.nousresearch.com/docs/integrations/providers/](https://hermes-agent.nousresearch.com/docs/integrations/providers/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/messaging/](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/docker/](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)
* [https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)
* [https://hermes-agent.nousresearch.com/docs/skills/](https://hermes-agent.nousresearch.com/docs/skills/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/)
* [https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes](https://hermes-agent.nousresearch.com/docs/guides/use-mcp-with-hermes)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files/](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/cli/](https://hermes-agent.nousresearch.com/docs/user-guide/cli/)
* [https://hermes-agent.nousresearch.com/docs/user-guide/sessions/](https://hermes-agent.nousresearch.com/docs/user-guide/sessions/)
* [https://hermes-agent.nousresearch.com/docs/reference/faq/](https://hermes-agent.nousresearch.com/docs/reference/faq/)
* [https://hermes-agent.nousresearch.com/docs/guides/tips/](https://hermes-agent.nousresearch.com/docs/guides/tips/)
* [https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
* [https://github.com/NousResearch/hermes-agent/releases](https://github.com/NousResearch/hermes-agent/releases)
* [https://github.com/NousResearch/hermes-agent/issues](https://github.com/NousResearch/hermes-agent/issues)
* [https://github.com/NousResearch/hermes-agent/pulls](https://github.com/NousResearch/hermes-agent/pulls)
* [https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile](https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile)
* [https://github.com/NousResearch/hermes-agent/blob/main/gateway/run.py](https://github.com/NousResearch/hermes-agent/blob/main/gateway/run.py)
* [https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md](https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md)
* [https://github.com/NousResearch/hermes-agent/blob/main/cli-config.yaml.example](https://github.com/NousResearch/hermes-agent/blob/main/cli-config.yaml.example)
* [https://github.com/NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution)
* [https://github.com/NousResearch/hermes-paperclip-adapter](https://github.com/NousResearch/hermes-paperclip-adapter)
* [https://github.com/NousResearch](https://github.com/NousResearch)
* [https://x.com/NousResearch](https://x.com/NousResearch)
* [https://x.com/Teknium](https://x.com/Teknium)

[1]: https://hermes-agent.nousresearch.com/?utm_source=chatgpt.com "Hermes Agent - nous research"
[2]: https://hermes-agent.nousresearch.com/docs/ "Hermes Agent Documentation | Hermes Agent"
[3]: https://github.com/nousresearch/hermes-agent?utm_source=chatgpt.com "NousResearch/hermes-agent: The agent that grows with you"
[4]: https://github.com/NousResearch/hermes-agent/releases "Releases · NousResearch/hermes-agent · GitHub"
[5]: https://github.com/nousresearch?utm_source=chatgpt.com "Nous Research"
[6]: https://x.com/NousResearch/status/2040147789573714427?utm_source=chatgpt.com "Hermes Agent v0.7.0 is out now. Our headline update"
[7]: https://x.com/Teknium/status/2039102514508058675?utm_source=chatgpt.com "Useful guide for getting started with Hermes Agent:::"
[8]: https://github.com/NousResearch/hermes-agent-self-evolution?utm_source=chatgpt.com "NousResearch/hermes-agent-self-evolution"
[9]: https://github.com/NousResearch/hermes-paperclip-adapter?utm_source=chatgpt.com "Paperclip adapter for Hermes Agent"
[10]: https://hermes-agent.nousresearch.com/docs/getting-started/installation/?utm_source=chatgpt.com "Installation | Hermes Agent - nous research"
[11]: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/?utm_source=chatgpt.com "Configuration | Hermes Agent - nous research"
[12]: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/ "Messaging Gateway | Hermes Agent"
[13]: https://hermes-agent.nousresearch.com/docs/user-guide/docker/ "Docker | Hermes Agent"
[14]: https://hermes-agent.nousresearch.com/docs/developer-guide/architecture/ "Architecture | Hermes Agent"
[15]: https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/?utm_source=chatgpt.com "Tools & Toolsets | Hermes Agent - nous research"
[16]: https://hermes-agent.nousresearch.com/docs/user-guide/cli/?utm_source=chatgpt.com "CLI Interface | Hermes Agent - nous research"
[17]: https://github.com/NousResearch/hermes-agent/blob/main/Dockerfile "hermes-agent/Dockerfile at main · NousResearch/hermes-agent · GitHub"
[18]: https://github.com/NousResearch/hermes-agent/blob/main/gateway/run.py?utm_source=chatgpt.com "hermes-agent/gateway/run.py at main"
[19]: https://github.com/NousResearch/hermes-agent/blob/main/cli-config.yaml.example "hermes-agent/cli-config.yaml.example at main · NousResearch/hermes-agent · GitHub"
[20]: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/ "Configuration | Hermes Agent"
[21]: https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md "hermes-agent/AGENTS.md at main · NousResearch/hermes-agent · GitHub"
