#!/usr/bin/env node
'use strict';

// Manual source selection only: no module linking or evaluation.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash } = require('node:crypto');
const { fileURLToPath, pathToFileURL } = require('node:url');
const { TextDecoder } = require('node:util');

const SCHEMA = 'commons.javascript_import_sources/v1';
const DEFAULTS = Object.freeze({
  max_files: 256,
  max_bytes: 8 * 1024 * 1024,
  max_file_bytes: 1024 * 1024,
  max_imports: 4096,
});
const BOUNDARIES = [
  'Only static evaluation-phase requests for .js/.mjs with no import attributes are followed.',
  '.js is explicitly parsed as ESM; package.json type, exports, imports and conditions are not resolved.',
  'Dynamic import(), require(), runtime file access and external packages are not evaluated or discovered.',
  'Query/fragment variants retain request URLs but share one canonical file-byte identity.',
  'Explicit assets are opaque bytes; their presence does not establish runtime completeness.',
  'Reads are bounded observations with before/after file checks, not an atomic filesystem snapshot.',
];

class ImportMapError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'ImportMapError';
    this.code = code;
  }
}

function inside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === '' || (!path.isAbsolute(relative) &&
    relative !== '..' && !relative.startsWith('..' + path.sep));
}

function displayPath(root, candidate) {
  return path.relative(root, candidate).split(path.sep).join('/');
}

function explicitPath(value, kind) {
  if (typeof value !== 'string' || !value || value.includes('\\') ||
      value.includes('\0') || value.startsWith('/') ||
      value.split('/').some(part => !part || part === '.' || part === '..')) {
    throw new ImportMapError('INVALID_PATH', kind + ' must be a relative path without traversal');
  }
  if (kind === 'entry' && !/\.(?:mjs|js)$/.test(value)) {
    throw new ImportMapError('INVALID_ENTRY', 'entry must end in .mjs or .js and is parsed as ESM');
  }
  return value;
}

function normalizeOptions(options) {
  if (!options || typeof options.root !== 'string' || !options.root) {
    throw new ImportMapError('INVALID_ROOT', 'an explicit existing root directory is required');
  }
  if (!Array.isArray(options.entries) || !options.entries.length) {
    throw new ImportMapError('INVALID_ENTRY', 'at least one entry is required');
  }
  const limits = {};
  for (const [key, fallback] of Object.entries(DEFAULTS)) {
    const value = options[key] === undefined ? fallback : options[key];
    if (!Number.isSafeInteger(value) || value <= 0) {
      throw new ImportMapError('INVALID_LIMIT', key + ' must be a positive safe integer');
    }
    limits[key] = value;
  }
  if (options.assets !== undefined && !Array.isArray(options.assets)) {
    throw new ImportMapError('INVALID_ASSET', 'assets must be an array of relative paths');
  }
  return {
    root: options.root,
    entries: [...new Set(options.entries.map(value => explicitPath(value, 'entry')))],
    assets: [...new Set((options.assets || []).map(value => explicitPath(value, 'asset')))],
    limits,
  };
}

function errorRow(error, extra) {
  return {
    ...extra,
    code: error instanceof ImportMapError ? error.code : (error.code || error.name || 'Error'),
    detail: error instanceof ImportMapError ? error.message : (error.name || 'Error'),
  };
}

function identity(relative, raw) {
  return {
    path: relative,
    bytes: raw.length,
    blob_sha: createHash('sha1').update('blob ' + raw.length + '\0').update(raw).digest('hex'),
    sha256: createHash('sha256').update(raw).digest('hex'),
  };
}

class SourceMap {
  constructor(options) {
    if (typeof vm.SourceTextModule !== 'function' ||
        !('moduleRequests' in vm.SourceTextModule.prototype)) {
      throw new ImportMapError('PARSER_UNAVAILABLE',
        'use Node 24.4 or later with --experimental-vm-modules and moduleRequests support');
    }
    this.options = normalizeOptions(options);
    this.root = fs.realpathSync(path.resolve(this.options.root));
    if (!fs.statSync(this.root).isDirectory()) {
      throw new ImportMapError('INVALID_ROOT', 'root must be an existing directory');
    }
    this.limits = this.options.limits;
    this.files = [];
    this.imports = [];
    this.errors = [];
    this.assets = [];
    this.assetErrors = [];
    this.skippedSources = [];
    this.skippedAssets = [];
    this.limitsReached = new Set();
    this.queue = [];
    this.scheduled = new Set();
    this.cache = new Map();
    this.attemptedCanonical = new Set();
    this.aliases = [];
    this.bytesRead = 0;
    this.readAttempts = 0;
    this.queueIndex = 0;
    this.interruptedSource = null;
    this.interruptedAsset = null;
    this.unrecordedRequests = [];
    this.unfollowedLocal = 0;
    this.unfollowedExternal = 0;
    this.context = vm.createContext(Object.create(null));
  }

  schedule(relative) {
    if (!this.scheduled.has(relative)) {
      this.scheduled.add(relative);
      this.queue.push(relative);
    }
  }

  canonical(relative) {
    const lexical = path.resolve(this.root, relative);
    if (!inside(this.root, lexical)) {
      throw new ImportMapError('OUTSIDE_ROOT', 'local path is outside the explicit root');
    }
    const resolved = fs.realpathSync(lexical);
    if (!inside(this.root, resolved)) {
      throw new ImportMapError('OUTSIDE_ROOT', 'resolved local path is outside the explicit root');
    }
    return { absolute: resolved, relative: displayPath(this.root, resolved) };
  }

  readFile(target, kind) {
    const flags = fs.constants.O_RDONLY | (fs.constants.O_NONBLOCK || 0) |
      (fs.constants.O_NOFOLLOW || 0);
    const descriptor = fs.openSync(target.absolute, flags);
    try {
      const before = fs.fstatSync(descriptor, { bigint: true });
      if (!before.isFile()) {
        throw new ImportMapError('NOT_REGULAR_FILE', kind + ' is not a regular file');
      }
      if (before.size > BigInt(this.limits.max_file_bytes)) {
        this.limitsReached.add('max_file_bytes');
        return { skipped: { path: target.relative, reason: 'max_file_bytes', bytes: before.size.toString() } };
      }
      if (before.size > BigInt(this.limits.max_bytes - this.bytesRead)) {
        this.limitsReached.add('max_bytes');
        return { interrupted: true };
      }
      const size = Number(before.size);
      const raw = Buffer.alloc(size);
      let offset = 0;
      while (offset < size) {
        const count = fs.readSync(descriptor, raw, offset, size - offset, offset);
        if (!count) break;
        offset += count;
        this.bytesRead += count;
      }
      const after = fs.fstatSync(descriptor, { bigint: true });
      if (offset !== size || before.dev !== after.dev || before.ino !== after.ino ||
          before.size !== after.size || before.mtimeNs !== after.mtimeNs ||
          before.ctimeNs !== after.ctimeNs) {
        throw new ImportMapError('FILE_CHANGED', kind + ' changed while reading');
      }
      return { raw };
    } finally {
      fs.closeSync(descriptor);
    }
  }

  importRequest(origin, request) {
    const row = {
      source: origin,
      specifier: request.specifier,
      phase: request.phase,
      attributes: Object.fromEntries(Object.entries(request.attributes)),
    };
    this.imports.push(row);
    const specifier = request.specifier;
    const isLocal = specifier.startsWith('./') || specifier.startsWith('../') ||
      specifier.startsWith('/') || specifier.startsWith('file:');
    if (!isLocal) {
      row.resolution = specifier.startsWith('node:') ? 'builtin' :
        (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(specifier) ? 'external_url' : 'package_or_bare');
      this.unfollowedExternal += 1;
      return;
    }
    try {
      const url = new URL(specifier, pathToFileURL(path.join(this.root, origin)));
      if (url.protocol !== 'file:') {
        throw new ImportMapError('INVALID_LOCAL_SPECIFIER', 'local request is not a file URL');
      }
      row.module_url = url.href;
      const absolute = fileURLToPath(url);
      if (!inside(this.root, absolute)) {
        throw new ImportMapError('OUTSIDE_ROOT', 'local request is outside the explicit root');
      }
      row.target = displayPath(this.root, absolute);
      const extension = path.extname(absolute);
      if (request.phase !== 'evaluation' || Object.keys(request.attributes).length ||
          (extension !== '.mjs' && extension !== '.js')) {
        row.resolution = 'local_not_followed';
        row.reason = request.phase !== 'evaluation' ? 'non_evaluation_phase' :
          (Object.keys(request.attributes).length ? 'import_attributes' : 'unsupported_extension');
        this.unfollowedLocal += 1;
        return;
      }
      row.resolution = 'local_source';
      this.schedule(row.target);
    } catch (error) {
      row.resolution = 'error';
      this.errors.push(errorRow(error, { stage: 'resolve_import', path: origin, specifier }));
    }
  }

  scanSources() {
    for (const entry of this.options.entries) this.schedule(entry);
    while (this.queueIndex < this.queue.length) {
      const requested = this.queue[this.queueIndex];
      let target;
      try {
        target = this.canonical(requested);
      } catch (error) {
        if (this.readAttempts >= this.limits.max_files) {
          this.limitsReached.add('max_files');
          break;
        }
        this.readAttempts += 1;
        this.queueIndex += 1;
        this.errors.push(errorRow(error, { stage: 'resolve_source', path: requested }));
        continue;
      }
      if (target.relative !== requested) {
        this.aliases.push({ path: requested, canonical_path: target.relative });
      }
      if (this.attemptedCanonical.has(target.relative)) {
        this.queueIndex += 1;
        continue;
      }
      if (this.readAttempts >= this.limits.max_files) {
        this.limitsReached.add('max_files');
        break;
      }
      this.readAttempts += 1;
      this.queueIndex += 1;
      this.attemptedCanonical.add(target.relative);
      try {
        const read = this.readFile(target, 'source');
        if (read.skipped) {
          this.skippedSources.push(read.skipped);
          continue;
        }
        if (read.interrupted) {
          this.interruptedSource = requested;
          break;
        }
        const row = { ...identity(target.relative, read.raw), parsed_as: 'esm', parsed: false };
        this.files.push(row);
        this.cache.set(target.relative, row);
        let code;
        try {
          code = new TextDecoder('utf-8', { fatal: true }).decode(read.raw);
        } catch {
          throw new ImportMapError('INVALID_UTF8', 'source is not valid UTF-8');
        }
        // Construction parses only. Do not link, instantiate, evaluate or access a namespace.
        const parsed = new vm.SourceTextModule(code, {
          context: this.context,
          identifier: pathToFileURL(target.absolute).href,
        });
        row.parsed = true;
        row.module_status = parsed.status;
        const requests = parsed.moduleRequests;
        row.static_requests = requests.length;
        const retained = Math.min(requests.length, this.limits.max_imports - this.imports.length);
        row.requests_recorded = retained;
        for (let index = 0; index < retained; index += 1) {
          this.importRequest(target.relative, requests[index]);
        }
        if (retained !== requests.length) {
          this.limitsReached.add('max_imports');
          this.unrecordedRequests.push({
            path: target.relative,
            observed: requests.length,
            recorded: retained,
            omitted: requests.length - retained,
          });
          break;
        }
      } catch (error) {
        this.errors.push(errorRow(error, { stage: 'read_or_parse_source', path: target.relative }));
      }
    }
  }

  scanAssets() {
    const pending = [...this.options.assets];
    let index = 0;
    const observed = new Map();
    while (index < pending.length) {
      const requested = pending[index];
      let target;
      try {
        target = this.canonical(requested);
      } catch (error) {
        if (this.readAttempts >= this.limits.max_files) {
          this.limitsReached.add('max_files');
          break;
        }
        this.readAttempts += 1;
        index += 1;
        this.assetErrors.push(errorRow(error, { stage: 'resolve_asset', path: requested }));
        continue;
      }
      const retained = this.cache.get(target.relative) || observed.get(target.relative);
      if (retained) {
        this.assets.push({
          path: requested,
          canonical_path: target.relative,
          bytes: retained.bytes,
          blob_sha: retained.blob_sha,
          sha256: retained.sha256,
          reused_source: this.cache.has(target.relative),
          reused_asset: observed.has(target.relative),
        });
        index += 1;
        continue;
      }
      if (this.readAttempts >= this.limits.max_files) {
        this.limitsReached.add('max_files');
        break;
      }
      this.readAttempts += 1;
      index += 1;
      try {
        const read = this.readFile(target, 'asset');
        if (read.skipped) {
          this.skippedAssets.push({ ...read.skipped, requested_path: requested });
          continue;
        }
        if (read.interrupted) {
          this.interruptedAsset = requested;
          break;
        }
        const row = identity(target.relative, read.raw);
        observed.set(target.relative, row);
        this.assets.push({
          ...row,
          path: requested,
          canonical_path: target.relative,
          reused_source: false,
          reused_asset: false,
        });
      } catch (error) {
        this.assetErrors.push(errorRow(error, { stage: 'read_asset', path: requested }));
      }
    }
    return pending.slice(index);
  }

  run() {
    this.scanSources();
    const sourceBytes = this.bytesRead;
    const pendingAssets = this.scanAssets();
    const pendingSources = this.queue.slice(this.queueIndex);
    const sourcesFinished = !pendingSources.length && !this.interruptedSource &&
      !this.unrecordedRequests.length && !this.skippedSources.length &&
      !this.errors.length && !this.unfollowedLocal;
    const assetsFinished = !pendingAssets.length && !this.interruptedAsset &&
      !this.skippedAssets.length && !this.assetErrors.length;
    return {
      schema: SCHEMA,
      root: this.root,
      entries: this.options.entries,
      files: this.files,
      imports: this.imports,
      errors: this.errors,
      requested_assets: this.options.assets,
      assets: this.assets,
      asset_errors: this.assetErrors,
      coverage: {
        scope: 'static local ESM requests and explicit assets under the local root',
        parser: 'node:vm.SourceTextModule.moduleRequests',
        node_version: process.version,
        source_scan_finished: sourcesFinished,
        explicit_assets_finished: assetsFinished,
        scan_finished: sourcesFinished && assetsFinished,
        runtime_completeness: 'not_evaluated',
        module_evaluation: false,
        source_files_read: this.files.length,
        source_bytes_read: sourceBytes,
        asset_bytes_read: this.bytesRead - sourceBytes,
        total_bytes_read: this.bytesRead,
        file_read_attempts: this.readAttempts,
        imports_recorded: this.imports.length,
        unfollowed_external_requests: this.unfollowedExternal,
        unfollowed_local_requests: this.unfollowedLocal,
        limits: this.limits,
        limits_reached: [...this.limitsReached].sort(),
        pending_sources: pendingSources,
        pending_assets: pendingAssets,
        interrupted_source: this.interruptedSource,
        interrupted_asset: this.interruptedAsset,
        skipped_sources: this.skippedSources,
        skipped_assets: this.skippedAssets,
        unrecorded_static_requests: this.unrecordedRequests,
        source_aliases: this.aliases,
        boundaries: BOUNDARIES,
      },
    };
  }
}

function mapSources(options) {
  return new SourceMap(options).run();
}

const USAGE = 'Usage: node --experimental-vm-modules host/javascript_import_sources.cjs ' +
  '--root DIR --entry RELATIVE.mjs [--entry RELATIVE.js] [--asset RELATIVE] ' +
  '[--max-files N] [--max-bytes N] [--max-file-bytes N] [--max-imports N]';

function parseArgs(argv) {
  const options = { entries: [], assets: [] };
  const names = {
    '--root': 'root', '--entry': 'entries', '--asset': 'assets',
    '--max-files': 'max_files', '--max-bytes': 'max_bytes',
    '--max-file-bytes': 'max_file_bytes', '--max-imports': 'max_imports',
  };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    const key = names[flag];
    if (!key || index + 1 >= argv.length) throw new Error('unknown option or missing value: ' + flag);
    const value = argv[++index];
    if (key === 'entries' || key === 'assets') options[key].push(value);
    else if (key === 'root') options[key] = value;
    else {
      if (!/^[1-9][0-9]*$/.test(value) || !Number.isSafeInteger(Number(value))) {
        throw new Error(flag + ' requires a positive safe integer');
      }
      options[key] = Number(value);
    }
  }
  if (!options.root || !options.entries.length) throw new Error('--root and --entry are required');
  return options;
}

function main(argv) {
  if (argv.length === 1 && (argv[0] === '--help' || argv[0] === '-h')) {
    process.stdout.write(USAGE + '\n');
    return 0;
  }
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    process.stderr.write('javascript import sources: ' + error.message + '\n' + USAGE + '\n');
    return 2;
  }
  let result;
  try {
    result = mapSources(options);
  } catch (error) {
    result = { schema: SCHEMA, error: 'IMPORT_MAP_INPUT', ...errorRow(error, {}) };
    process.stdout.write(JSON.stringify(result) + '\n');
    process.stderr.write('javascript import sources: input or parser unavailable; see JSON\n');
    return 1;
  }
  process.stdout.write(JSON.stringify(result) + '\n');
  if (result.errors.length || result.asset_errors.length) {
    process.stderr.write('javascript import sources: ' + result.errors.length +
      ' source errors and ' + result.asset_errors.length + ' asset errors; see JSON\n');
    return 1;
  }
  return 0;
}

module.exports = { ImportMapError, mapSources, main };
if (require.main === module) process.exitCode = main(process.argv.slice(2));
