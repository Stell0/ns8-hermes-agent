#!/usr/bin/env python3

import sys
from pathlib import Path


def replace_once(path, old, new):
    content = path.read_text(encoding="utf-8")
    if new in content:
        return
    if old not in content:
        raise SystemExit(f"expected snippet not found in {path}")

    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def main():
    repo_root = Path(sys.argv[1]).resolve()

    replace_once(
        repo_root / "web" / "src" / "main.tsx",
        """import { createRoot } from \"react-dom/client\";\nimport { BrowserRouter } from \"react-router-dom\";\nimport \"./index.css\";\nimport App from \"./App\";\nimport { I18nProvider } from \"./i18n\";\nimport { ThemeProvider } from \"./themes\";\nimport { exposePluginSDK } from \"./plugins\";\n\n// Expose the plugin SDK before rendering so plugins loaded via <script>\n// can access React, components, etc. immediately.\nexposePluginSDK();\n\ncreateRoot(document.getElementById(\"root\")!).render(\n  <BrowserRouter>\n""",
        """import { createRoot } from \"react-dom/client\";\nimport { BrowserRouter } from \"react-router-dom\";\nimport \"./index.css\";\nimport App from \"./App\";\nimport { I18nProvider } from \"./i18n\";\nimport { ThemeProvider } from \"./themes\";\nimport { exposePluginSDK } from \"./plugins\";\n\ndeclare global {\n  interface Window {\n    __HERMES_BASE_URL__?: string;\n  }\n}\n\nconst BASE_URL = window.__HERMES_BASE_URL__ || undefined;\n\n// Expose the plugin SDK before rendering so plugins loaded via <script>\n// can access React, components, etc. immediately.\nexposePluginSDK();\n\ncreateRoot(document.getElementById(\"root\")!).render(\n  <BrowserRouter basename={BASE_URL}>\n""",
    )

    replace_once(
        repo_root / "web" / "src" / "lib" / "api.ts",
        'const BASE = "";\n',
        'const BASE = typeof window !== "undefined" ? window.__HERMES_BASE_URL__ ?? "" : "";\n',
    )
    replace_once(
        repo_root / "web" / "src" / "lib" / "api.ts",
        """declare global {\n  interface Window {\n    __HERMES_SESSION_TOKEN__?: string;\n  }\n}\n""",
        """declare global {\n  interface Window {\n    __HERMES_BASE_URL__?: string;\n    __HERMES_SESSION_TOKEN__?: string;\n  }\n}\n""",
    )

    replace_once(
        repo_root / "web" / "src" / "plugins" / "usePlugins.ts",
        """import { api } from \"@/lib/api\";\nimport type { PluginManifest, RegisteredPlugin } from \"./types\";\nimport { getPluginComponent, onPluginRegistered } from \"./registry\";\n\nexport function usePlugins() {\n""",
        """import { api } from \"@/lib/api\";\nimport type { PluginManifest, RegisteredPlugin } from \"./types\";\nimport { getPluginComponent, onPluginRegistered } from \"./registry\";\n\nconst DASHBOARD_BASE_URL =\n  (window as Window & { __HERMES_BASE_URL__?: string }).__HERMES_BASE_URL__ ?? \"\";\n\nexport function usePlugins() {\n""",
    )
    replace_once(
        repo_root / "web" / "src" / "plugins" / "usePlugins.ts",
        '        const cssUrl = `/dashboard-plugins/${manifest.name}/${manifest.css}`;\n',
        '        const cssUrl = `${DASHBOARD_BASE_URL}/dashboard-plugins/${manifest.name}/${manifest.css}`;\n',
    )
    replace_once(
        repo_root / "web" / "src" / "plugins" / "usePlugins.ts",
        '      const jsUrl = `/dashboard-plugins/${manifest.name}/${manifest.entry}`;\n',
        '      const jsUrl = `${DASHBOARD_BASE_URL}/dashboard-plugins/${manifest.name}/${manifest.entry}`;\n',
    )

    replace_once(
        repo_root / "web" / "index.html",
        '<link rel="icon" type="image/svg+xml" href="/favicon.ico" />\n',
        '<link rel="icon" type="image/svg+xml" href="./favicon.ico" />\n',
    )

    replace_once(
        repo_root / "web" / "vite.config.ts",
        "export default defineConfig({\n",
        "export default defineConfig({\n  base: \"./\",\n",
    )


if __name__ == "__main__":
    main()