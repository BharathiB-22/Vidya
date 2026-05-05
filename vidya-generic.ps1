# ==============================================================================
# vidya-generic.ps1
# One-time Claude Code machine bootstrap for Vidya development.
# Run once per machine before any Vidya project work. Safe to re-run.
# Owner: Srinivas / Fidelitus Corp
# ==============================================================================

Write-Host ""
Write-Host "VIDYA - GENERIC MACHINE BOOTSTRAP" -ForegroundColor Cyan
Write-Host "Run once per machine. Safe to re-run." -ForegroundColor Cyan
Write-Host ""

# 1. Prerequisites
Write-Host "[ 1/7 ] Checking prerequisites..." -ForegroundColor Yellow
$missing = @()

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += "Node.js - https://nodejs.org" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { $missing += "npm - comes with Node.js" }
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { $missing += "Claude CLI - npm install -g @anthropic-ai/claude-code" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $missing += "Git - https://git-scm.com" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += "Python 3.12 - https://python.org" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { $missing += "Docker - https://docker.com" }

if ($missing.Count -gt 0) {
    Write-Host "Missing prerequisites:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Node, npm, Claude CLI, Git, Python, Docker all present." -ForegroundColor Green

# 2. cc-status-line
Write-Host ""
Write-Host "[ 2/7 ] Installing cc-status-line..." -ForegroundColor Yellow
Write-Host "Shows context percent, model, cost, and clock." -ForegroundColor DarkGray

npx cc-status-line@latest --install 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "cc-status-line installed." -ForegroundColor Green
} else {
    Write-Host "Run manually if needed: npx cc-status-line@latest --install" -ForegroundColor Yellow
}

# 3. Global MCP servers
Write-Host ""
Write-Host "[ 3/7 ] Installing global MCP servers..." -ForegroundColor Yellow

$mcpPackages = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking"
)

foreach ($pkg in $mcpPackages) {
    Write-Host "Installing $pkg" -ForegroundColor DarkGray
    npm install -g $pkg 2>$null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installed $pkg" -ForegroundColor Green
    } else {
        Write-Host "Install manually: npm install -g $pkg" -ForegroundColor Red
    }
}

$claudeDir = "$env:USERPROFILE\.claude"
if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir | Out-Null
}

$npmGlobalRoot = (npm root -g 2>$null).Trim()

$mcpJson = @"
{
  "mcpServers": {
    "filesystem": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-filesystem\\dist\\index.js", "C:\\"]
    },
    "memory": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-memory\\dist\\index.js"]
    },
    "sequential-thinking": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-sequential-thinking\\dist\\index.js"]
    }
  }
}
"@

Set-Content -Path "$claudeDir\.mcp.json" -Value $mcpJson -Encoding UTF8
Write-Host "Written: $claudeDir\.mcp.json" -ForegroundColor Green

# 4. Global CLAUDE.md
Write-Host ""
Write-Host "[ 4/7 ] Writing ~/.claude/CLAUDE.md..." -ForegroundColor Yellow

$claudeMd = @"
# ~/.claude/CLAUDE.md - Global Rules for All Projects
# Owner: Srinivas / Fidelitus Corp
# Project CLAUDE.md extends these rules. Never contradict these rules.

## Model Tiers

Task type: Boilerplate, config, CRUD, JSON, renaming
Model: Haiku

Task type: Real coding, APIs, debugging, Docker, docs
Model: Sonnet

Task type: Failed twice on Sonnet, hard architecture
Model: Opus

Default model is Sonnet.
Use Haiku for mechanical work.
Use Opus only as last resort.

## Context Window

- Watch context percentage in the status bar.
- At 50 percent: finish current unit, clear session, start a new session.
- Never use compact.
- One session equals one module and one file scope.

## Superpowers Workflow

1. superpowers brainstorm - clarify, approaches, spec document
2. superpowers write plan - convert spec to implementation plan
3. superpowers execute plan - use sub-agents in isolated context windows

Sub-agents should handle one task and one file, then report summary only.

## Tool Policy

context7:
Use for any library or API to prevent hallucinated method names.

sequential-thinking:
Use for architecture and complex debugging.

memory MCP:
Use to persist decisions, schema, and open questions.

filesystem MCP:
Use to read files. Never paste entire files into chat.

context-mode:
Use for large outputs and context savings when available.

## PDCA

Plan, present, approval, do, check, act.
No scope creep.
Every deviation means stop and re-plan.

## Git

- Never commit to main.
- Commit format: [TASK-XXX] verb: what changed
- Show git diff before every commit.

## Paste Discipline

Paste only the function relevant to the task.
Use filesystem MCP for full files.

## AI - Humans Decide

Vidya principle: AI advises, humans decide.
Never implement autonomous grade, penalty, or rejection logic.
Always require a human ratification step.
"@

Set-Content -Path "$claudeDir\CLAUDE.md" -Value $claudeMd -Encoding UTF8
Write-Host "Written: $claudeDir\CLAUDE.md" -ForegroundColor Green

# 5. settings.json
Write-Host ""
Write-Host "[ 5/7 ] Writing ~/.claude/settings.json..." -ForegroundColor Yellow

$settingsJson = @"
{
  "defaultModel": "claude-sonnet-4-6",
  "autoApprove": false,
  "theme": "dark",
  "statusLine": {
    "line1": "model|context_pct|session_cost|session_clock",
    "line2": "git_branch|git_worktree"
  }
}
"@

Set-Content -Path "$claudeDir\settings.json" -Value $settingsJson -Encoding UTF8
Write-Host "Written: $claudeDir\settings.json" -ForegroundColor Green

# 6. Python toolchain check
Write-Host ""
Write-Host "[ 6/7 ] Checking Python toolchain for Vidya backend..." -ForegroundColor Yellow

$pyTools = @("pip", "uvicorn", "celery")

foreach ($t in $pyTools) {
    if (Get-Command $t -ErrorAction SilentlyContinue) {
        Write-Host "$t present." -ForegroundColor Green
    } else {
        Write-Host "$t not found. Install via: pip install $t" -ForegroundColor Yellow
    }
}

# 7. Manual steps
Write-Host ""
Write-Host "[ 7/7 ] Manual steps inside Claude Code:" -ForegroundColor Yellow
Write-Host ""
Write-Host "Type /plugin and install each at USER scope:" -ForegroundColor White
Write-Host "  superpowers      - brainstorm, plan, execute workflow" -ForegroundColor Cyan
Write-Host "  code-simplifier  - refactor helper" -ForegroundColor Cyan
Write-Host "  context7         - live API docs" -ForegroundColor Cyan
Write-Host "  context-mode     - context savings if available" -ForegroundColor Cyan
Write-Host ""
Write-Host "VIDYA GENERIC BOOTSTRAP COMPLETE" -ForegroundColor Green
Write-Host "Next: cd to Vidya project root and run vidya-project.ps1" -ForegroundColor Green
Write-Host ""