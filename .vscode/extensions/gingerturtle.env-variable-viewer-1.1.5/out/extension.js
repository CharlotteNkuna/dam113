"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
class EnvFileTreeItem extends vscode.TreeItem {
    constructor(label, collapsibleState, envFile, envVar) {
        super(label, collapsibleState);
        this.label = label;
        this.collapsibleState = collapsibleState;
        this.envFile = envFile;
        this.envVar = envVar;
        if (envFile) {
            this.tooltip = `${envFile.path} (${envFile.variables.length} variables)`;
            this.description = `${envFile.variables.length} vars`;
            this.contextValue = 'envFile';
            this.iconPath = new vscode.ThemeIcon('file-code');
            this.resourceUri = vscode.Uri.file(envFile.path);
        }
        else if (envVar) {
            const displayValue = envVar.masked ? '***' : envVar.value;
            let tooltip = `${envVar.key}=${displayValue} (Line ${envVar.line})`;
            // Add validation warning to tooltip
            if (envVar.validationWarning) {
                tooltip += `\n⚠️ ${envVar.validationWarning}`;
            }
            this.tooltip = tooltip;
            this.description = displayValue;
            this.contextValue = 'envVariable';
            // Show warning icon if validation failed
            this.iconPath = envVar.validationWarning
                ? new vscode.ThemeIcon('warning', new vscode.ThemeColor('problemsWarningIcon.foreground'))
                : new vscode.ThemeIcon('symbol-variable');
        }
    }
}
class EnvVariablesProvider {
    constructor() {
        this._onDidChangeTreeData = new vscode.EventEmitter();
        this.onDidChangeTreeData = this._onDidChangeTreeData.event;
        this.envFiles = [];
    }
    refresh() {
        this._onDidChangeTreeData.fire();
    }
    getTreeItem(element) {
        return element;
    }
    async getChildren(element) {
        if (!element) {
            // Root level - return env files
            await this.loadEnvFiles();
            return this.envFiles.map(file => new EnvFileTreeItem(file.name, vscode.TreeItemCollapsibleState.Expanded, file, undefined));
        }
        else if (element.envFile) {
            // File level - return variables
            const config = vscode.workspace.getConfiguration('envViewer');
            const showLineNumbers = config.get('showLineNumbers', true);
            return element.envFile.variables.map(variable => {
                const label = showLineNumbers ? `${variable.key} (L${variable.line})` : variable.key;
                return new EnvFileTreeItem(label, vscode.TreeItemCollapsibleState.None, undefined, variable);
            });
        }
        return [];
    }
    async loadEnvFiles() {
        const config = vscode.workspace.getConfiguration('envViewer');
        const patterns = config.get('envFilePatterns', ['.env']);
        const sortMode = config.get('sortVariables', 'alphabetical');
        this.envFiles = [];
        if (!vscode.workspace.workspaceFolders) {
            return;
        }
        for (const folder of vscode.workspace.workspaceFolders) {
            for (const pattern of patterns) {
                // Security: Validate pattern to prevent path traversal
                if (!isValidEnvFilePattern(pattern)) {
                    outputChannel.appendLine(`Skipping invalid pattern: "${pattern}" - contains path traversal or absolute path`);
                    continue;
                }
                const envPath = path.resolve(folder.uri.fsPath, pattern);
                // Security: Ensure resolved path is within workspace boundary
                const workspaceRoot = folder.uri.fsPath;
                if (!envPath.startsWith(workspaceRoot + path.sep) && envPath !== workspaceRoot) {
                    outputChannel.appendLine(`Skipping pattern "${pattern}" - resolves outside workspace`);
                    continue;
                }
                if (fs.existsSync(envPath)) {
                    try {
                        const envFile = await this.parseEnvFile(envPath);
                        if (envFile && envFile.variables.length > 0) {
                            this.envFiles.push(envFile);
                        }
                    }
                    catch (error) {
                        outputChannel.appendLine(`Error parsing ${envPath}: ${error}`);
                    }
                }
            }
        }
        // Sort files and variables
        if (sortMode === 'alphabetical') {
            this.envFiles.sort((a, b) => a.name.localeCompare(b.name));
            this.envFiles.forEach(file => {
                file.variables.sort((a, b) => a.key.localeCompare(b.key));
            });
        }
    }
    async parseEnvFile(filePath) {
        try {
            const content = fs.readFileSync(filePath, 'utf8');
            const lines = content.split('\n');
            const variables = [];
            const config = vscode.workspace.getConfiguration('envViewer');
            const maskSensitive = config.get('maskSensitiveValues', false);
            lines.forEach((line, index) => {
                const trimmedLine = line.trim();
                // Skip empty lines and comments
                if (!trimmedLine || trimmedLine.startsWith('#')) {
                    return;
                }
                // Parse key=value pairs
                const equalIndex = trimmedLine.indexOf('=');
                if (equalIndex > 0) {
                    const key = trimmedLine.substring(0, equalIndex).trim();
                    let value = trimmedLine.substring(equalIndex + 1).trim();
                    // Remove quotes if present
                    if ((value.startsWith('"') && value.endsWith('"')) ||
                        (value.startsWith("'") && value.endsWith("'"))) {
                        value = value.slice(1, -1);
                    }
                    // Check if should be masked
                    const shouldMask = maskSensitive && this.isSensitiveKey(key);
                    // Validate variable
                    const validationWarning = validateEnvVariable(key, value);
                    variables.push({
                        key,
                        value,
                        line: index + 1,
                        file: filePath,
                        masked: shouldMask,
                        validationWarning
                    });
                }
            });
            return {
                path: filePath,
                name: path.basename(filePath),
                variables
            };
        }
        catch (error) {
            outputChannel.appendLine(`Error reading ${filePath}: ${error}`);
            return null;
        }
    }
    isSensitiveKey(key) {
        const sensitivePatterns = ['password', 'secret', 'key', 'token', 'auth', 'api'];
        const lowerKey = key.toLowerCase();
        return sensitivePatterns.some(pattern => lowerKey.includes(pattern));
    }
    getEnvFiles() {
        return this.envFiles;
    }
}
// Validation helper functions
function validateEnvVariable(key, value) {
    // Check for common patterns
    const upperKey = key.toUpperCase();
    // Validate PORT
    if (upperKey.includes('PORT')) {
        const port = parseInt(value, 10);
        if (isNaN(port) || port < 1 || port > 65535) {
            return `Invalid port number: should be between 1 and 65535`;
        }
    }
    // Validate URL
    if (upperKey.includes('URL') || upperKey.includes('URI') || upperKey.includes('ENDPOINT')) {
        if (value && !value.match(/^(https?:\/\/|\/)/)) {
            return `Possibly invalid URL: should start with http://, https://, or /`;
        }
    }
    // Validate boolean
    if (upperKey.includes('ENABLE') || upperKey.includes('DISABLE') || upperKey.includes('DEBUG') || upperKey === 'NODE_ENV') {
        const lowerValue = value.toLowerCase();
        if (!['true', 'false', '1', '0', 'yes', 'no', 'development', 'production', 'test', 'staging'].includes(lowerValue)) {
            return `Possibly invalid boolean/environment value`;
        }
    }
    // Check for empty required values
    if ((upperKey.includes('KEY') || upperKey.includes('SECRET') || upperKey.includes('TOKEN') || upperKey.includes('PASSWORD')) && !value.trim()) {
        return `Sensitive value is empty - this may cause security issues`;
    }
    // Check for placeholder values
    const placeholders = ['your-', 'example', 'replace-me', 'change-me', 'todo', 'xxx', 'yyy'];
    if (placeholders.some(placeholder => value.toLowerCase().includes(placeholder))) {
        return `Value appears to be a placeholder - update before using`;
    }
    return undefined;
}
function isValidEnvFilePattern(pattern) {
    // Reject path traversal attempts
    if (pattern.includes('..')) {
        return false;
    }
    // Reject absolute paths
    if (path.isAbsolute(pattern)) {
        return false;
    }
    // Reject patterns with directory separators (should be filename only)
    if (pattern.includes('/') || pattern.includes('\\')) {
        return false;
    }
    // Validate pattern is a reasonable filename
    if (pattern.length === 0 || pattern.length > 255) {
        return false;
    }
    return true;
}
// Export format helper functions
function exportToJSON(variables) {
    const obj = {};
    variables.forEach(v => {
        obj[v.key] = v.value;
    });
    return JSON.stringify(obj, null, 2);
}
function exportToYAML(variables) {
    let yaml = '';
    variables.forEach(v => {
        // Escape quotes and handle multiline
        const value = v.value.includes('\n') || v.value.includes('"') || v.value.includes("'")
            ? `"${v.value.replace(/"/g, '\\"')}"`
            : v.value;
        yaml += `${v.key}: ${value}\n`;
    });
    return yaml;
}
function exportToCSV(variables) {
    let csv = 'Key,Value,File,Line\n';
    variables.forEach(v => {
        const value = `"${v.value.replace(/"/g, '""')}"`;
        const file = path.basename(v.file);
        csv += `${v.key},${value},${file},${v.line}\n`;
    });
    return csv;
}
function exportToDotEnv(variables) {
    let env = '';
    variables.forEach(v => {
        // Quote values with spaces or special characters
        const needsQuotes = /[\s#"'$]/.test(v.value);
        const value = needsQuotes ? `"${v.value.replace(/"/g, '\\"')}"` : v.value;
        env += `${v.key}=${value}\n`;
    });
    return env;
}
// Create output channel for logging
const outputChannel = vscode.window.createOutputChannel('Env Variable Viewer');
function activate(context) {
    outputChannel.appendLine('Environment Variable Viewer extension is now active!');
    const treeProvider = new EnvVariablesProvider();
    const treeView = vscode.window.createTreeView('envVariablesExplorer', {
        treeDataProvider: treeProvider,
        showCollapseAll: true
    });
    // Set context for when env files are available
    const updateContext = async () => {
        const hasEnvFiles = await hasEnvFilesInWorkspace();
        vscode.commands.executeCommand('setContext', 'envViewer.hasEnvFiles', hasEnvFiles);
        vscode.commands.executeCommand('setContext', 'envViewer.treeViewVisible', hasEnvFiles);
    };
    updateContext();
    // Watch for file changes using VS Code's built-in file system watcher
    const config = vscode.workspace.getConfiguration('envViewer');
    if (config.get('autoRefresh', true)) {
        setupFileWatcher(context, treeProvider, updateContext);
    }
    // Register commands
    const commands = [
        vscode.commands.registerCommand('envViewer.viewVariables', async () => {
            await showEnvVariables(treeProvider);
        }),
        vscode.commands.registerCommand('envViewer.copyVariable', async () => {
            await showEnvVariables(treeProvider);
        }),
        vscode.commands.registerCommand('envViewer.refreshTree', () => {
            treeProvider.refresh();
            updateContext();
        }),
        vscode.commands.registerCommand('envViewer.openFile', async (item) => {
            if (item?.envFile) {
                const doc = await vscode.workspace.openTextDocument(item.envFile.path);
                await vscode.window.showTextDocument(doc);
            }
            else if (item?.envVar) {
                const doc = await vscode.workspace.openTextDocument(item.envVar.file);
                const editor = await vscode.window.showTextDocument(doc);
                const line = item.envVar.line - 1;
                const range = new vscode.Range(line, 0, line, 0);
                editor.selection = new vscode.Selection(range.start, range.end);
                editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
            }
        }),
        vscode.commands.registerCommand('envViewer.copyKey', async (item) => {
            if (item?.envVar) {
                await vscode.env.clipboard.writeText(item.envVar.key);
                vscode.window.showInformationMessage(`Copied key: ${item.envVar.key}`);
            }
        }),
        vscode.commands.registerCommand('envViewer.copyValue', async (item) => {
            if (item?.envVar) {
                await vscode.env.clipboard.writeText(item.envVar.value);
                vscode.window.showInformationMessage(`Copied value for: ${item.envVar.key}`);
            }
        }),
        vscode.commands.registerCommand('envViewer.copyBoth', async (item) => {
            if (item?.envVar) {
                const text = `${item.envVar.key}=${item.envVar.value}`;
                await vscode.env.clipboard.writeText(text);
                // Don't show value in notification if masked
                const displayText = item.envVar.masked
                    ? `${item.envVar.key}=***`
                    : text;
                vscode.window.showInformationMessage(`Copied: ${displayText}`);
            }
        }),
        vscode.commands.registerCommand('envViewer.searchVariables', async () => {
            await searchVariables(treeProvider);
        }),
        vscode.commands.registerCommand('envViewer.toggleQuickPick', async () => {
            await showEnvVariables(treeProvider);
        }),
        vscode.commands.registerCommand('envViewer.sponsor', async () => {
            const sponsorUrl = 'https://buymeacoffee.com/gingerturtle';
            const choice = await vscode.window.showInformationMessage('☕ Enjoying the Environment Variable Viewer?', {
                modal: false,
                detail: 'Your support helps keep this extension free and actively maintained!'
            }, 'Buy Me a Coffee ☕', 'Maybe Later');
            if (choice === 'Buy Me a Coffee ☕') {
                vscode.env.openExternal(vscode.Uri.parse(sponsorUrl));
            }
        }),
        vscode.commands.registerCommand('envViewer.exportVariables', async () => {
            await exportVariables(treeProvider);
        }),
        vscode.commands.registerCommand('envViewer.showValidationWarnings', async () => {
            await showValidationWarnings(treeProvider);
        })
    ];
    // Register tree view click handler
    context.subscriptions.push(treeView.onDidChangeSelection(async (e) => {
        if (e.selection.length > 0) {
            const item = e.selection[0];
            if (item.envVar) {
                // Single click to copy value
                await vscode.env.clipboard.writeText(item.envVar.value);
                vscode.window.showInformationMessage(`Copied value for: ${item.envVar.key}`);
            }
        }
    }));
    context.subscriptions.push(treeView, outputChannel, ...commands);
}
async function hasEnvFilesInWorkspace() {
    if (!vscode.workspace.workspaceFolders) {
        return false;
    }
    const config = vscode.workspace.getConfiguration('envViewer');
    const patterns = config.get('envFilePatterns', ['.env']);
    for (const folder of vscode.workspace.workspaceFolders) {
        for (const pattern of patterns) {
            // Security: Validate pattern to prevent path traversal
            if (!isValidEnvFilePattern(pattern)) {
                continue;
            }
            const envPath = path.resolve(folder.uri.fsPath, pattern);
            // Security: Ensure resolved path is within workspace boundary
            const workspaceRoot = folder.uri.fsPath;
            if (!envPath.startsWith(workspaceRoot + path.sep) && envPath !== workspaceRoot) {
                continue;
            }
            if (fs.existsSync(envPath)) {
                return true;
            }
        }
    }
    return false;
}
function setupFileWatcher(context, treeProvider, updateContext) {
    if (!vscode.workspace.workspaceFolders) {
        return;
    }
    const config = vscode.workspace.getConfiguration('envViewer');
    const patterns = config.get('envFilePatterns', ['.env']);
    // Create file system watcher for .env files
    patterns.forEach(pattern => {
        // Security: Validate pattern to prevent malicious glob patterns
        if (!isValidEnvFilePattern(pattern)) {
            outputChannel.appendLine(`Skipping invalid file watcher pattern: "${pattern}"`);
            return;
        }
        const watchPattern = `**/${pattern}`;
        const watcher = vscode.workspace.createFileSystemWatcher(watchPattern);
        // Fix resource leak: Add watcher and all listeners to subscriptions
        context.subscriptions.push(watcher);
        context.subscriptions.push(watcher.onDidChange(() => {
            treeProvider.refresh();
            updateContext().catch(err => outputChannel.appendLine(`Failed to update context: ${err}`));
        }));
        context.subscriptions.push(watcher.onDidCreate(() => {
            treeProvider.refresh();
            updateContext().catch(err => outputChannel.appendLine(`Failed to update context: ${err}`));
        }));
        context.subscriptions.push(watcher.onDidDelete(() => {
            treeProvider.refresh();
            updateContext().catch(err => outputChannel.appendLine(`Failed to update context: ${err}`));
        }));
    });
}
async function showEnvVariables(treeProvider) {
    try {
        // Load env files first to avoid race condition
        await treeProvider.loadEnvFiles();
        treeProvider.refresh();
        const envFiles = treeProvider.getEnvFiles();
        if (envFiles.length === 0) {
            vscode.window.showErrorMessage('No .env files found in the workspace');
            return;
        }
        const allVariables = [];
        envFiles.forEach(file => {
            allVariables.push(...file.variables);
        });
        if (allVariables.length === 0) {
            vscode.window.showInformationMessage('No environment variables found in .env files');
            return;
        }
        await showQuickPick(allVariables, envFiles, treeProvider);
    }
    catch (error) {
        outputChannel.appendLine(`Error reading .env files: ${error}`);
        vscode.window.showErrorMessage('Error reading .env files. Check the output log for details.');
    }
}
async function showQuickPick(envVariables, envFiles, treeProvider) {
    const config = vscode.workspace.getConfiguration('envViewer');
    const showLineNumbers = config.get('showLineNumbers', true);
    const items = [];
    // Group by file for better organization
    envFiles.forEach(file => {
        if (file.variables.length === 0)
            return;
        // File header
        items.push({
            label: `$(file-code) ${file.name}`,
            description: `${file.variables.length} variables`,
            detail: file.path,
            envVar: { key: '', value: '', line: 0, file: file.path },
            action: 'copyValue',
            kind: vscode.QuickPickItemKind.Separator
        });
        // Variables in this file
        file.variables.forEach(envVar => {
            const lineInfo = showLineNumbers ? ` (L${envVar.line})` : '';
            const displayValue = envVar.masked ? '***' : envVar.value;
            // Main variable item
            items.push({
                label: `$(key) ${envVar.key}${lineInfo}`,
                description: displayValue,
                detail: `Click to copy value • ${file.name}`,
                envVar: envVar,
                action: 'copyValue'
            });
            // Copy options
            items.push({
                label: `  $(clippy) Copy key: ${envVar.key}`,
                description: '',
                detail: 'Copy just the variable name',
                envVar: envVar,
                action: 'copyKey'
            });
            items.push({
                label: `  $(symbol-parameter) Copy as: ${envVar.key}=${displayValue}`,
                description: '',
                detail: 'Copy the full key=value pair',
                envVar: envVar,
                action: 'copyBoth'
            });
        });
        // Add spacing between files
        items.push({
            label: '',
            description: '',
            detail: '',
            envVar: { key: '', value: '', line: 0, file: '' },
            action: 'copyValue',
            kind: vscode.QuickPickItemKind.Separator
        });
    });
    // Remove last separator
    if (items.length > 0 && items[items.length - 1].kind === vscode.QuickPickItemKind.Separator) {
        items.pop();
    }
    const quickPick = vscode.window.createQuickPick();
    quickPick.title = 'Environment Variables';
    quickPick.placeholder = 'Search for environment variables...';
    quickPick.items = items;
    quickPick.matchOnDescription = true;
    quickPick.matchOnDetail = true;
    quickPick.onDidChangeSelection(async (selection) => {
        if (selection.length > 0) {
            const selected = selection[0];
            if (selected.envVar.key) {
                await handleSelection(selected);
            }
            quickPick.hide();
        }
    });
    quickPick.onDidHide(() => {
        quickPick.dispose();
    });
    // Add buttons
    quickPick.buttons = [
        {
            iconPath: new vscode.ThemeIcon('refresh'),
            tooltip: 'Refresh environment variables'
        },
        {
            iconPath: new vscode.ThemeIcon('settings'),
            tooltip: 'Open settings'
        }
    ];
    quickPick.onDidTriggerButton(async (button) => {
        if (button.tooltip === 'Refresh environment variables') {
            quickPick.hide();
            // Reuse existing tree provider instead of creating a new one
            await showEnvVariables(treeProvider);
        }
        else if (button.tooltip === 'Open settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'envViewer');
        }
    });
    quickPick.show();
}
async function searchVariables(treeProvider) {
    const searchTerm = await vscode.window.showInputBox({
        prompt: 'Search environment variables',
        placeHolder: 'Enter search term...'
    });
    if (!searchTerm) {
        return;
    }
    // Load env files first to avoid race condition
    await treeProvider.loadEnvFiles();
    treeProvider.refresh();
    const envFiles = treeProvider.getEnvFiles();
    const allVariables = [];
    envFiles.forEach(file => {
        allVariables.push(...file.variables);
    });
    const filtered = allVariables.filter(variable => variable.key.toLowerCase().includes(searchTerm.toLowerCase()) ||
        variable.value.toLowerCase().includes(searchTerm.toLowerCase()));
    if (filtered.length === 0) {
        vscode.window.showInformationMessage(`No variables found matching "${searchTerm}"`);
        return;
    }
    // Create a temporary quick pick with filtered results
    const items = filtered.map(envVar => ({
        label: `$(key) ${envVar.key}`,
        description: envVar.masked ? '***' : envVar.value,
        detail: `${path.basename(envVar.file)} (Line ${envVar.line})`,
        envVar: envVar,
        action: 'copyValue'
    }));
    const quickPick = vscode.window.createQuickPick();
    quickPick.title = `Search Results: "${searchTerm}" (${filtered.length} found)`;
    quickPick.items = items;
    quickPick.onDidChangeSelection(async (selection) => {
        if (selection.length > 0) {
            const selected = selection[0];
            await handleSelection(selected);
            quickPick.hide();
        }
    });
    quickPick.onDidHide(() => {
        quickPick.dispose();
    });
    quickPick.show();
}
async function handleSelection(item) {
    const { envVar, action } = item;
    let textToCopy = '';
    let message = '';
    switch (action) {
        case 'copyKey':
            textToCopy = envVar.key;
            message = `Copied key: ${envVar.key}`;
            break;
        case 'copyValue':
            textToCopy = envVar.value;
            message = `Copied value for: ${envVar.key}`;
            break;
        case 'copyBoth':
            textToCopy = `${envVar.key}=${envVar.value}`;
            // Don't show value in notification if masked
            const displayValue = envVar.masked ? '***' : envVar.value;
            message = `Copied: ${envVar.key}=${displayValue}`;
            break;
    }
    await vscode.env.clipboard.writeText(textToCopy);
    vscode.window.showInformationMessage(message);
}
async function showValidationWarnings(treeProvider) {
    try {
        await treeProvider.loadEnvFiles();
        const envFiles = treeProvider.getEnvFiles();
        if (envFiles.length === 0) {
            vscode.window.showInformationMessage('No .env files found in the workspace');
            return;
        }
        // Collect all variables with warnings
        const variablesWithWarnings = [];
        envFiles.forEach(file => {
            file.variables.forEach(variable => {
                if (variable.validationWarning) {
                    variablesWithWarnings.push(variable);
                }
            });
        });
        if (variablesWithWarnings.length === 0) {
            vscode.window.showInformationMessage('✅ No validation warnings found - all variables look good!');
            return;
        }
        // Show warnings in quick pick
        const items = variablesWithWarnings.map(envVar => ({
            label: `$(warning) ${envVar.key}`,
            description: envVar.masked ? '***' : envVar.value,
            detail: `${envVar.validationWarning} (${path.basename(envVar.file)}:${envVar.line})`,
            envVar: envVar,
            action: 'copyValue'
        }));
        const quickPick = vscode.window.createQuickPick();
        quickPick.title = `⚠️ Validation Warnings (${variablesWithWarnings.length} found)`;
        quickPick.placeholder = 'Select a variable to view or fix...';
        quickPick.items = items;
        quickPick.onDidChangeSelection(async (selection) => {
            if (selection.length > 0) {
                const selected = selection[0];
                // Open the file at the line
                const doc = await vscode.workspace.openTextDocument(selected.envVar.file);
                const editor = await vscode.window.showTextDocument(doc);
                const line = selected.envVar.line - 1;
                const range = new vscode.Range(line, 0, line, 1000);
                editor.selection = new vscode.Selection(range.start, range.end);
                editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
                quickPick.hide();
            }
        });
        quickPick.onDidHide(() => {
            quickPick.dispose();
        });
        quickPick.show();
    }
    catch (error) {
        outputChannel.appendLine(`Error showing validation warnings: ${error}`);
        vscode.window.showErrorMessage('Error showing validation warnings. Check the output log for details.');
    }
}
async function exportVariables(treeProvider) {
    try {
        // Load env files
        await treeProvider.loadEnvFiles();
        const envFiles = treeProvider.getEnvFiles();
        if (envFiles.length === 0) {
            vscode.window.showErrorMessage('No .env files found in the workspace');
            return;
        }
        // Collect all variables
        const allVariables = [];
        envFiles.forEach(file => {
            allVariables.push(...file.variables);
        });
        if (allVariables.length === 0) {
            vscode.window.showInformationMessage('No environment variables found to export');
            return;
        }
        // Ask user for export format
        const format = await vscode.window.showQuickPick([
            { label: 'JSON', description: 'Export as JSON object', value: 'json' },
            { label: 'YAML', description: 'Export as YAML format', value: 'yaml' },
            { label: 'CSV', description: 'Export as CSV with metadata', value: 'csv' },
            { label: '.env', description: 'Export as .env file', value: 'env' }
        ], {
            placeHolder: 'Select export format'
        });
        if (!format) {
            return;
        }
        // Generate export content
        let content;
        let defaultFileName;
        switch (format.value) {
            case 'json':
                content = exportToJSON(allVariables);
                defaultFileName = 'env-export.json';
                break;
            case 'yaml':
                content = exportToYAML(allVariables);
                defaultFileName = 'env-export.yaml';
                break;
            case 'csv':
                content = exportToCSV(allVariables);
                defaultFileName = 'env-export.csv';
                break;
            case 'env':
                content = exportToDotEnv(allVariables);
                defaultFileName = 'exported.env';
                break;
            default:
                return;
        }
        // Show save dialog
        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(defaultFileName),
            filters: {
                'All Files': ['*']
            }
        });
        if (uri) {
            await vscode.workspace.fs.writeFile(uri, Buffer.from(content, 'utf8'));
            const choice = await vscode.window.showInformationMessage(`Exported ${allVariables.length} variables to ${path.basename(uri.fsPath)}`, 'Open File');
            if (choice === 'Open File') {
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc);
            }
        }
    }
    catch (error) {
        outputChannel.appendLine(`Error exporting variables: ${error}`);
        vscode.window.showErrorMessage('Error exporting variables. Check the output log for details.');
    }
}
function deactivate() { }
//# sourceMappingURL=extension.js.map