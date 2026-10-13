/* @flow */

import {fs} from './util';
import path from 'path';

export default async function findFiles (...input: string[]): Promise<string[]> {
  const found = [];
  for (const item of input) {
    try {
      await collectFiles(item, found);
    } catch ( err ) {
      console.error(`Ignore files from ${item}: ${err}`);
    }
  }
  return found;
}

async function collectFiles (fileOrDir: string, collected: string[]): Promise<string[]> {
  const stat = await fs.statAsync(fileOrDir);
  if (stat.isDirectory()) {
    for (const item of await fs.readdirAsync(fileOrDir)) {
      await collectFiles(path.join(fileOrDir, item), collected);
    }
  }
  else if (isJavaScriptFile(fileOrDir)) {
    await addJavaScriptFile(fileOrDir, collected);
  }
  return collected;
}

async function addJavaScriptFile (filename: string, collected: string[]): Promise<void> {
  if (isFlowDefinitionFile(filename)) {
    const runtimeFile = filename.replace(/\.flow$/, '');
    const runtimeIndex = collected.indexOf(runtimeFile);
    if (runtimeIndex !== -1) {
      collected.splice(runtimeIndex, 1);
    }
    if (collected.indexOf(filename) === -1) {
      collected.push(filename);
    }
    return;
  }

  if (await hasFlowDefinitionFile(filename)) {
    await addJavaScriptFile(`${filename}.flow`, collected);
    return;
  }
  else if (collected.indexOf(filename) === -1) {
    collected.push(filename);
  }
}

function isJavaScriptFile (filename: string): boolean {
  return /\.js(x|m)?$/.test(filename) || isFlowDefinitionFile(filename);
}

function isFlowDefinitionFile (filename: string): boolean {
  return /\.js\.flow$/.test(filename);
}

async function hasFlowDefinitionFile (filename: string): Promise<boolean> {
  const definitionFilename = `${filename}.flow`;
  if (!isFlowDefinitionFile(definitionFilename)) {
    return false;
  }
  try {
    const stat = await fs.statAsync(definitionFilename);
    return stat.isFile();
  }
  catch (e) {
    return false;
  }
}
