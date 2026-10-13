// Real frozen WebView2 window, with original CLI export and normal WM_CLOSE cleanup.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import { spawn, spawnSync, execFileSync } from 'node:child_process';

if (process.platform !== 'win32' || process.env.GITHUB_ACTIONS !== 'true') throw Error('CI-only native acceptance');
await fs.mkdir('evidence', { recursive: true });
execFileSync('python', ['-c', 'from pathlib import Path; import sys; sys.path.insert(0,"tests"); from fixtures import fixtures; fixtures(Path("evidence"))']);
const probe = net.createServer();
await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
const port = probe.address().port;
await new Promise(resolve => probe.close(resolve));
const receiptFile = path.resolve('evidence/native-startup.json');
const env = { ...process.env, LAIN42_DESKTOP_SMOKE: 'true', LAIN42_DESKTOP_DEBUG_PORT: String(port),
  LAIN42_DESKTOP_RECEIPT: receiptFile, PYINSTALLER_RESET_ENVIRONMENT: '1', HF_HUB_OFFLINE: '1' };
delete env.LAIN42_SUBTITLE_SOURCE_ENGINE;
const binary = path.resolve(process.argv[2]);
const child = spawn(binary, [], { env, stdio: ['ignore', 'pipe', 'pipe'] });
let output = '', browser;
child.stdout.on('data', data => output += data);
child.stderr.on('data', data => output += data);
try {
  let receipt;
  for (let i = 0; i < 120; i++) {
    assert.equal(child.exitCode, null, output);
    try {
      receipt = JSON.parse(await fs.readFile(receiptFile, 'utf8'));
      browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
      break;
    } catch { await new Promise(resolve => setTimeout(resolve, 500)); }
  }
  assert(browser && receipt, 'Actual WebView2 startup failed: ' + output);
  for(let i=0;i<100;i++) {
    try {receipt=JSON.parse(await fs.readFile(receiptFile,'utf8'));if(receipt.native_icon_applied===true)break;} catch {}
    await new Promise(r=>setTimeout(r,100));
  }
  assert.equal(receipt.native_icon_applied,true,'actual native window must use the packaged Lyco icon');
  const page = browser.contexts()[0].pages()[0];
  assert(page, 'Missing native page');
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.waitForURL(receipt.url);
  await page.getByLabel('选择视频', { exact: true }).setInputFiles('evidence/original.mp4');
  await page.getByLabel('选择已有 SRT', { exact: true }).setInputFiles('evidence/original.srt');
  await page.getByRole('button', { name: '打开工作区', exact: true }).click();
  const editor = page.getByLabel('SRT 时间轴与字幕正文', { exact: true });
  await editor.waitFor();
  await page.waitForFunction(() => document.querySelector('video')?.readyState > 0);
  await editor.fill((await editor.inputValue()).replace('NEW CAPTION', 'EDITED IN NATIVE WINDOW'));
  await page.getByRole('button', { name: '保存修改', exact: true }).click();
  await page.getByRole('button', { name: '已保存', exact: true }).waitFor();
  await page.waitForFunction(() => [...document.querySelector('video').textTracks]
    .some(track => [...(track.cues || [])].some(cue => cue.text.includes('EDITED IN NATIVE WINDOW'))));
  await page.getByLabel('字幕方式', { exact: true }).selectOption('soft');
  await page.getByRole('button', { name: '导出视频', exact: true }).click();
  const download = page.getByRole('link', { name: '下载全部成果', exact: true });
  await download.waitFor({ timeout: 60000 });
  // Fetch within the actual native page: its HttpOnly cookie isn't in CDP's APIRequestContext.
  const exported = await download.evaluate(async link => {
    const response = await fetch(link.getAttribute('href'));
    const bytes = new Uint8Array(await response.arrayBuffer());
    let data = '';
    for (const byte of bytes) data += String.fromCharCode(byte);
    return { status: response.status, data: btoa(data) };
  });
  assert.equal(exported.status, 200);
  const zip = path.resolve('evidence/native-export.zip');
  await fs.writeFile(zip, Buffer.from(exported.data, 'base64'));
  execFileSync('python', ['-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert set(z.namelist())=={"video.mp4","subtitles.srt"}; assert b"EDITED IN NATIVE WINDOW" in z.read("subtitles.srt"); assert len(z.read("video.mp4"))>1000', zip]);
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await page.screenshot({ path: 'evidence/windows-native.png', fullPage: true });
  await fs.access(receipt.workspace_root);
  const close = spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-File',
    'tests/close-native-window.ps1', '-Binary', binary], { encoding: 'utf8' });
  assert.equal(close.status, 0, close.stderr);
  for (let i = 0; i < 100 && child.exitCode === null; i++) await new Promise(resolve => setTimeout(resolve, 200));
  assert.equal(child.exitCode, 0, 'Normal close failed: ' + output);
  await assert.rejects(fs.access(receipt.workspace_root), 'Private workspace survived normal close');
  await assert.rejects(fetch(receipt.url), 'Server survived normal close');
  await fs.writeFile('evidence/windows-native.json', JSON.stringify({ commit: process.env.GITHUB_SHA,
    native_webview2: true, native_icon_applied: true, real_video_preview: true, edited_real_vtt: true,
    original_frozen_cli_export: true, real_zip_contents: true, normal_close: true,
    workspace_removed: true, port_closed: true, pageErrors: errors,
    media_source: 'CI host, not bundled', distributable: false }, null, 2));
} finally {
  if (child.exitCode === null) child.kill();
  if (browser) await browser.close().catch(() => {});
  await fs.writeFile('evidence/windows-native.log', output);
  if (child.exitCode !== 0) console.error(output);
}
