"""Only task lifecycle and owned exports; processing stays in subtitle_tool.py."""
import asyncio
import zipfile
from . import captions, engine


class Jobs:
    def __init__(self):
        self.items = {}
        self.tasks = {}
        self.serial = asyncio.Semaphore(1)

    def public(self, job):
        return {key: job[key] for key in ('id', 'session', 'index', 'mode', 'state', 'log', 'error', 'files')}

    def busy(self, session):
        return any(j['session'] == session and j['state'] in {'queued', 'running'} for j in self.items.values())

    def start(self, identifier, workspace, request):
        if len(self.items) >= 30:
            raise ValueError('任务历史最多 30 条，请保存成果并清空工作区')
        if self.busy(workspace['id']):
            raise ValueError('这一组视频还有任务进行中，请先等待或取消')
        if request.index >= len(workspace['videos']):
            raise ValueError('所选视频不存在')
        engine.executable()
        if request.mode == 'transcribe':
            engine.model()
        elif not (workspace['root'] / 'input' / f'caption-{request.index}.srt').is_file():
            raise ValueError('先生成或导入字幕，再导出视频')
        out = workspace['root'] / 'output' / identifier
        out.mkdir()
        job = {'id': identifier, 'session': workspace['id'], 'index': request.index, 'mode': request.mode,
               'state': 'queued', 'log': '', 'error': None, 'files': [], 'out': out}
        self.items[identifier] = job
        self.tasks[identifier] = asyncio.create_task(self.run(job, workspace, request))
        return self.public(job)

    async def run(self, job, workspace, request):
        try:
            async with self.serial:
                job['state'] = 'running'
                source = workspace['videos'][request.index]['path']
                caption = workspace['root'] / 'input' / f'caption-{request.index}.srt'
                if request.mode == 'transcribe':
                    output = job['out'] / 'subtitles.srt'
                    args = [str(source), '--transcribe-only', '--device', 'cpu', '--language', request.language,
                            '--model', str(engine.model()), '--local-only', '--output', str(output)]
                else:
                    # Snapshot the edited document, so later editing cannot change a running export.
                    text = captions.document(caption.read_text(encoding='utf-8'))['text']
                    subtitle = job['out'] / 'subtitles.srt'
                    subtitle.write_text(text, encoding='utf-8')
                    output = job['out'] / ('video.' + request.container)
                    args = [str(source), '--srt', str(subtitle), '--mode', request.mode,
                            '--font', request.font, '--font-size', str(request.font_size),
                            '--local-only', '--output', str(output)]
                await engine.call(args, job['out'], lambda data: job.update(log=(job['log'] + data)[-65536:]))
                if not output.is_file() or output.stat().st_size == 0:
                    raise ValueError('引擎未生成有效成果')
                if request.mode == 'transcribe':
                    parsed = captions.document(output.read_text(encoding='utf-8-sig'))
                    output.write_text(parsed['text'], encoding='utf-8')
                    caption.write_text(parsed['text'], encoding='utf-8')
                files = [p for p in job['out'].iterdir() if p.is_file()]
                if sum(p.stat().st_size for p in files) > 512 * 1024 * 1024:
                    raise ValueError('单次成果超过 512 MB，请使用更短视频')
                with zipfile.ZipFile(job['out'] / 'export.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                    for path in files:
                        archive.write(path, path.name)
                job['files'] = [{'name': p.name, 'size': p.stat().st_size} for p in files]
                job['state'] = 'done'
        except asyncio.CancelledError:
            job['state'] = 'cancelled'
            raise
        except (ValueError, OSError, RuntimeError, asyncio.TimeoutError) as error:
            job['state'] = 'failed'
            job['error'] = str(error) or '处理超过 30 分钟，任务已停止'

    async def cancel(self, identifier):
        task = self.tasks.get(identifier)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.public(self.items[identifier])

    async def delete(self, session):
        for identifier in [key for key, job in self.items.items() if job['session'] == session]:
            await self.cancel(identifier)
            del self.items[identifier]
            self.tasks.pop(identifier, None)

    async def close(self):
        for identifier in list(self.tasks):
            await self.cancel(identifier)
