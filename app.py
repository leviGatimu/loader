# YouTube Downloader Backend - Production Ready
import os
import uuid
import threading
import re
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
# Allow common origins
CORS(app, resources={
    r"/*": {
        "origins": ["*", "https://loader-frontend-ipa4dg5y7-levigatimus-projects.vercel.app", "http://localhost:3000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Use /tmp/downloads for cloud compatibility (Railway)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_FOLDER = "/tmp/downloads"
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

task_status = {}
task_progress = {}

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

ffmpeg_available = check_ffmpeg()

def download_worker(task_id, url, format_id, title):
    safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')]).strip()    
    safe_title = safe_title[:100]
    output_template = os.path.join(DOWNLOAD_FOLDER, f"{task_id}.%(ext)s")

    def progress_hook(d):
        if d['status'] == 'downloading':
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            task_progress[task_id] = {
                'status': 'downloading',
                'percent': ansi_escape.sub('', d.get('_percent_str', '0%')).strip(),
                'speed': ansi_escape.sub('', d.get('_speed_str', 'N/A')).strip(),
                'eta': ansi_escape.sub('', d.get('_eta_str', 'N/A')).strip()
            }
        elif d['status'] == 'finished':
            task_status[task_id] = {'status': 'merging', 'percent': '100%'}
            task_progress[task_id] = {'status': 'merging', 'percent': '100%'}

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'check_formats': False
    }
    
    # Try to use cookies.txt if the user uploaded it
    cookie_path = os.path.join(BASE_DIR, "cookies.txt")
    if os.path.exists(cookie_path):
        ydl_opts['cookiefile'] = cookie_path

    if '+' in format_id:
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            actual_filename = None
            for f in os.listdir(DOWNLOAD_FOLDER):
                if f.startswith(task_id):
                    actual_filename = f
                    break
            
            if actual_filename:
                ext = actual_filename.split('.')[-1]
                display_name = f"{safe_title}.{ext}"
                task_status[task_id] = {
                    'status': 'finished', 
                    'filename': actual_filename, 
                    'display_name': display_name
                }
            else:
                task_status[task_id] = {'status': 'error', 'message': 'File not found after download'}
    except Exception as e:
        task_status[task_id] = {'status': 'error', 'message': str(e)}

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "ffmpeg": ffmpeg_available})

@app.route('/fetch', methods=['POST'])
def fetch_info():
    data = request.json
    url = data.get('url')
    if not url: return jsonify({'error': 'URL is required'}), 400

    cookie_path = os.path.join(BASE_DIR, "cookies.txt")
    
    ydl_opts = {
        'quiet': True, 
        'no_warnings': True, 
        'skip_download': True, 
        'noplaylist': True,
        'check_formats': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
    }
    
    if os.path.exists(cookie_path):
        logger.info(f"Found cookies.txt. Testing readability...")
        try:
            with open(cookie_path, 'r') as f:
                logger.info(f"Cookie file first line: {f.readline()[:30]}...")
            ydl_opts['cookiefile'] = cookie_path
        except Exception as e:
            logger.error(f"Cookie file error: {e}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []

            if ffmpeg_available:
                formats.append({
                    'format_id': 'bestvideo+bestaudio/best',
                    'extension': 'mp4',
                    'resolution': 'Best Quality',
                    'filesize': 'Variable',
                    'type': 'Video',
                    'quality_score': 10000,
                    'is_combined': True,
                    'note': 'Highest possible quality'
                })

            all_raw = info.get('formats', [])
            seen_resolutions = set()
            video_formats = []
            
            for f in all_raw:
                acodec = f.get('acodec')
                height = f.get('height')
                vcodec = f.get('vcodec')
                is_video = vcodec != 'none'
                
                if not is_video: continue
                
                res_label = f"{height}p" if height else (f.get('resolution') or 'Video')
                res_key = height if height else res_label

                if res_key not in seen_resolutions:
                    seen_resolutions.add(res_key)
                    if ffmpeg_available and height:
                        f_id = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
                        is_combined = True
                        note = "High Quality Merge"
                    else:
                        f_id = f.get('format_id')
                        is_combined = acodec and acodec != 'none'
                        note = f.get('format_note') or ''

                    filesize = f.get('filesize') or f.get('filesize_approx')
                    video_formats.append({
                        'format_id': f_id,
                        'extension': f.get('ext', 'mp4') or 'mp4',
                        'resolution': str(res_label),
                        'filesize': f"{round(filesize / (1024 * 1024), 2)} MB" if filesize else "Variable",
                        'type': 'Video',
                        'quality_score': height or 0,
                        'is_combined': is_combined,
                        'note': note
                    })
                    
            video_formats.sort(key=lambda x: x['quality_score'], reverse=True)
            formats.extend(video_formats)
            formats.append({
                'format_id': 'bestaudio/best',
                'extension': 'mp3',
                'resolution': 'Best Audio',
                'filesize': 'Variable',
                'type': 'Audio Only',
                'quality_score': -1,
                'is_combined': False,
                'note': 'Highest audio quality'
            })

            return jsonify({
                'id': info.get('id'), 
                'title': info.get('title'), 
                'thumbnail': info.get('thumbnail'), 
                'duration': info.get('duration_string') or 'N/A', 
                'formats': formats,
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count')
            })      
    except Exception as e: 
        error_msg = str(e)
        if "Sign in to confirm you’re not a bot" in error_msg:
            return jsonify({
                'error': "YouTube blocked the server (Bot Detection). Please upload cookies.txt to the backend folder.",
                'details': "Visit the project's help section for instructions on cookies.txt."
            }), 403
        
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_error = ansi_escape.sub('', error_msg)
        return jsonify({'error': f"Extraction failed: {clean_error}"}), 500

@app.route('/download', methods=['POST'])
def start_download():
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id')
    title = data.get('title', 'video')
    
    if not url or not format_id:
        return jsonify({'error': 'URL and format_id are required'}), 400
        
    task_id = str(uuid.uuid4())
    task_status[task_id] = {'status': 'started', 'percent': '0%'}
    task_progress[task_id] = {'percent': '0%', 'speed': 'Starting...', 'eta': '...'}
    
    threading.Thread(target=download_worker, args=(task_id, url, format_id, title)).start()    
    return jsonify({'task_id': task_id})

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    return jsonify(task_progress.get(task_id, {'percent': '0%', 'speed': '...'}))

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    return jsonify(task_status.get(task_id, {'status': 'not_found'}))

@app.route('/file/<task_id>', methods=['GET'])
def serve_file(task_id):
    status = task_status.get(task_id)
    if status and status.get('status') == 'finished':
        return send_from_directory(
            DOWNLOAD_FOLDER, 
            status['filename'], 
            as_attachment=True, 
            download_name=status['display_name']
        )
    return jsonify({'error': 'Not ready'}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
