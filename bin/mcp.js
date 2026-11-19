#!/usr/bin/env node

/**
 * Cross-platform stdio launcher for Skill Vault read-only MCP server (scripts/mcp_server.py).
 */

const { spawn } = require('child_process');
const path = require('path');

const scriptPath = path.join(__dirname, '..', 'scripts', 'mcp_server.py');
const candidates = process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];
const extraArgs = process.argv.slice(2);

function runWith(idx) {
  if (idx >= candidates.length) {
    console.error('[Skill Vault MCP Error] Python 3 was not found on PATH.');
    process.exit(1);
  }
  const cmd = candidates[idx];
  const cmdArgs = cmd === 'py' ? ['-3', scriptPath, ...extraArgs] : [scriptPath, ...extraArgs];
  const child = spawn(cmd, cmdArgs, { stdio: 'inherit' });

  child.on('error', (err) => {
    if (err && err.code === 'ENOENT') {
      runWith(idx + 1);
      return;
    }
    console.error(`[Skill Vault MCP Error] ${err.message}`);
    process.exit(1);
  });

  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });
}

runWith(0);
