from typing import List, Dict
import os
import subprocess
import tempfile


def _is_exe(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def concat_segments_ffmpeg(segments: List[Dict], output_path: str, ffmpeg_path: str = 'ffmpeg'):
    if not (_is_exe(ffmpeg_path) or ffmpeg_path == 'ffmpeg'):
        raise RuntimeError(f"ffmpeg not found at {ffmpeg_path}")
    if not segments:
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        part_paths = []
        for idx, s in enumerate(segments):
            start = max(0.0, float(s['start_time']))
            end = float(s['end_time'])
            in_path = s['video_path']
            part = os.path.join(tmpdir, f'part_{idx:04d}.mp4')
            # Re-encode for accurate trim
            # Đặt -i trước -ss để đảm bảo seek chính xác hơn
            cmd = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                   '-i', in_path,
                   '-ss', f'{start:.3f}', '-to', f'{end:.3f}',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-an', part]
            subprocess.run(cmd, check=True)
            part_paths.append(part)

        list_file = os.path.join(tmpdir, 'parts.txt')
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in part_paths:
                f.write(f"file '{p.replace('\\', '/')}'\n")

        cmd_concat = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                      '-f', 'concat', '-safe', '0', '-i', list_file,
                      '-c', 'copy', output_path]
        subprocess.run(cmd_concat, check=True)


def concat_segments(segments: List[Dict], output_path: str, ffmpeg_path: str | None = None):
    # Prefer ffmpeg if available
    if ffmpeg_path and (_is_exe(ffmpeg_path) or ffmpeg_path == 'ffmpeg'):
        return concat_segments_ffmpeg(segments, output_path, ffmpeg_path)

    try:
        from moviepy.editor import VideoFileClip, concatenate_videoclips
    except Exception as e:
        raise RuntimeError(f"moviepy not available and no ffmpeg provided: {e}")

    clips = []
    for s in segments:
        start = max(0, s['start_time'])
        end = s['end_time']
        clip = VideoFileClip(s['video_path']).subclip(start, end)
        clips.append(clip)

    if not clips:
        return

    result = concatenate_videoclips(clips, method='compose')
    result.write_videofile(output_path, codec='libx264', audio=False, fps=25)
    for c in clips:
        c.close()
    result.close()


