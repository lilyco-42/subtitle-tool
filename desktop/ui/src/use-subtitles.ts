import { useCallback, useEffect, useRef, useState } from "react";

export type Workspace = { id: string; videos: { index: number; name: string; size: number }[] };
export type Cue = { start: number; end: number; text: string };
export type Document = { text: string; count: number; cues: Cue[] };
export type Job = { id: string; index: number; mode: string; state: string; error: string | null; log: string; files: { name: string; size: number }[] };
type Capabilities = { engine: boolean; model: boolean; max_file: number; max_total: number };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: "same-origin" });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "请求无效，请核对输入");
  return result as T;
}

export function useSubtitles() {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [index, setIndex] = useState(0);
  const [document, setDocument] = useState<Document>({ text: "", count: 0, cues: [] });
  const [text, setText] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [history, setHistory] = useState<Job[]>([]);
  const epoch = useRef(0);
  const live = useRef(true);
  const dirty = text !== document.text;
  const captionBase = workspace ? `/api/workspaces/${workspace.id}/captions/${index}` : "";

  useEffect(() => {
    live.current = true;
    api<Capabilities>("/api/capabilities").then(setCapabilities).catch(e => setError(String(e.message)));
    return () => { live.current = false; epoch.current++; };
  }, []);

  const reload = useCallback(async (id: string, selected: number) => {
    const version = ++epoch.current;
    const next = await api<Document>(`/api/workspaces/${id}/captions/${selected}`);
    if (live.current && version === epoch.current) {
      setDocument(next); setText(next.text); setRevision(r => r + 1);
      return true;
    }
    return false;
  }, []);

  async function open(videos: File[], subtitle: File | null) {
    if (!videos.length || videos.length > 3) { setError("请选择 1–3 个视频"); return; }
    if (workspace) { setError("请保存成果并清空旧工作区，再选择新文件"); return; }
    setError(""); setNotice(""); setBusy(true);
    try {
      const body = new FormData();
      videos.forEach(video => body.append("videos", video));
      if (subtitle) body.append("subtitle", subtitle);
      const next = await api<Workspace>("/api/workspaces", { method: "POST", body });
      setWorkspace(next); setIndex(0); setJob(null); setHistory([]);
      await reload(next.id, 0);
      setNotice("视频已加载，文件留在本机。请先校对字幕，再导出。");
    } catch (e) { setError((e as Error).message); }
    finally { if (live.current) setBusy(false); }
  }

  async function select(selected: number) {
    if (!workspace || busy) return;
    if (dirty && !window.confirm("未保存的字幕修改会丢失。继续切换视频？")) return;
    setError("");
    try { if (await reload(workspace.id, selected)) { setIndex(selected); setJob(null); } }
    catch (e) { setError((e as Error).message); }
  }

  async function save() {
    if (!workspace || busy) return;
    setError(""); setBusy(true);
    try {
      const next = await api<Document>(captionBase, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      setDocument(next); setText(next.text); setRevision(r => r + 1); setNotice(`已保存 ${next.count} 段字幕`);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function run(mode: "transcribe" | "soft" | "hard", options: { language: string; container: string; font: string; font_size: number }, all: boolean) {
    if (!workspace || busy) return;
    if (dirty) { setError("请先保存字幕修改，再开始处理"); return; }
    if (mode === "transcribe" && document.count && !window.confirm("重新转录会替换当前字幕。继续？")) return;
    setError(""); setNotice(""); setBusy(true);
    try {
      for (const selected of all ? workspace.videos.map(v => v.index) : [index]) {
        let current = await api<Job>("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session: workspace.id, index: selected, mode, ...options }) });
        setJob(current);
        while (["queued", "running"].includes(current.state) && live.current) {
          await new Promise(resolve => setTimeout(resolve, 500));
          current = await api<Job>(`/api/jobs/${current.id}`); setJob(current);
        }
        if (!live.current) return;
        setHistory(previous => [current, ...previous].slice(0, 30));
        if (current.state === "failed") throw new Error(current.error || "处理失败，请查看日志");
        if (current.state === "cancelled") { setNotice("任务已停止；不会自动重试或处理余下视频"); break; }
        if (mode === "transcribe") await reload(workspace.id, index);
        setNotice(all ? "该视频完成，正在按顺序处理批量任务" : "成果已生成，请先预览并下载");
      }
    } catch (e) { if (live.current) setError((e as Error).message); }
    finally { if (live.current) setBusy(false); }
  }

  async function cancel() {
    if (!job || !["queued", "running"].includes(job.state)) return;
    try { await api<Job>(`/api/jobs/${job.id}/cancel`, { method: "POST" }); }
    catch (e) { setError((e as Error).message); }
  }

  async function clear() {
    if (!workspace || busy || !window.confirm("清空会删除本机临时视频、字幕与成果。确认已经下载需要保留的文件？")) return;
    setBusy(true); setError("");
    try {
      await api(`/api/workspaces/${workspace.id}`, { method: "DELETE" });
      epoch.current++; setWorkspace(null); setIndex(0); setDocument({ text: "", count: 0, cues: [] });
      setText(""); setJob(null); setHistory([]); setNotice("临时文件与历史已清空");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return { capabilities, workspace, index, document, text, setText, revision, busy, error, notice, job, history,
    dirty, captionBase, open, select, save, run, cancel, clear };
}
