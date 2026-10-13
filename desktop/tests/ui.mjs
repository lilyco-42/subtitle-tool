import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve('evidence');
fs.mkdirSync(root, { recursive: true });
execFileSync('python', ['-c', 'from pathlib import Path; import sys; sys.path.insert(0,"tests"); from fixtures import fixtures,speech; fixtures(Path("evidence")); speech(Path("evidence"))']);
fs.copyFileSync(path.join(root, 'own-speech.mp4'), path.join(root, 'second.mp4'));
const browser = await chromium.launch();
const evidence = [];
try {
  for (const width of [1440, 1028, 768, 390, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 960 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8057/');
    await page.getByLabel('选择视频', { exact: true }).setInputFiles([path.join(root, 'original.mp4'), path.join(root, 'second.mp4')]);
    await page.getByLabel('选择已有 SRT', { exact: true }).setInputFiles(path.join(root, 'original.srt'));
    await page.getByRole('button', { name: '打开工作区', exact: true }).click();
    const editor = page.getByLabel('SRT 时间轴与字幕正文', { exact: true });
    await editor.waitFor();
    await page.waitForFunction(() => document.querySelector('video')?.readyState > 0);
    assert.match(await editor.inputValue(), /NEW CAPTION/);
    await editor.fill((await editor.inputValue()).replace('NEW CAPTION', 'EDITED IN GUI'));
    await page.getByRole('button', { name: '保存修改', exact: true }).click();
    await page.getByRole('button', { name: '已保存', exact: true }).waitFor();
    await page.waitForFunction(() => [...document.querySelector('video').textTracks]
      .some(track => [...(track.cues || [])].some(cue => cue.text.includes('EDITED IN GUI'))));
    await page.getByLabel('字幕方式', { exact: true }).selectOption('soft');
    await page.getByText('按顺序处理这一组全部视频', { exact: true }).click();
    await page.getByRole('button', { name: '导出视频', exact: true }).click();
    await page.waitForFunction(() => document.querySelectorAll('.subtitle-history article').length === 2,
                               null, { timeout: 60000 });
    const download = page.waitForEvent('download');
    await page.getByRole('link', { name: '下载全部成果', exact: true }).first().click();
    const result = await download;
    const archive = path.join(root, `ui-${width}.zip`);
    await result.saveAs(archive);
    execFileSync('python', ['-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert set(z.namelist())=={"subtitles.srt","video.mp4"}; assert b"NEW CAPTION" in z.read("subtitles.srt"); assert len(z.read("video.mp4"))>1000', archive]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    assert.equal(overflow, false, `Horizontal overflow at ${width}`);
    if (width === 1440) {
      await page.getByRole('button', { name: 'second.mp4', exact: true }).click();
      await page.getByText('按顺序处理这一组全部视频', { exact: true }).click();
      await page.getByLabel('语音语言', { exact: true }).selectOption('en');
      page.once('dialog', dialog => dialog.accept());
      await page.getByRole('button', { name: '生成字幕', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.subtitle-history article').length === 3,
                                 null, { timeout: 120000 });
      assert.match((await editor.inputValue()).toLowerCase(), /subtitle/);
    }
    assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(root, `workbench-${width}.png`), fullPage: true });
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '清空文件与历史', exact: true }).click();
    await page.getByRole('button', { name: '打开工作区', exact: true }).waitFor();
    assert.equal(await page.locator('.subtitle-history article').count(), 0);
    evidence.push({ width, uploaded_two_own_videos: true, edited_and_real_vtt: true,
      original_cli_batch_soft_exports: true, actual_zip_content: true, clear_history: true,
      actual_local_cpu_transcription: width === 1440,
      horizontal_overflow: false, pageErrors: errors });
    await context.close();
  }
} finally {
  await browser.close();
  fs.writeFileSync(path.join(root, 'browser.json'), JSON.stringify({ commit: process.env.GITHUB_SHA, layouts: evidence }, null, 2));
}
