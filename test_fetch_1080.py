import yt_dlp
import json

ydl_opts = {
    'quiet': True, 
    'no_warnings': True, 
    'skip_download': True, 
    'noplaylist': True
}

ffmpeg_available = False
url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Rick Roll, 1080p

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    
    formats = []
    
    all_raw = info.get('formats', [])
    all_raw.sort(key=lambda x: (x.get('height') or 0, x.get('tbr') or 0), reverse=True)
    
    seen_resolutions = set()
    for f in all_raw:
        height = f.get('height')
        vcodec = f.get('vcodec')
        acodec = f.get('acodec')
        
        if vcodec and vcodec != 'none':
            res_label = f"{height}p" if height else f.get('resolution') or 'Video'
            res_key = height if height else res_label
            
            if res_key not in seen_resolutions:
                seen_resolutions.add(res_key)
                formats.append({
                    'format_id': f.get('format_id'),
                    'resolution': res_label,
                    'type': 'Video',
                    'vcodec': vcodec,
                    'height': height
                })

    print(json.dumps(formats, indent=2))
