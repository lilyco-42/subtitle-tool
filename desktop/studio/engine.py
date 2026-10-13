"""Original CLI process boundary; fixed executable, arguments and owned trees."""
import asyncio
import os
import hashlib
import json
from pathlib import Path
import signal
import sys


def base():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def executable():
    suffix = '.exe' if os.name == 'nt' else ''
    path = base() / 'bin' / 'subtitle-engine' / ('subtitle-engine' + suffix)
    if path.is_file():
        return [str(path)]
    if os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('LAIN42_SUBTITLE_SOURCE_ENGINE') == 'true':
        return [sys.executable, str(Path(__file__).resolve().parents[2] / 'subtitle_tool.py')]
    raise ValueError('字幕引擎未打包，当前不是可交付的完整桌面版')


def model():
    path = base() / 'models' / 'tiny'
    if not (path / 'manifest.json').is_file():
        raise ValueError('本地模型尚未打包；仍可导入已有 SRT 并导出视频')
    try:
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        names = {'model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt', 'README.md', 'WHISPER-LICENSE'}
        if manifest['model'] != 'Systran/faster-whisper-tiny' or manifest['revision'] != 'd90ca5fe260221311c53c58e660288d3deb8d356' or set(manifest['files']) != names:
            raise ValueError('本地模型来源不符')
        for name, info in manifest['files'].items():
            data = (path / name).read_bytes()
            if len(data) != info['size'] or hashlib.sha256(data).hexdigest() != info['sha256']:
                raise ValueError('本地模型文件损坏，请重新获取完整包')
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('本地模型不完整，请重新获取完整包') from error
    return path


async def call(arguments, folder, log):
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {'start_new_session': True}
    # The worker is a separate frozen executable, not another invocation of this shell.
    environment = dict(os.environ)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(*executable(), '--wait-for-controller', *arguments,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=folder, env=environment, **kwargs))
    process = None
    owned = None
    reader = None

    async def read():
        while data := await process.stdout.read(4096):
            log(data.decode('utf-8', errors='replace'))

    try:
        # Cancellation during CreateProcess must not lose the eventual PID.
        process = await asyncio.shield(spawn)
        if os.name == 'nt':
            from .windows_process_job import WindowsProcessJob
            owned = WindowsProcessJob(process.pid)
        process.stdin.write(b'ready\n')
        await process.stdin.drain()
        process.stdin.close()
        reader = asyncio.create_task(read())
        code = await asyncio.wait_for(process.wait(), timeout=1800)
        await reader
        if code:
            raise ValueError('原字幕引擎处理失败，请查看任务日志')
    finally:
        if process is None:
            process = await spawn
        try:
            if owned:
                await owned.stop()
            elif os.name != 'nt':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.returncode is None:
                process.kill()
            await process.wait()
        finally:
            if reader and not reader.done():
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
