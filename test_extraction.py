import yt_dlp
import json

ydl_opts = {
    'quiet': True, 
    'no_warnings': True, 
    'skip_download': True, 
    'noplaylist': True
}

url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # Me at the zoo

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    
    print("Total formats:", len(info.get('formats', [])))
    
    video_formats = []
    audio_formats = []
    
    for f in info.get('formats', []):
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        height = f.get('height')
        
        if vcodec != 'none':
            video_formats.append({
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'vcodec': vcodec,
                'acodec': acodec,
                'height': height,
                'resolution': f.get('resolution')
            })
        elif acodec != 'none':
            audio_formats.append({
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'acodec': acodec,
            })
            
    print("\nVideo Formats Found:", len(video_formats))
    for vf in video_formats[-5:]: # show last 5 (usually highest qual)
        print(vf)
        
    print("\nAudio Formats Found:", len(audio_formats))
    
