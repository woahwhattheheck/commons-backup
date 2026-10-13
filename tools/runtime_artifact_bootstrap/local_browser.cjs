'use strict';

const fs = require('node:fs/promises');
const { constants } = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { fileURLToPath } = require('node:url');

async function localTarget(target) {
  if (typeof target !== 'string' || !target.trim()) {
    throw new Error('An explicit local product URL is required.');
  }
  const url = new URL(target);
  if (url.username || url.password) throw new Error('Use a local URL without embedded credentials.');
  if (url.protocol === 'file:') {
    if (url.hostname || !(await fs.stat(fileURLToPath(url))).isFile()) {
      throw new Error('The file URL must name an existing local file.');
    }
  } else if (!['http:', 'https:'].includes(url.protocol) ||
             !['127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw new Error('Use a numeric loopback HTTP(S) URL or an explicit local file URL.');
  }
  return url;
}

async function taskDirectory(tempRoot) {
  if (tempRoot !== undefined && (typeof tempRoot !== 'string' || !path.isAbsolute(tempRoot))) {
    throw new Error('tempRoot must be an absolute directory path.');
  }
  const parents = tempRoot === undefined
    ? [...new Set([os.tmpdir(), '/dev/shm'])]
    : [tempRoot];
  const failures = [];
  for (const parent of parents) {
    let directory;
    try {
      directory = await fs.mkdtemp(path.join(parent, 'commons-local-browser-'));
      await fs.chmod(directory, 0o700);
      const probe = path.join(directory, '.write-probe');
      await fs.writeFile(probe, Buffer.alloc(4096), { flag: 'wx', mode: 0o600 });
      await fs.unlink(probe);
      return directory;
    } catch (error) {
      if (directory) await fs.rm(directory, { recursive: true, force: true });
      failures.push(`${parent}: ${error.code || error.message}`);
    }
  }
  throw new Error(`No writable browser temporary directory (${failures.join('; ')}). Supply tempRoot.`);
}

/** Open one explicit local product in a disposable, independently owned context. */
async function openLocalBrowser({ target, executablePath, tempRoot } = {}) {
  const url = await localTarget(target);
  if (typeof executablePath !== 'string' || !path.isAbsolute(executablePath)) {
    throw new Error('executablePath must name an already available Chromium executable by absolute path.');
  }
  if (!(await fs.stat(executablePath)).isFile()) throw new Error('Chromium executable is not a file.');
  await fs.access(executablePath, constants.X_OK);
  const moduleRoot = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
  let playwright;
  try {
    playwright = require(moduleRoot ? path.join(moduleRoot, 'playwright') : 'playwright');
  } catch (error) {
    throw new Error('An installed Playwright package is required; no runtime was downloaded.', { cause: error });
  }
  const temporaryDirectory = await taskDirectory(tempRoot);
  let context;
  let closing;
  const close = () => closing ||= (async () => {
    try {
      if (context) await context.close();
    } finally {
      await fs.rm(temporaryDirectory, { recursive: true, force: true });
    }
  })();
  try {
    const profile = path.join(temporaryDirectory, 'profile');
    const artifacts = path.join(temporaryDirectory, 'artifacts');
    const downloads = path.join(temporaryDirectory, 'downloads');
    for (const directory of [profile, artifacts, downloads]) await fs.mkdir(directory, { mode: 0o700 });
    context = await playwright.chromium.launchPersistentContext(profile, {
      executablePath,
      headless: true,
      artifactsDir: artifacts,
      downloadsPath: downloads,
      env: { ...process.env, TMPDIR: temporaryDirectory },
      ignoreDefaultArgs: ['--enable-unsafe-swiftshader'],
      args: ['--no-zygote', '--single-process', '--disable-gpu', '--disable-software-rasterizer', '--disable-webgl'],
    });
    const page = context.pages()[0] || await context.newPage();
    const response = await page.goto(url.href, { waitUntil: 'domcontentloaded' });
    if (response && response.status() >= 400) {
      throw new Error(`Local product returned HTTP ${response.status()}.`);
    }
    return { page, context, temporaryDirectory, close };
  } catch (error) {
    try {
      await close();
    } catch (cleanupError) {
      throw new AggregateError([error, cleanupError], 'Local browser failed and its temporary directory needs cleanup.');
    }
    throw error;
  }
}

module.exports = { openLocalBrowser };
