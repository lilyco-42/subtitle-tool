"""Strict subtitle document I/O using the existing srt library."""
import html
import srt

MAX_SRT = 2 * 1024 * 1024


def document(text):
    if len(text.encode('utf-8')) > MAX_SRT:
        raise ValueError('字幕文件最多 2 MB')
    try:
        cues = list(srt.parse(text.lstrip('\ufeff'), ignore_errors=False))
    except (srt.SRTParseError, ValueError) as error:
        raise ValueError('字幕格式无效，请检查序号、时间轴与空行') from error
    if not cues or len(cues) > 10000:
        raise ValueError('字幕必须包含 1–10000 个片段')
    if any(c.start.total_seconds() < 0 or c.end <= c.start or not c.content.strip() for c in cues):
        raise ValueError('字幕起止时间或内容无效，不能静默丢弃片段')
    ordered = list(srt.sort_and_reindex(cues, skip=False))
    canonical = srt.compose(ordered, reindex=False)
    vtt = 'WEBVTT\n\n' + '\n\n'.join(
        srt.timedelta_to_srt_timestamp(c.start).replace(',', '.') + ' --> ' +
        srt.timedelta_to_srt_timestamp(c.end).replace(',', '.') + '\n' + html.escape(c.content)
        for c in ordered) + '\n'
    return {'text': canonical, 'count': len(ordered), 'vtt': vtt,
            'cues': [{'start': c.start.total_seconds(), 'end': c.end.total_seconds(),
                      'text': c.content} for c in ordered]}
