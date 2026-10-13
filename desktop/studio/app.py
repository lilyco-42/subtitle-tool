"""Loopback HTTP boundary for the original subtitle CLI."""
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import captions, engine
from .jobs import Jobs
from .workspaces import MAX_FILE, MAX_TOTAL, Workspaces


class JobInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: UUID
    index: int = Field(ge=0, le=2)
    mode: Literal['transcribe', 'soft', 'hard']
    language: str = Field(default='auto', pattern=r'^(auto|[a-z]{2,3})$')
    container: Literal['mp4', 'mkv'] = 'mp4'
    font: Literal['Arial', 'Microsoft YaHei', 'DejaVu Sans'] = 'Arial'
    font_size: int = Field(default=22, ge=8, le=96)


class CaptionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(max_length=captions.MAX_SRT)


def create_app():
    workspaces, jobs = Workspaces(), Jobs()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await jobs.close()
            workspaces.close()

    app = FastAPI(title='Lain42 Subtitle Studio', lifespan=lifespan, docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.state.workspaces, app.state.jobs = workspaces, jobs
    token = secrets.token_urlsafe(32)
    frontend = engine.base() / 'frontend'

    @app.middleware('http')
    async def local_only(request, call_next):
        if request.url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            return JSONResponse({'detail': '只允许本机访问'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
            return JSONResponse({'detail': '跨站请求被拒绝'}, status_code=403)
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': '无效请求大小'}, status_code=400)
        limit = MAX_TOTAL + 1024 * 1024 if request.url.path == '/api/workspaces' else 8 * 1024 * 1024
        if length < 0 or length > limit:
            return JSONResponse({'detail': '请求数据过大'}, status_code=413)
        cookie = f'subtitle_session_{request.url.port or 80}'
        if request.url.path.startswith('/api/') and not secrets.compare_digest(request.cookies.get(cookie, ''), token):
            return JSONResponse({'detail': '请从本机应用窗口访问'}, status_code=403)
        response = await call_next(request)
        if request.url.path == '/':
            response.set_cookie(cookie, token, httponly=True, samesite='strict')
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; media-src 'self' blob:; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)[:1000]}, status_code=400)

    @app.get('/')
    def index():
        return FileResponse(frontend / 'index.html')

    @app.get('/api/capabilities')
    def capabilities():
        try:
            engine.executable()
            installed = True
        except ValueError:
            installed = False
        try:
            engine.model()
            model = True
        except ValueError:
            model = False
        return {'engine': installed, 'model': model, 'max_file': MAX_FILE, 'max_total': MAX_TOTAL,
                'model_device': 'cpu', 'temporary': True}

    @app.post('/api/workspaces')
    async def upload(videos: list[UploadFile] = File(...), subtitle: UploadFile | None = File(None)):
        identifier = str(uuid4())
        item = workspaces.new(identifier)
        total = 0
        try:
            if not 1 <= len(videos) <= 3:
                raise ValueError('一次选择 1–3 个视频')
            for index, video in enumerate(videos):
                name = (video.filename or '').replace('\\', '/').split('/')[-1][:160]
                suffix = Path(name).suffix.lower()
                if suffix not in {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}:
                    raise ValueError('请选择 MP4、MKV、MOV、AVI、WebM 或 M4V')
                path = item['root'] / 'input' / f'video-{index}{suffix}'
                size = 0
                with path.open('wb') as stream:
                    while chunk := await video.read(65536):
                        size += len(chunk)
                        total += len(chunk)
                        if size > MAX_FILE or total > MAX_TOTAL:
                            raise ValueError('单视频最多 256 MB，一组最多 512 MB')
                        stream.write(chunk)
                if size == 0:
                    raise ValueError('视频文件为空')
                item['videos'].append({'index': index, 'name': name, 'size': size, 'path': path})
            if subtitle:
                if Path(subtitle.filename or '').suffix.lower() != '.srt':
                    raise ValueError('请导入 UTF-8 的 SRT 字幕')
                data = await subtitle.read(captions.MAX_SRT + 1)
                if len(data) > captions.MAX_SRT:
                    raise ValueError('字幕最多 2 MB')
                parsed = captions.document(data.decode('utf-8-sig'))
                for index in range(len(videos)):
                    (item['root'] / 'input' / f'caption-{index}.srt').write_text(parsed['text'], encoding='utf-8')
            return {'id': identifier, 'videos': [{key: v[key] for key in ('index', 'name', 'size')} for v in item['videos']]}
        except UnicodeError as error:
            workspaces.delete(identifier)
            raise ValueError('字幕须为 UTF-8 编码') from error
        except BaseException:
            workspaces.delete(identifier)
            raise
        finally:
            for video in videos:
                await video.close()
            if subtitle:
                await subtitle.close()

    def video_for(identifier, index):
        item = workspaces.get(str(identifier))
        if index < 0 or index >= len(item['videos']):
            raise HTTPException(404, '视频不存在')
        return item, item['videos'][index]

    @app.get('/api/workspaces/{identifier}/videos/{index}')
    def video(identifier: UUID, index: int):
        _, item = video_for(identifier, index)
        return FileResponse(item['path'], content_disposition_type='inline')

    @app.get('/api/workspaces/{identifier}/captions/{index}')
    def get_caption(identifier: UUID, index: int):
        item, _ = video_for(identifier, index)
        path = item['root'] / 'input' / f'caption-{index}.srt'
        return captions.document(path.read_text(encoding='utf-8')) if path.is_file() else {'text': '', 'count': 0, 'cues': []}

    @app.put('/api/workspaces/{identifier}/captions/{index}')
    def put_caption(identifier: UUID, index: int, request: CaptionInput):
        item, _ = video_for(identifier, index)
        if jobs.busy(str(identifier)):
            raise ValueError('任务执行中，请等待或取消后修改字幕')
        parsed = captions.document(request.text)
        (item['root'] / 'input' / f'caption-{index}.srt').write_text(parsed['text'], encoding='utf-8')
        return parsed

    @app.get('/api/workspaces/{identifier}/captions/{index}/vtt')
    def vtt(identifier: UUID, index: int):
        document = get_caption(identifier, index)
        return Response(document.get('vtt', 'WEBVTT\n\n'), media_type='text/vtt')

    @app.get('/api/workspaces/{identifier}/captions/{index}/srt')
    def srt_file(identifier: UUID, index: int):
        document = get_caption(identifier, index)
        if not document['count']:
            raise HTTPException(404, '请先生成或导入字幕')
        return Response(document['text'], media_type='application/x-subrip',
                        headers={'Content-Disposition': 'attachment; filename="subtitles.srt"'})

    @app.delete('/api/workspaces/{identifier}')
    async def delete(identifier: UUID):
        await jobs.delete(str(identifier))
        workspaces.delete(str(identifier))
        return {'deleted': True}

    @app.post('/api/jobs')
    async def start(request: JobInput):
        return jobs.start(str(uuid4()), workspaces.get(str(request.session)), request)

    def get_job(identifier):
        item = jobs.items.get(str(identifier))
        if not item:
            raise HTTPException(404, '任务不存在或已清空')
        return item

    @app.get('/api/jobs/{identifier}')
    def status(identifier: UUID):
        return jobs.public(get_job(identifier))

    @app.post('/api/jobs/{identifier}/cancel')
    async def cancel(identifier: UUID):
        get_job(identifier)
        return await jobs.cancel(str(identifier))

    @app.get('/api/jobs/{identifier}/files/{name}')
    def download(identifier: UUID, name: str):
        job = get_job(identifier)
        if job['state'] != 'done' or name not in {'export.zip'} | {item['name'] for item in job['files']}:
            raise HTTPException(404, '结果尚未完成或文件不存在')
        return FileResponse(job['out'] / name, filename=name,
                            content_disposition_type='inline' if name.endswith('.mp4') else 'attachment')

    if frontend.is_dir():
        app.mount('/assets', StaticFiles(directory=frontend), name='assets')
    return app
