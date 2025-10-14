from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.responses import StreamingResponse
import os
import uuid
from typing import List
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from anyio import to_thread
import json

from .service import run_job


app = FastAPI(title='VJTS API')


@app.post('/jobs')
async def create_job(plate: str = Form(...), video_dir: str = Form('data/videos'), output_dir: str = Form('data/outputs')):
    res = run_job(
        plate=plate,
        video_dir=video_dir,
        output_dir=output_dir,
        config_path='config/config.yaml',
        annotate=True,
        ffmpeg_path=os.path.join(os.getcwd(), 'ffmpeg.exe') if os.path.exists('ffmpeg.exe') else None,
        db_path='db/vjts.sqlite',
    )
    return JSONResponse(res)


@app.post('/upload_run')
async def upload_and_run(
    plate: str = Form(...),
    files: List[UploadFile] = File(...),
    output_dir: str = Form('data/outputs')
):
    job_uuid = uuid.uuid4().hex[:12]
    upload_dir = os.path.join('data', 'videos', 'uploads', job_uuid)
    os.makedirs(upload_dir, exist_ok=True)
    saved = []
    for uf in files:
        dest = os.path.join(upload_dir, uf.filename)
        with open(dest, 'wb') as f:
            f.write(await uf.read())
        saved.append(dest)

    res = run_job(
        plate=plate,
        video_dir=upload_dir,
        output_dir=output_dir,
        config_path='config/config.yaml',
        annotate=True,
        ffmpeg_path=os.path.join(os.getcwd(), 'ffmpeg.exe') if os.path.exists('ffmpeg.exe') else None,
        db_path='db/vjts.sqlite',
    )
    res['uploaded'] = saved
    return JSONResponse(res)

@app.post('/upload')
async def upload_only(files: List[UploadFile] = File(...)):
    job_uuid = uuid.uuid4().hex[:12]
    upload_dir = os.path.join('data', 'videos', 'uploads', job_uuid)
    os.makedirs(upload_dir, exist_ok=True)
    saved = []
    for uf in files:
        dest = os.path.join(upload_dir, uf.filename)
        with open(dest, 'wb') as f:
            f.write(await uf.read())
        saved.append(dest)
    return JSONResponse({'upload_dir': upload_dir, 'saved': saved})


@app.websocket('/ws')
async def ws_progress(ws: WebSocket):
    await ws.accept()
    job_uuid = None
    try:
        data = await ws.receive_json()
        plate = data.get('plate')
        video_dir = data.get('video_dir', 'data/videos')
        output_dir = data.get('output_dir', 'data/outputs')
        job_uuid = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()

        def on_event(evt):
            loop.call_soon_threadsafe(asyncio.create_task, ws.send_json(evt))

        def on_crop(buf: bytes):
            loop.call_soon_threadsafe(asyncio.create_task, ws.send_bytes(buf))

        async def run_blocking():
            return await to_thread.run_sync(
                run_job,
                plate,
                video_dir,
                output_dir,
                'config/config.yaml',
                True,
                os.path.join(os.getcwd(), 'ffmpeg.exe') if os.path.exists('ffmpeg.exe') else None,
                'db/vjts.sqlite',
                on_event,
                on_crop,
            )

        res = await run_blocking()
        await ws.send_json({'type': 'result', **res})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({'type': 'error', 'message': str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.get('/events')
async def sse_events(plate: str, video_dir: str = 'data/videos', output_dir: str = 'data/outputs'):
    queue: asyncio.Queue = asyncio.Queue()

    def on_event(evt):
        try:
            queue.put_nowait({'type': 'event', 'payload': evt})
        except Exception:
            pass

    def on_crop(buf: bytes):
        try:
            import base64
            b64 = base64.b64encode(buf).decode('ascii')
            queue.put_nowait({'type': 'crop', 'payload': f'data:image/jpeg;base64,{b64}'})
        except Exception:
            pass

    async def gen():
        loop = asyncio.get_running_loop()
        task = loop.create_task(to_thread.run_sync(
            run_job,
            plate,
            video_dir,
            output_dir,
            'config/config.yaml',
            True,
            os.path.join(os.getcwd(), 'ffmpeg.exe') if os.path.exists('ffmpeg.exe') else None,
            'db/vjts.sqlite',
            on_event,
            on_crop,
        ))
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.5)
                    if item['type'] == 'event':
                        yield f"data: {json.dumps(item['payload'])}\n\n"
                    elif item['type'] == 'crop':
                        yield f"event: crop\ndata: {item['payload']}\n\n"
                except asyncio.TimeoutError:
                    if task.done():
                        try:
                            res = task.result()
                            yield f"event: result\ndata: {json.dumps(res)}\n\n"
                        except Exception as e:
                            err = {'error': 'job_failed', 'message': str(e)}
                            yield f"event: result\ndata: {json.dumps(err)}\n\n"
                        break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(gen(), media_type='text/event-stream')


@app.get('/download/result')
async def download_result(path: str):
    if not os.path.exists(path):
        return JSONResponse({'error': 'not found'}, status_code=404)
    return FileResponse(path)


@app.get('/')
async def root_index():
    return RedirectResponse(url='/ui/')

app.mount('/ui', StaticFiles(directory='web', html=True), name='web')


