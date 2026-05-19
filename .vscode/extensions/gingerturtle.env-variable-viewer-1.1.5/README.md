# Environment Variable Viewer — .env & dotenv File Viewer / Manager for VS Code

<div align="center">

![VS Code Marketplace Version](https://vsmarketplacebadges.dev/version-short/GingerTurtle.env-variable-viewer.png)
![VS Code Marketplace Installs](https://vsmarketplacebadges.dev/installs-short/GingerTurtle.env-variable-viewer.png)
![VS Code Marketplace Rating](https://vsmarketplacebadges.dev/rating-short/GingerTurtle.env-variable-viewer.png)
![License](https://img.shields.io/github/license/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier?style=for-the-badge)

**The [#1](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/issues/1) .env file viewer, dotenv manager & environment variable tool for VS Code**

View • Search • Copy • Export • Validate your environment variables from `.env` files

Works with `.env`, `.env.local`, `.env.production`, `.env.development`, `.env.example` and more!  
Perfect for **React**, **Next.js**, **Vue**, **NestJS**, **Node.js**, **Vite**, **Angular**, **Svelte**, **Nuxt**, **Docker** & **Kubernetes**.

[Install Now](https://marketplace.visualstudio.com/items?itemName=GingerTurtle.env-variable-viewer) • [Report Bug](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/issues) • [Request Feature](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/issues)

</div>

---

> **Stop manually hunting through `.env` files.** This extension gives you a dedicated tree view panel and quick-pick UI to view, search, copy, and manage all your dotenv environment variables — across every `.env` file in your workspace — without ever leaving VS Code.

---

## 🎯 Why You Need This dotenv Viewer

Are you tired of:
- ❌ Opening multiple `.env` files to find one variable?
- ❌ Copying environment variables manually and making mistakes?
- ❌ Not knowing if your PORT or URL values are valid?
- ❌ Switching between development and production configs?

**This extension solves all of that!** ✨

---

## 🚀 Quick Start

1. **Install** the extension from [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=GingerTurtle.env-variable-viewer)
2. **Open** any project with `.env` files
3. **Look** for "Environment Variables" in your Explorer sidebar
4. **Done!** Start viewing and managing your environment variables

Or press **`Ctrl+Alt+E`** (Mac: `Cmd+Alt+E`) to open the quick picker!

---

## ✨ Key Features

### 🔍 **Smart .env & dotenv File Detection**
Automatically finds and loads ALL your dotenv environment files:
- ✅ `.env` (main)
- ✅ `.env.local` (local overrides)
- ✅ `.env.development` (dev environment)
- ✅ `.env.production` (production)
- ✅ `.env.test` (testing)
- ✅ `.env.staging` (staging)
- ✅ `.env.example` (template)
- ✅ **Custom patterns** via settings

**Perfect for:** React, Next.js, Vue, Angular, Vite, Node.js, Docker, and any framework using .env / dotenv files!

---

### 📋 **Instant Copy & Paste**
Copy environment variables with **one click**:
- 🔑 **Copy Key** - Just the variable name (e.g., `API_KEY`)
- 📝 **Copy Value** - Just the value (e.g., `abc123xyz`)
- 📦 **Copy Both** - Full pair (e.g., `API_KEY=abc123xyz`)

**Use case:** Need to paste an API key into Postman? One click. Done. ✅

---

### 📤 **Export to Any Format** _(v1.1.0)_
Export your environment variables to:
- **JSON** - For API documentation
- **YAML** - For Kubernetes/Docker configs
- **CSV** - For spreadsheets and analysis
- **.env** - Create backups or share templates

**Use case:** Share your .env structure with your team (without exposing real values!)

---

### ✅ **Automatic Validation** _(v1.1.0)_
Catch configuration errors **before** they break production:
- ⚠️ **Invalid ports** - "8080abc" is not a valid port!
- ⚠️ **Malformed URLs** - Missing http:// or https://
- ⚠️ **Empty secrets** - Your API_KEY shouldn't be blank!
- ⚠️ **Placeholder values** - "your-api-key-here" needs to be replaced
- ⚠️ **Wrong booleans** - Use "true" or "false", not "yes" or "no"

**Visual warnings** with yellow icons and tooltips - fix issues in seconds!

---

### 🌳 **Dual Interface**
Choose how you work:

**1. Tree View Panel** (Sidebar)
- See all .env files organized in one place
- Expand/collapse files
- Hover to see full values
- Right-click for copy options

**2. Quick Pick Interface** (Keyboard)
- Press `Ctrl+Alt+E` to open
- Type to search instantly
- Select and copy in one action
- Perfect for keyboard warriors ⌨️

---

### 🔒 **Security First**
- **Sensitive Value Masking** - Automatically hides passwords, secrets, API keys, and tokens
- **Masked by default** - Enabled out of the box (can be disabled)
- **Screenshot safe** - Safe to share screens during meetings
- **No data sent** - Everything runs locally in VS Code

---

### 🔎 **Powerful Search**
Find variables **instantly**:
- Search across **all** .env files at once
- **Fuzzy matching** - typos don't matter
- Search both **keys** and **values**
- **Case-insensitive**
- Press `Ctrl+Alt+F` when tree view is focused

**Example:** Type "port" to find `PORT`, `DATABASE_PORT`, `REDIS_PORT`, etc.

---

## 🎬 See It In Action

<!-- TODO: Add screenshots/GIFs here -->

**Tree View:**
```
📁 .env (5 variables)
  🔑 PORT = 3000
  🔑 DATABASE_URL = postgres://...
  ⚠️ API_KEY = (empty) ← validation warning!

📁 .env.production (8 variables)
  🔑 NODE_ENV = production
  🔑 API_URL = https://api.example.com
  ...
```

---

## 🎯 Perfect For — .env Variable Management in Any Stack

| Use Case | How This Helps |
|----------|---------------|
| **Frontend Developers** (React, Vue, Angular) | Quickly access API URLs, feature flags, and environment configs |
| **Backend Developers** (Node.js, Python, Go) | Manage database connections, service URLs, and API keys |
| **DevOps Engineers** | Export configs to Kubernetes YAML or Docker Compose |
| **Full-Stack Teams** | Share .env templates, validate configs before deployment |
| **Open Source Projects** | Provide .env.example with validation for contributors |

---

## 📖 Complete Feature List

### Core Features
- ✅ **Multi-file support** - All .env variants automatically detected
- ✅ **Tree view panel** - Organized sidebar in Explorer
- ✅ **Quick pick interface** - Keyboard-driven search and select
- ✅ **Smart copying** - Key, value, or both with one click
- ✅ **Line numbers** - Jump to exact location in file
- ✅ **Auto-refresh** - Updates when .env files change
- ✅ **Context menus** - Right-click anywhere for actions
- ✅ **Multi-workspace** - Works with VS Code workspaces

### Advanced Features _(v1.1.0)_
- ✅ **Export to JSON/YAML/CSV/.env** - Share or backup configs
- ✅ **Variable validation** - Catch errors before they break production
- ✅ **Validation warnings view** - See all issues at a glance
- ✅ **Visual indicators** - Warning icons for invalid variables
- ✅ **Quick fix navigation** - Click warning → jump to file location

### Security & Privacy
- ✅ **Sensitive value masking** - Hide passwords, secrets, keys, tokens
- ✅ **Masked by default** - Secure out of the box
- ✅ **Tooltip masking** - Masked values stay masked everywhere
- ✅ **No telemetry** - Your data never leaves your machine
- ✅ **Path validation** - Protection against malicious workspace settings

---

## ⚙️ Configuration

Customize the extension to fit your workflow:

### Settings

```json
{
  // Which files to scan (default: common .env variants)
  "envViewer.envFilePatterns": [
    ".env",
    ".env.local",
    ".env.development",
    ".env.production"
  ],

  // Show line numbers in tree view and quick pick
  "envViewer.showLineNumbers": true,

  // Automatically mask sensitive values (RECOMMENDED)
  "envViewer.maskSensitiveValues": true,

  // Auto-refresh when .env files change
  "envViewer.autoRefresh": true,

  // How to sort variables
  "envViewer.sortVariables": "alphabetical" // or "none", "byFile"
}
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Alt+E` / `Cmd+Alt+E` | Open environment variable viewer |
| `Ctrl+Alt+F` / `Cmd+Alt+F` | Search variables (when tree focused) |

**Tip:** Customize shortcuts via `File > Preferences > Keyboard Shortcuts`

---

## 💡 Usage Examples

### Example 1: Copy API Key to Postman
1. Press `Ctrl+Alt+E`
2. Type "api"
3. Click your API_KEY
4. Value copied! Paste into Postman ✅

### Example 2: Export Config for Docker
1. Click the 📤 Export button in tree view
2. Select "YAML" format
3. Save as `docker-config.yaml`
4. Use in your Dockerfile or docker-compose.yml ✅

### Example 3: Find All Port Configurations
1. Click 🔍 Search in tree view
2. Type "port"
3. See all PORT variables across all .env files
4. Jump to any file with one click ✅

### Example 4: Validate Before Deployment
1. Click ⚠️ Validation Warnings button
2. See all configuration errors
3. Click any warning to jump to file
4. Fix issues and deploy confidently ✅

---

## 🤔 FAQ

<details>
<summary><strong>Q: Does this work with NestJS and its ConfigModule?</strong></summary>

**A:** Yes! NestJS projects typically store configuration in `.env` files loaded via `@nestjs/config` or the `dotenv` package. This extension detects and displays all those variables automatically.
</details>

<details>
<summary><strong>Q: Does this work with Nuxt and Remix?</strong></summary>

**A:** Yes! Both Nuxt (using `runtimeConfig` backed by `.env`) and Remix (using `.env` with `process.env`) are fully supported. The extension auto-detects `.env` files in your project root.
</details>

<details>
<summary><strong>Q: Does this work with .env.local and other variants?</strong></summary>

**A:** Yes! It automatically detects `.env`, `.env.local`, `.env.development`, `.env.production`, `.env.test`, `.env.staging`, `.env.example`, and any custom patterns you configure.
</details>

<details>
<summary><strong>Q: Is my .env / dotenv data secure?</strong></summary>

**A:** Absolutely. All processing happens **locally** in VS Code. Nothing is ever sent to external servers. Sensitive values are masked by default, and the extension has passed comprehensive security audits.
</details>

<details>
<summary><strong>Q: Can I use this with Docker/Kubernetes?</strong></summary>

**A:** Yes! Export your variables to YAML format for Kubernetes ConfigMaps/Secrets, or use .env export for Docker Compose.
</details>

<details>
<summary><strong>Q: Does it support multiple workspaces?</strong></summary>

**A:** Yes! If you have multiple workspace folders open, the extension scans all of them.
</details>

<details>
<summary><strong>Q: Can I share my .env structure without exposing values?</strong></summary>

**A:** Yes! Export to JSON/YAML/CSV with masked values, or manually create a `.env.example` file. You can copy keys only and share those with your team.
</details>

---

## 🆚 Why Choose This .env Viewer Over Other Extensions?

| Feature | This Extension | Other .env / dotenv Extensions |
|---------|---------------|--------------------------------|
| **Tree View** | ✅ Yes | ❌ Most don't have |
| **Quick Pick** | ✅ Yes | ❌ Most don't have |
| **Export (JSON/YAML/CSV)** | ✅ Yes | ❌ Rare |
| **Validation** | ✅ Yes (ports, URLs, booleans) | ❌ None |
| **Multi-file Support** | ✅ All variants | ⚠️ Limited |
| **Security Masking** | ✅ Masked by default | ⚠️ Optional or missing |
| **Search Across Files** | ✅ Yes | ❌ Rare |
| **NestJS / Nuxt Support** | ✅ Yes | ⚠️ Varies |
| **Active Development** | ✅ Regular updates | ⚠️ Many abandoned |
| **Zero Vulnerabilities** | ✅ Audited & secure | ❓ Unknown |

---

## 📊 Supported Frameworks & dotenv Environments

Works perfectly with any framework or runtime that uses `.env` / `dotenv` files:

- ⚛️ **React** (Create React App, Vite, react-scripts)
- ▲ **Next.js** (All versions, App Router & Pages Router)
- 💚 **Vue.js** (Vue CLI, Vite, Nuxt)
- 🟢 **Nuxt** (Nuxt 2 & Nuxt 3)
- 🅰️ **Angular**
- 🔷 **Svelte** / **SvelteKit**
- ⚡ **Vite** (any Vite-based project)
- 🐤 **NestJS** (ConfigModule, dotenv)
- 🟢 **Node.js** (Express, Fastify, Koa, Hapi, dotenv package)
- 🎸 **Remix**
- 🚀 **Astro**
- 🐍 **Python** (Django, Flask, FastAPI with python-dotenv)
- 🐹 **Go** (godotenv)
- 🦀 **Rust** (dotenv)
- 🐳 **Docker** / **Docker Compose** (.env files)
- ☸️ **Kubernetes** (via export to YAML)

---

## 🐛 Troubleshooting

### .env viewer not showing up?
- Make sure you have at least one `.env` file in your workspace root
- Check that the file is named correctly (`.env`, not `env.txt`)
- Restart VS Code if needed

### dotenv variables not updating?
- Make sure `envViewer.autoRefresh` is enabled in settings
- Click the 🔄 Refresh button in the tree view
- Save your .env file to trigger refresh

### Can't find a specific file type?
- Add your custom pattern to `envViewer.envFilePatterns` in settings
- Example: `".env.custom"`, `"config.env"`

---

## 🛣️ Roadmap

### Version 1.2.0 (Coming Soon)
- [ ] Bulk editing (rename/update multiple variables)
- [ ] Encryption support for sensitive values
- [ ] Environment diff view (compare .env files)
- [ ] Variable templates and presets

### Version 1.3.0
- [ ] Cloud secret manager integration (AWS, Azure, GCP)
- [ ] Team collaboration features
- [ ] Variable dependency tracking
- [ ] Auto-completion in .env files

**Vote for features:** [GitHub Issues](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/issues)

---

## ☕ Support Development

This extension is **100% free** and will always be. If it saves you time and you want to support development:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-☕-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/gingerturtle)

Your support helps:
- ✨ Keep the extension free for everyone
- 🚀 Fund new features and improvements
- 🐛 Fix bugs and maintain compatibility
- 📚 Create better documentation

**Thank you!** 🙏

---

## 📝 Changelog

See [CHANGELOG.md](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/blob/HEAD/CHANGELOG.md) for detailed release notes.

### Latest (v1.1.5)
- 🔧 **Badges:** Replaced the broken VS Marketplace badge source so version, installs, and rating indicators render correctly again

### v1.1.4
- 🔧 **Metadata:** Corrected the public GitHub repository links across the extension metadata and README so issues, discussions, and documentation resolve properly

### v1.1.3
- 🔍 **Discoverability:** Restored `Programming Languages` category (was mistakenly replaced in v1.1.2), expanded framework coverage (NestJS, Nuxt, Remix, Astro, SvelteKit, Express, Fastify), added "Popular Searches" section to README, optimized keywords

### v1.1.2
- 🔍 **SEO:** Improved marketplace discoverability — better keywords, description & display name

### v1.1.0
- ✨ **NEW:** Export to JSON, YAML, CSV, .env
- ✨ **NEW:** Variable validation with warnings
- 🔒 **SECURITY:** Fixed path traversal vulnerability
- 🔒 **SECURITY:** Fixed masking bypass issues
- 🐛 **FIXED:** All resource leaks and race conditions
- ⬆️ **UPDATED:** TypeScript 5.3, 0 npm vulnerabilities

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/blob/HEAD/LICENSE) file for details.

---

## 🔍 Popular Searches for This Extension

Looking for any of these? This extension covers them all:

- **dotenv viewer for VS Code** — browse all dotenv variables in a tree panel
- **.env file manager VS Code** — manage multiple .env files from one place
- **environment variable viewer VS Code** — see every env var at a glance
- **env file browser extension** — navigate .env files without opening each one
- **copy environment variable VS Code** — one-click copy key, value, or both
- **NestJS env viewer** — view .env variables used by NestJS ConfigModule
- **Next.js dotenv extension** — manage `.env.local` and `.env.production` for Next.js
- **export dotenv to JSON YAML** — export variables for Docker, Kubernetes, CI/CD
- **dotenv validation VS Code** — catch invalid ports, URLs, and placeholders
- **secret masking .env VS Code** — hide passwords and API keys on screen
- **process.env viewer VS Code** — inspect all process.env variables defined in .env

---

## 🌟 Show Your Support

If this extension helps you, please:
- ⭐ **Star** the [GitHub repository](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier)
- ✍️ **Leave a review** on the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=GingerTurtle.env-variable-viewer)
- 🐦 **Share** with your developer friends
- 💬 **Join** the discussion on [GitHub](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/discussions)

---

<div align="center">

**Made with ❤️ for developers who work with .env files daily**

[Install Now](https://marketplace.visualstudio.com/items?itemName=GingerTurtle.env-variable-viewer) • [Documentation](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier) • [Report Issue](https://github.com/Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier/issues)

</div>
