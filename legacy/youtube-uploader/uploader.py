import os
import json
import sqlite3
import subprocess
import tempfile
import base64
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS = 'client_secret.json'
TOKEN_FILE = 'token.json'
DB_FILE = 'pipeline.db'
DAILY_LIMIT = 50
VIDEOS_DIR = os.path.expanduser('~/Desktop/car-vids')

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY,
        filepath TEXT UNIQUE,
        filename TEXT,
        car_model TEXT,
        status TEXT DEFAULT 'pending',
        uploaded_at TEXT
    )''')
    conn.commit()
    conn.close()

def scan_videos():
    extensions = ('.mp4', '.mov', '.MP4', '.MOV', '.m4v', '.M4V')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    found = 0
    for f in os.listdir(VIDEOS_DIR):
        if f.endswith(extensions):
            filepath = os.path.join(VIDEOS_DIR, f)
            try:
                c.execute('INSERT OR IGNORE INTO videos (filepath, filename) VALUES (?, ?)', (filepath, f))
                if c.rowcount:
                    found += 1
            except:
                pass
    conn.commit()
    conn.close()
    print(f'Scanned: {found} new videos indexed from {VIDEOS_DIR}')

def extract_frame(filepath):
    tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
    out_path = tmp.name
    tmp.close()
    cmd = [
        'ffmpeg', '-i', filepath,
        '-ss', '00:00:02',
        '-vframes', '1',
        '-q:v', '2',
        '-y', out_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode == 0 and os.path.exists(out_path):
        return out_path
    return None

def identify_car(frame_path):
    try:
        with open(frame_path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        message = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=64,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': 'image/jpeg',
                            'data': image_data
                        }
                    },
                    {
                        'type': 'text',
                        'text': 'What car is in this image? Reply with ONLY the make and model, and location if you can identify it (e.g. "BMW M3 on Mulholland Drive" or "Audi A6 in Los Angeles"). No year. If you cannot identify a specific car, reply with exactly "Car Vid".'
                    }
                ]
            }]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f'  Vision error: {e}')
        return 'Car Vid'

def get_video_duration(filepath):
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', filepath
    ], capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                return float(stream.get('duration', 0))
    except:
        pass
    return 0

def process_video(filepath):
    duration = get_video_duration(filepath)
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    out_path = tmp.name
    tmp.close()

    trim = ['-t', '59'] if duration > 59 else []

    cmd = [
        'ffmpeg', '-i', filepath,
        '-vf', 'crop=ih*9/16:ih,scale=1080:1920',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        '-c:a', 'aac', '-b:a', '128k',
        *trim,
        '-y', out_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode == 0:
        return out_path
    return None

def get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def upload_video(youtube, filepath, title):
    body = {
        'snippet': {
            'title': title,
            'description': '#Shorts #Cars #BMW #CarContent #EnvyCars',
            'tags': ['Shorts', 'Cars', 'BMW', 'CarContent', 'EnvyCars', 'Automotive'],
            'categoryId': '2'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    media = MediaFileUpload(filepath, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = request.execute()
    return response.get('id')

def run_pipeline():
    init_db()
    scan_videos()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT filepath, filename FROM videos WHERE status='pending' LIMIT ?", (DAILY_LIMIT,))
    pending = c.fetchall()
    conn.close()

    if not pending:
        print('No pending videos.')
        return

    print(f'\nUploading {len(pending)} videos...\n')
    youtube = get_authenticated_service()
    uploaded = 0
    skipped = 0

    for (filepath, filename) in pending:
        print(f'Processing: {filename}')

        # Extract frame and identify car
        frame = extract_frame(filepath)
        if frame:
            car_model = identify_car(frame)
            try:
                os.unlink(frame)
            except:
                pass
        else:
            car_model = 'Car Vid'
        print(f'  Identified: {car_model}')

        # Save car model to db
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE videos SET car_model=? WHERE filepath=?", (car_model, filepath))
        conn.commit()
        conn.close()

        # Process video
        processed = process_video(filepath)
        if not processed:
            print(f'  FFmpeg failed, skipping.')
            skipped += 1
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE videos SET status='failed' WHERE filepath=?", (filepath,))
            conn.commit()
            conn.close()
            continue

        title = f'{car_model}'
        try:
            video_id = upload_video(youtube, processed, title)
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE videos SET status='uploaded', uploaded_at=? WHERE filepath=?",
                      (datetime.now().isoformat(), filepath))
            conn.commit()
            conn.close()
            print(f'  Uploaded: youtube.com/shorts/{video_id}')
            uploaded += 1
        except Exception as e:
            print(f'  Upload failed: {e}')
        finally:
            try:
                os.unlink(processed)
            except:
                pass

    print(f'\nDone. {uploaded} uploaded, {skipped} skipped out of {len(pending)} processed.')

if __name__ == '__main__':
    run_pipeline()
