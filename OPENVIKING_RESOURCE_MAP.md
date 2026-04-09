# OpenViking Resource Guide

## What this is

OpenViking is presented by its official website and repository as an open-source context database for AI agents, centered on a filesystem-style paradigm for memories, resources, and skills. The project’s primary official surfaces are the main website/docs and the `volcengine/OpenViking` GitHub repository. ([openviking.ai][1])

## Recommended use by an agent

* For **what OpenViking is**, start from the website homepage and docs landing page.
* For **installation, first setup, configuration, and running a server**, start from the docs site, then check `docker-compose.yml`, Helm, and the bot README.
* For **developer work, source layout, build requirements, and contributing**, start from the main repo, `CONTRIBUTING.md`, `docs/`, `design/`, `examples/`, and `crates/`.
* For **latest changes, roadmap signals, and real-world issues**, check Releases, GitHub Discussions, and GitHub Issues.
* For **community interaction**, use GitHub Discussions, Discord, and X. I did not find an official OpenViking Discourse forum; GitHub Discussions appears to be the main forum-like discussion surface. ([GitHub][2])

---

## 1. Official website and top-level docs

### Main entry points

* [OpenViking website](https://openviking.ai/)
* [OpenViking documentation home](https://openviking.ai/docs)
* [About / project overview in repo docs](https://github.com/volcengine/OpenViking/blob/main/docs/en/about/01-about-us.md)

These are the best starting points for understanding the product, terminology, positioning, and official documentation tree. The docs landing page exposes core sections such as introduction, quick start, configuration, FAQ, and about. ([openviking.ai][1])

### Use these for

* product overview
* official concepts and terminology
* first-time orientation
* agent-facing documentation starting point

---

## 2. Official documentation

### Primary docs

* [Docs home](https://openviking.ai/docs)
* [Quick start (repo docs page surfaced by search)](https://github.com/volcengine/OpenViking/blob/main/docs/en/getting-started/02-quickstart.md)
* [Server quick start / deployment-oriented doc](https://github.com/volcengine/OpenViking/blob/main/docs/en/getting-started/03-quickstart-server.md)
* [Core concepts / context types](https://github.com/volcengine/OpenViking/blob/main/docs/en/concepts/02-context-types.md)

### What an agent should look for there

* installation and first run
* model/provider configuration
* server setup
* core abstractions: memory, resource, skill
* context-loading model and retrieval model

The official docs and repo README cover installation, supported providers, model configuration, filesystem concepts, and advanced reading links. ([GitHub][2])

---

## 3. Administrator manual / operations resources

## Note

I did not find a separate official standalone “administrator manual” branded as such. For admin and operations work, the closest official sources are the docs site, the server quick start, Docker Compose, Helm chart, and bot/server configuration docs. ([openviking.ai][3])

### Best admin/ops sources

* [Docs home](https://openviking.ai/docs)
* [Server quick start](https://github.com/volcengine/OpenViking/blob/main/docs/en/getting-started/03-quickstart-server.md)
* [Docker Compose example](https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml)
* [Helm chart README](https://github.com/volcengine/OpenViking/tree/main/deploy/helm)
* [Vikingbot README](https://github.com/volcengine/OpenViking/blob/main/bot/README.md)

### Why these matter

* `docker-compose.yml` shows the default container image, exposed ports, persisted config/data mounts, health check, and default service name.
* Helm provides the clearest official Kubernetes deployment example, including storage, resource sizing, server host/port, and config structure.
* The bot README explains operational config such as `~/.openviking/ov.conf`, startup flow, and server connection behavior. ([GitHub][4])

### Use these for

* self-hosted deployment
* container startup
* persistent volume layout
* server port/defaults
* health checks
* bot/server config

---

## 4. Developer documentation

### Main developer sources

* [Main repository](https://github.com/volcengine/OpenViking)
* [Contributing guide](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING.md)
* [Docs folder](https://github.com/volcengine/OpenViking/tree/main/docs)
* [Examples folder](https://github.com/volcengine/OpenViking/tree/main/examples)
* [Crates folder](https://github.com/volcengine/OpenViking/tree/main/crates)
* [Vikingbot README](https://github.com/volcengine/OpenViking/blob/main/bot/README.md)

### What each is for

* **Main repository**: canonical source tree, README, issues, discussions, releases, and project metadata.
* **Contributing guide**: developer prerequisites, supported platforms, local development setup, and contribution workflow.
* **Docs folder**: English/Chinese docs and design material entry points.
* **Examples folder**: practical integration and plugin examples.
* **Crates folder**: Rust-side components, especially `ov_cli`.
* **Bot README**: bot-specific install/config/runtime details.

The repo structure explicitly includes `docs`, `examples`, `crates`, `deploy/helm`, `docker`, `tests`, and `bot`, which makes it the main source for implementation-oriented research. The contributing guide documents local build prerequisites such as Python, Go, Rust, C++ toolchain, and CMake. ([GitHub][2])

---

## 5. Most useful source-tree areas for an agent

### Core repo entry

* [Repository root](https://github.com/volcengine/OpenViking)

### Documentation and design

* [Docs](https://github.com/volcengine/OpenViking/tree/main/docs)
* [English docs](https://github.com/volcengine/OpenViking/tree/main/docs/en)
* [Design docs](https://github.com/volcengine/OpenViking/tree/main/docs/design)

### Deployment and operations

* [Docker Compose](https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml)
* [Helm chart](https://github.com/volcengine/OpenViking/tree/main/deploy/helm)
* [Docker assets](https://github.com/volcengine/OpenViking/tree/main/docker)

### Developer examples and integrations

* [Examples](https://github.com/volcengine/OpenViking/tree/main/examples)
* [Basic usage example](https://github.com/volcengine/OpenViking/tree/main/examples/basic-usage)
* [OpenClaw plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/openclaw-plugin)
* [OpenCode memory plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-memory-plugin)
* [Claude Code memory plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/claude-code-memory-plugin)
* [Multi-tenant examples](https://github.com/volcengine/OpenViking/tree/main/examples/multi_tenant)
* [Skills examples](https://github.com/volcengine/OpenViking/tree/main/examples/skills)

### CLI and low-level components

* [Rust crates](https://github.com/volcengine/OpenViking/tree/main/crates)
* [ov_cli crate](https://github.com/volcengine/OpenViking/tree/main/crates/ov_cli)
* [ragfs crate](https://github.com/volcengine/OpenViking/tree/main/crates/ragfs)
* [ragfs-python crate](https://github.com/volcengine/OpenViking/tree/main/crates/ragfs-python)

### Bot-specific area

* [bot/](https://github.com/volcengine/OpenViking/tree/main/bot)
* [bot README](https://github.com/volcengine/OpenViking/blob/main/bot/README.md)

The examples tree currently includes `basic-usage`, Claude-related memory plugins, OpenClaw and OpenCode integrations, multi-tenant examples, and skills examples. The crates tree includes `ov_cli`, `ragfs`, and `ragfs-python`. ([GitHub][5])

---

## 6. Repositories and official code hosting

### Official repository

* [volcengine/OpenViking](https://github.com/volcengine/OpenViking)

### Repository surfaces an agent should check

* [README](https://github.com/volcengine/OpenViking#readme)
* [Issues](https://github.com/volcengine/OpenViking/issues)
* [Pull requests](https://github.com/volcengine/OpenViking/pulls)
* [Discussions](https://github.com/volcengine/OpenViking/discussions)
* [Releases](https://github.com/volcengine/OpenViking/releases)
* [Actions](https://github.com/volcengine/OpenViking/actions)

### Distribution / package surface

* [GitHub Container package](https://github.com/orgs/volcengine/packages/container/package/openviking)

The main official code host appears to be a single GitHub repository under `volcengine/OpenViking`, with releases and a published container image available from GitHub’s package registry. ([GitHub][2])

---

## 7. Community and discussion

## Note on “community discourse”

I did not find an official OpenViking Discourse forum. The project’s official community/discussion surfaces currently appear to be GitHub Discussions plus community links exposed from the repo README. ([GitHub][6])

### Official community links

* [GitHub Discussions](https://github.com/volcengine/OpenViking/discussions)
* [Announcements category](https://github.com/volcengine/OpenViking/discussions/categories/announcements)
* [Q&A category](https://github.com/volcengine/OpenViking/discussions/categories/q-a)
* [Ideas category](https://github.com/volcengine/OpenViking/discussions/categories/ideas)
* [RFC category](https://github.com/volcengine/OpenViking/discussions/categories/rfc)
* [Discord](https://discord.com/invite/2ch6Q4GP7H)
* [X / Twitter](https://x.com/openvikingai)

### Additional community links exposed by the repo

* Lark group QR link is surfaced from the repo README
* WeChat group QR link is surfaced from the repo README

The repo README explicitly advertises community participation through GitHub Discussions, Discord, X, Lark, and WeChat. GitHub Discussions also exposes structured categories such as Announcements, Q&A, Ideas, and RFC, making it the closest thing to a forum/discourse hub for the project. ([GitHub][2])

---

## 8. Best sources for “latest trends” and current project direction

### Start here

* [Releases](https://github.com/volcengine/OpenViking/releases)
* [Announcements](https://github.com/volcengine/OpenViking/discussions/categories/announcements)
* [All Discussions](https://github.com/volcengine/OpenViking/discussions)
* [Issues](https://github.com/volcengine/OpenViking/issues)
* [Pull requests](https://github.com/volcengine/OpenViking/pulls)
* [X / Twitter](https://x.com/openvikingai)

### Why

* **Releases** show shipped versions.
* **Announcements** show maintainer summaries and feature rollouts.
* **Discussions** show ongoing design/RFC/community direction.
* **Issues/PRs** show current bugs, friction points, and work in progress.
* **X** is useful for outward-facing updates and ecosystem visibility.

For example, GitHub Discussions announcements include release notes like `v0.2.1`, and the repo shows current release history. Issues also expose current operational or security-relevant concerns. ([GitHub][7])

---

## 9. Best sources by research question

### “What is OpenViking?”

* [Website](https://openviking.ai/)
* [Docs home](https://openviking.ai/docs)
* [Repo README](https://github.com/volcengine/OpenViking#readme)

### “How do I install and configure it?”

* [Docs home](https://openviking.ai/docs)
* [Quick start](https://github.com/volcengine/OpenViking/blob/main/docs/en/getting-started/02-quickstart.md)
* [Server quick start](https://github.com/volcengine/OpenViking/blob/main/docs/en/getting-started/03-quickstart-server.md)
* [Docker Compose](https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml)
* [Helm chart](https://github.com/volcengine/OpenViking/tree/main/deploy/helm)

### “How is it structured internally?”

* [Docs](https://github.com/volcengine/OpenViking/tree/main/docs)
* [Design docs](https://github.com/volcengine/OpenViking/tree/main/docs/design)
* [Crates](https://github.com/volcengine/OpenViking/tree/main/crates)
* [Contributing guide](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING.md)

### “How do I integrate it with agent systems?”

* [Examples](https://github.com/volcengine/OpenViking/tree/main/examples)
* [OpenClaw plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/openclaw-plugin)
* [OpenCode memory plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/opencode-memory-plugin)
* [Claude Code memory plugin example](https://github.com/volcengine/OpenViking/tree/main/examples/claude-code-memory-plugin)
* [Vikingbot README](https://github.com/volcengine/OpenViking/blob/main/bot/README.md)

### “What are the current problems / open questions?”

* [Issues](https://github.com/volcengine/OpenViking/issues)
* [Discussions](https://github.com/volcengine/OpenViking/discussions)
* [RFC discussions](https://github.com/volcengine/OpenViking/discussions/categories/rfc)

### “What changed recently?”

* [Releases](https://github.com/volcengine/OpenViking/releases)
* [Announcements](https://github.com/volcengine/OpenViking/discussions/categories/announcements)
* [X / Twitter](https://x.com/openvikingai)

These surfaces map well to the kinds of questions an agent would need to answer: overview, install/configure, architecture, integrations, troubleshooting, and latest developments. ([GitHub][2])

---

## 10. Short canonical link list

* [https://openviking.ai/](https://openviking.ai/)
* [https://openviking.ai/docs](https://openviking.ai/docs)
* [https://github.com/volcengine/OpenViking](https://github.com/volcengine/OpenViking)
* [https://github.com/volcengine/OpenViking/issues](https://github.com/volcengine/OpenViking/issues)
* [https://github.com/volcengine/OpenViking/discussions](https://github.com/volcengine/OpenViking/discussions)
* [https://github.com/volcengine/OpenViking/releases](https://github.com/volcengine/OpenViking/releases)
* [https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING.md](https://github.com/volcengine/OpenViking/blob/main/CONTRIBUTING.md)
* [https://github.com/volcengine/OpenViking/tree/main/docs](https://github.com/volcengine/OpenViking/tree/main/docs)
* [https://github.com/volcengine/OpenViking/tree/main/examples](https://github.com/volcengine/OpenViking/tree/main/examples)
* [https://github.com/volcengine/OpenViking/tree/main/crates](https://github.com/volcengine/OpenViking/tree/main/crates)
* [https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml](https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml)
* [https://github.com/volcengine/OpenViking/tree/main/deploy/helm](https://github.com/volcengine/OpenViking/tree/main/deploy/helm)
* [https://github.com/volcengine/OpenViking/blob/main/bot/README.md](https://github.com/volcengine/OpenViking/blob/main/bot/README.md)
* [https://discord.com/invite/2ch6Q4GP7H](https://discord.com/invite/2ch6Q4GP7H)
* [https://x.com/openvikingai](https://x.com/openvikingai)

This canonical list is the minimum set I would hand to another agent as the official OpenViking research surface. ([GitHub][2])

[1]: https://openviking.ai/?utm_source=chatgpt.com "OpenViking - The Context File System for AI Agents"
[2]: https://github.com/volcengine/OpenViking "GitHub - volcengine/OpenViking: OpenViking is an open-source context database designed specifically for AI Agents(such as openclaw). OpenViking unifies the management of context (memory, resources, and skills) that Agents need through a file system paradigm, enabling hierarchical context delivery and self-evolving. · GitHub"
[3]: https://openviking.ai/docs?utm_source=chatgpt.com "OpenViking - The Context File System for AI Agents"
[4]: https://github.com/volcengine/OpenViking/blob/main/docker-compose.yml "OpenViking/docker-compose.yml at main · volcengine/OpenViking · GitHub"
[5]: https://github.com/volcengine/OpenViking/tree/main/examples "OpenViking/examples at main · volcengine/OpenViking · GitHub"
[6]: https://github.com/volcengine/OpenViking/discussions?utm_source=chatgpt.com "volcengine OpenViking · Discussions"
[7]: https://github.com/volcengine/OpenViking/discussions/362?utm_source=chatgpt.com "v0.2.1 · volcengine OpenViking · Discussion #362"
