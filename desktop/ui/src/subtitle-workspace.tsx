import { useEffect, useRef, useState } from "react";
import { Captions, Download, Film, LockKeyhole, Moon, Play, Save, Square, Sun, Trash2, Upload } from "lucide-react";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./components/ui/card";
import { useSubtitles } from "./use-subtitles";

const names: Record<string, string> = { queued: "等待处理", running: "处理中", done: "已完成", failed: "失败", cancelled: "已取消" };
export function SubtitleWorkspace() {
  const state = useSubtitles();
  const video = useRef<HTMLVideoElement>(null);
  const [dark, setDark] = useState(false);
  const [videos, setVideos] = useState<File[]>([]);
  const [subtitle, setSubtitle] = useState<File | null>(null);
  const [language, setLanguage] = useState("auto");
  const [mode, setMode] = useState<"soft" | "hard">("hard");
  const [container, setContainer] = useState("mp4");
  const [font, setFont] = useState("Arial");
  const [fontSize, setFontSize] = useState(22);
  const [all, setAll] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const current = state.workspace?.videos[state.index];
  const options = { language, container, font, font_size: fontSize };
  useEffect(() => setVideoError(false), [state.workspace?.id, state.index]);

  function theme() {
    document.documentElement.classList.toggle("dark", !dark); setDark(!dark);
  }
  return <div className="subtitle-shell">
    <header className="subtitle-top"><div className="subtitle-brand"><Captions aria-hidden="true"/><div><h1>字幕工坊</h1><small>Lain42 · Subtitle Studio</small></div></div>
      <div className="subtitle-top-actions"><Badge variant="secondary"><LockKeyhole size={13}/> 本机处理</Badge><Button variant="ghost" size="icon" onClick={theme} aria-label={dark ? "切换浅色主题" : "切换深色主题"}>{dark ? <Sun/> : <Moon/>}</Button></div>
    </header>
    <main className="subtitle-layout">
      <aside className="subtitle-sidebar"><small>你的工作流</small><h2>把视频，变成能读懂的故事。</h2><ol className="subtitle-steps"><li>选择视频</li><li>生成或导入字幕</li><li>校对与预览</li><li>保存作品</li></ol>
        <p>原 faster-whisper 与 FFmpeg 引擎。文件不上传网站，不使用 AI 账户额度。</p>
        {state.capabilities && !state.capabilities.engine && <p role="status" className="subtitle-warning">当前引擎未打包，不是完整发行版。</p>}
        {state.workspace && <><h3>当前视频</h3><nav aria-label="批量视频">{state.workspace.videos.map(item => <Button key={item.index} variant={state.index === item.index ? "secondary" : "ghost"} onClick={() => void state.select(item.index)} disabled={state.busy} className="subtitle-file"><Film/><span>{item.name}</span></Button>)}</nav>
          <Button variant="outline" onClick={() => void state.clear()} disabled={state.busy}><Trash2/> 清空文件与历史</Button></>}
        <small>每次 1–3 个视频；单个最多 256 MB，总量 512 MB。关闭应用会移除临时文件，请先保存成果。</small>
      </aside>
      <section className="subtitle-main">
        <div className="subtitle-heading"><div><small>为视频加上清晰的表达</small><h2>{current ? current.name : "从第一个视频开始"}</h2></div>{state.document.count > 0 && <Badge variant="secondary">{state.document.count} 段字幕</Badge>}</div>
        {state.error && <p role="alert" className="subtitle-error">{state.error}</p>}
        {state.notice && <p role="status" className="subtitle-notice">{state.notice}</p>}
        {!state.workspace ? <Card><CardHeader><CardTitle>导入素材</CardTitle></CardHeader><CardContent className="subtitle-stack">
          <label className="subtitle-upload"><Upload/><strong>选择本机视频</strong><input aria-label="选择视频" type="file" accept=".mp4,.mkv,.mov,.avi,.webm,.m4v" multiple disabled={state.busy} onChange={e => setVideos(Array.from(e.target.files || []))}/><span>{videos.length ? videos.map(v => v.name).join("、") : "MP4 / MKV / MOV / AVI / WebM / M4V"}</span></label>
          <label>已有字幕（可选）<input type="file" accept=".srt" aria-label="选择已有 SRT" disabled={state.busy} onChange={e => setSubtitle(e.target.files?.[0] || null)}/></label>
          <small>同一 SRT 会先应用于这一组视频；加载后可逐个校对修改。没有字幕时使用本地模型转录。</small>
          <Button disabled={state.busy || !videos.length} onClick={() => void state.open(videos, subtitle)}>{state.busy ? "正在加载…" : "打开工作区"}</Button>
        </CardContent></Card> : <>
          <Card><CardHeader><CardTitle>视频与字幕预览</CardTitle></CardHeader><CardContent>
            <video ref={video} aria-label="当前视频预览" key={`${state.workspace.id}-${state.index}`} controls preload="metadata" className="subtitle-video" onError={() => setVideoError(true)}>
              <source src={`/api/workspaces/${state.workspace.id}/videos/${state.index}`} onError={() => setVideoError(true)}/>
              <track key={state.revision} src={`${state.captionBase}/vtt?r=${state.revision}`} kind="subtitles" srcLang={language === "auto" ? "zh" : language} label="校对字幕" default/>
            </video><small>预览使用已保存的字幕。播放器字幕按钮可开关显示。</small>
            {videoError && <p role="status">浏览器不支持这份源视频的编码或容器；仍可转录与导出，在本机播放器核对成果。</p>}
            <div className="subtitle-cues" aria-label="字幕片段">{state.document.cues.map((cue, index) => <button key={index} onClick={() => { if (video.current) video.current.currentTime = cue.start; }}><time>{cue.start.toFixed(1)}s</time><span>{cue.text}</span></button>)}</div>
          </CardContent></Card>
          <Card><CardHeader className="subtitle-editor-heading"><CardTitle>校对字幕</CardTitle><Button variant="outline" onClick={() => void state.save()} disabled={state.busy || !state.dirty || !state.text.trim()}><Save/> {state.dirty ? "保存修改" : "已保存"}</Button></CardHeader><CardContent>
            <label className="subtitle-sr-label" htmlFor="subtitle-document">SRT 时间轴与字幕正文</label><textarea id="subtitle-document" className="subtitle-editor" value={state.text} onChange={e => state.setText(e.target.value)} disabled={state.busy} spellCheck={false} placeholder={"1\n00:00:00,000 --> 00:00:02,000\n在这里写下你的字幕"}/>
            <small>保留序号与起止时间，片段之间留空行。保存时会验证格式；不静默丢弃错误片段。</small>
          </CardContent></Card>
        </>}
      </section>
      <aside className="subtitle-controls"><Card><CardHeader><CardTitle>生成字幕</CardTitle></CardHeader><CardContent className="subtitle-stack">
        <label>语音语言<select aria-label="语音语言" value={language} onChange={e => setLanguage(e.target.value)} disabled={state.busy}>{[["auto", "自动识别"], ["zh", "中文"], ["en", "英语"], ["ja", "日语"], ["ko", "韩语"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <small>CPU 本地转录。字幕可能有识别错误，导出前请校对。</small>
        {state.capabilities && !state.capabilities.model && <p role="status" className="subtitle-warning">本地模型尚未打包，可先导入已有 SRT。</p>}
        <Button variant="secondary" disabled={!state.workspace || state.busy || !state.capabilities?.model || !state.capabilities.engine} onClick={() => void state.run("transcribe", options, all)}><Captions/> 生成字幕</Button>
      </CardContent></Card>
        <Card><CardHeader><CardTitle>保存作品</CardTitle></CardHeader><CardContent className="subtitle-stack">
          <label>字幕方式<select aria-label="字幕方式" value={mode} onChange={e => setMode(e.target.value as "soft" | "hard")} disabled={state.busy}><option value="hard">烧录字幕 · 画面内显示</option><option value="soft">软字幕 · 播放器可开关</option></select></label>
          <small>{mode === "hard" ? "重新编码视频，适合手机播放和剪辑；字幕无法关闭。" : "保持音视频编码，播放器需支持字幕轨道。剪辑软件可能不读取软字幕。"}</small>
          <label>输出容器<select aria-label="输出容器" value={container} onChange={e => setContainer(e.target.value)} disabled={state.busy}><option value="mp4">MP4</option><option value="mkv">MKV</option></select></label>
          {mode === "hard" && <><label>字幕字体<select aria-label="字幕字体" value={font} onChange={e => setFont(e.target.value)} disabled={state.busy}><option>Arial</option><option>Microsoft YaHei</option><option>DejaVu Sans</option></select></label><label>字号<input aria-label="字幕字号" type="number" min={8} max={96} value={fontSize} onChange={e => setFontSize(Number(e.target.value))} disabled={state.busy}/></label><small>字体须已安装；缺字或回退需要在导出视频中核对。</small></>}
          <label className="subtitle-check"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} disabled={state.busy}/> 按顺序处理这一组全部视频</label>
          <Button disabled={!state.workspace || !state.document.count || state.busy || state.dirty || !state.capabilities?.engine} onClick={() => void state.run(mode, options, all)}><Play/> 导出视频</Button>
          {state.workspace && state.document.count > 0 && <a href={`${state.captionBase}/srt`} download className="subtitle-download"><Download size={16}/> 下载当前 SRT</a>}
          {state.job && <><Badge variant="secondary">{names[state.job.state] || state.job.state}</Badge>{["running", "queued"].includes(state.job.state) && <Button variant="outline" onClick={() => void state.cancel()}><Square/> 取消任务</Button>}<details><summary>任务日志</summary><pre className="subtitle-log">{state.job.log || "任务等待开始"}</pre></details></>}
        </CardContent></Card>
        {state.history.length > 0 && <Card><CardHeader><CardTitle>成果与历史</CardTitle></CardHeader><CardContent><div className="subtitle-history">{state.history.map(item => <article key={item.id}><strong>{state.workspace?.videos[item.index]?.name}</strong><small>{names[item.state]} · {item.mode === "transcribe" ? "生成字幕" : item.mode === "hard" ? "烧录字幕" : "软字幕"}</small>{item.state === "done" && <><a href={`/api/jobs/${item.id}/files/export.zip`} download className="subtitle-download"><Download size={16}/> 下载全部成果</a>{item.files.map(file => <a key={file.name} href={`/api/jobs/${item.id}/files/${encodeURIComponent(file.name)}`} download>{file.name}</a>)}</>}{item.error && <p>{item.error}</p>}</article>)}</div></CardContent></Card>}
      </aside>
    </main>
  </div>;
}
