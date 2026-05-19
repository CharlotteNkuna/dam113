# Changelog

All notable changes to the "Environment Variable Viewer" extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.5] - 2026-04-10

### 🔧 Fixed
- Replaced broken VS Marketplace shields with a more reliable badge source in `README.md`
- Refreshed release metadata and packaging for the badge fix

## [1.1.4] - 2026-04-10

### 🔧 Fixed
- Updated repository metadata to the correct GitHub project: `Goldenvikingsunset/Specific-.env-File-Variable-ViewerCopier`
- Fixed README links for issues, discussions, documentation, and license badge so release metadata points to the right repo

## [1.1.3] - 2026-03-20

### 🔍 Discoverability Improvements
- **Restored `Programming Languages` category** — replaces `Formatters` (inaccurate); `Programming Languages` drives significantly more browse traffic on the VS Code Marketplace
- **Expanded keywords**: added `nestjs`, `nuxt`, `nuxtjs`, `sveltekit`, `express`, `fastify`, `remix`, `astro`, `env file viewer`, `env file browser`, `secret manager`, `api key viewer`, `dotenv extension`, `dotenv plugin`, `dotenv support`, `twelve-factor`, `12-factor`, and more
- **Removed low-signal generic keywords**: `environment`, `config`, `development`, `deployment` — these dilute search ranking without targeting real user searches
- **Updated description**: now includes Svelte, NestJS, Python for broader framework coverage
- **README**: expanded framework support section to list NestJS, Nuxt, SvelteKit, Express, Fastify, Remix, Astro; added NestJS/Nuxt FAQ entries; added "Popular Searches" section for marketplace indexing; improved H1 tagline

## [1.1.2] - 2026-03-17

### 🔍 SEO Improvements
- Updated display name to include `dotenv` keyword for broader search coverage
- Optimised description: front-loaded key terms, added Vite, removed emoji for better plain-text indexing
- Expanded keywords: added `dotenv viewer`, `dotenv editor`, `dotenv manager`, `env inspector`, `vite env`, `twelve factor`, and more
- Updated categories: replaced `Programming Languages` with `Linters` for more accurate classification
- Improved README title and opening section with higher-value search terms
- Added Vite and dotenv-specific mentions throughout feature descriptions and framework list

## [1.1.1] - 2026-03-11

### 🔧 Fixed
- **CRITICAL SEO Fix**: Reverted display name to "Environment Variable Viewer" (primary) to restore search rankings
- Optimized description to prioritize "environment variables" keyword
- This fixes the install drop caused by v1.1.0 name change

## [1.0.0] - 2025-06-02

### Added
- Initial release of Environment Variable Viewer
- Tree view panel in Explorer sidebar
- Quick pick interface with Ctrl+Shift+E shortcut
- Support for multiple .env file variants (.env, .env.local, .env.development, etc.)
- Smart copying options (key only, value only, key=value pair)
- Real-time search functionality with fuzzy matching
- Configurable file patterns via settings
- Auto-refresh when .env files change
- Line number display for easy navigation
- Security feature to mask sensitive values
- Context menu integration for .env files
- Multi-workspace support
- Comprehensive settings configuration
- Right-click context menus for copying operations
- File navigation with quick open functionality
- **Sponsor button** in tree view to support development

### Features
- **Tree View Panel**: Persistent sidebar showing organized environment files
- **Quick Pick Interface**: Fast keyboard-driven variable selection
- **Multi-File Support**: Automatic detection of various .env file types
- **Advanced Search**: Global search across all variables and values
- **Smart Copying**: Multiple copy options for different use cases
- **Security**: Optional masking of sensitive variable values
- **Customization**: Extensive configuration options
- **Developer Experience**: Keyboard shortcuts, auto-refresh, line numbers

### Configuration Options
- `envViewer.envFilePatterns`: Customize which files to scan
- `envViewer.showLineNumbers`: Toggle line number display
- `envViewer.maskSensitiveValues`: Automatic masking of sensitive data
- `envViewer.autoRefresh`: Auto-refresh on file changes
- `envViewer.sortVariables`: Control variable sorting behavior

### Commands
- `envViewer.viewVariables`: Open quick pick interface
- `envViewer.copyVariable`: Alternative command for variable copying
- `envViewer.refreshTree`: Manually refresh tree view
- `envViewer.openFile`: Open source .env file
- `envViewer.copyKey`: Copy variable key only
- `envViewer.copyValue`: Copy variable value only
- `envViewer.copyBoth`: Copy key=value pair
- `envViewer.searchVariables`: Search across all variables
- `envViewer.toggleQuickPick`: Toggle quick pick view
- `envViewer.sponsor`: Support extension development (☕ Buy Me a Coffee)

### Keyboard Shortcuts
- `Ctrl+Shift+E` (Windows/Linux) / `Cmd+Shift+E` (Mac): Open variable viewer
- `Ctrl+Shift+F` (Windows/Linux) / `Cmd+Shift+F` (Mac): Search variables (when tree focused)

### 1.1.0 - Enhanced Features
- Export variables to different formats (JSON, YAML, etc.)
- Variable validation and suggestions
- Bulk editing capabilities
- Enhanced security with encryption support


### 1.2.0 - Cloud Integration
- Integration with cloud secret managers (AWS Secrets, Azure Key Vault)
- Environment variable synchronization
- Remote configuration management

### 1.3.0 - Advanced Tools
- Environment variable diff view
- Variable dependency tracking
- Configuration templates
- Team collaboration features