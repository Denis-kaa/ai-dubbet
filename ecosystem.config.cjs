const fs = require("fs");
const path = require("path");

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const env = {};
  const content = fs.readFileSync(filePath, "utf8");

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line || line.startsWith("#")) {
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    let value = line.slice(separatorIndex + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    env[key] = value;
  }

  return env;
}

const repoRoot = __dirname;
const envFromFile = loadEnvFile(path.join(repoRoot, ".env"));
const venvPython = path.join(repoRoot, ".venv", "bin", "python");
const pythonBin = fs.existsSync(venvPython) ? venvPython : "python3";

module.exports = {
  apps: [
    {
      name: "ai-dubber-api",
      cwd: repoRoot,
      script: pythonBin,
      args: "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      kill_timeout: 10000,
      env: {
        ...process.env,
        ...envFromFile,
        PYTHONPATH: repoRoot,
      },
    },
    {
      name: "ai-dubber-worker",
      cwd: repoRoot,
      script: pythonBin,
      args: "-m celery -A backend.workers.celery_app worker -l info -Q video_processing -c 2",
      interpreter: "none",
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      kill_timeout: 10000,
      env: {
        ...process.env,
        ...envFromFile,
        PYTHONPATH: repoRoot,
      },
    },
  ],
};
