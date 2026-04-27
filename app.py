import os, subprocess, time, shutil, socket
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from cryptography.fernet import Fernet
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024 # 2GB Limit

# --- DYNAMIC FOLDER CONFIGURATION ---
# IS_AZURE checks if the code is running on Azure Linux or Local Windows
IS_AZURE = os.environ.get('WEBSITE_INSTANCE_ID') is not None
BASE_PATH = "/mounts/sender" if IS_AZURE else r"C:\Sender"

UPLOAD_DIR = os.path.join(BASE_PATH, 'uploads')
VAULT_DIR = os.path.join(BASE_PATH, 'vault')
KEY_DIR = os.path.join(BASE_PATH, 'secure_keys')

metadata = {"filename": "ShieldStream_Broadcast"}

def initialize_folders():
    """Automatically creates the directory structure on whatever device is running the app."""
    folders = [BASE_PATH, UPLOAD_DIR, VAULT_DIR, KEY_DIR]
    for folder in folders:
        if not os.path.exists(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                print(f"Error creating {folder}: {e}")

# Initial run on startup
initialize_folders()

def get_ffmpeg_exe():
    """Locates FFmpeg based on the environment."""
    if IS_AZURE:
        return "ffmpeg"  # Linux uses the system-installed version
    return os.path.join(os.getcwd(), "ffmpeg.exe") # Windows looks for local exe

def kill_ffmpeg():
    if not IS_AZURE: # Only needed for local Windows testing
        try: subprocess.run("taskkill /f /im ffmpeg.exe", shell=True, capture_output=True)
        except: pass

def force_clear():
    kill_ffmpeg()
    time.sleep(1)
    initialize_folders()
    for folder in [UPLOAD_DIR, VAULT_DIR, KEY_DIR]:
        for f in os.listdir(folder):
            path = os.path.join(folder, f)
            try:
                if os.path.isfile(path): os.remove(path)
                elif os.path.isdir(path): shutil.rmtree(path)
            except: pass

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/sender_upload', methods=['POST'])
def sender():
    if 'video' not in request.files: return jsonify({"error": "No file"}), 400
    
    force_clear()
    file = request.files['video']
    metadata["filename"] = os.path.splitext(file.filename)[0]
    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    # 1. INVISIBLE WATERMARKING & CHUNKING
    output_template = os.path.join(UPLOAD_DIR, "part_%03d.mp4")
    watermark = "SHIELD-ID-99-ALPHA"
    
    cmd = (
        f'"{get_ffmpeg_exe()}" -i "{video_path}" '
        f'-vf "drawtext=text=\'{watermark}\':x=w-tw-20:y=h-th-20:fontsize=40:fontcolor=white@0.02" '
        f'-c:v libx264 -preset superfast -c:a aac -b:a 128k ' 
        f'-f segment -segment_time 60 "{output_template}"'
    )
    subprocess.run(cmd, shell=True)

    filenames = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("part_")]

    def encrypt_work(fname):
        key = Fernet.generate_key()
        with open(os.path.join(KEY_DIR, f"{fname}.key"), "wb") as kf: kf.write(key)
        with open(os.path.join(UPLOAD_DIR, fname), "rb") as f:
            data = Fernet(key).encrypt(f.read())
        with open(os.path.join(VAULT_DIR, f"{fname}.dat"), "wb") as f: f.write(data)

    with ThreadPoolExecutor(max_workers=4) as exe:
        exe.map(encrypt_work, filenames)

    return jsonify({"status": "Success", "parts": len(filenames)})

@app.route('/scan_link', methods=['POST'])
def scan_link():
    url = request.json.get('url', '')
    try:
        hostname = url.replace("http://", "").replace("https://", "").split("/")[0]
        ip_addr = socket.gethostbyname(hostname)
        # Standard piracy detection logic
        is_piracy = any(word in url.lower() for word in ['stream', 'live', 'tv', 'watch'])
        return jsonify({"found": is_piracy, "url": url, "ip": ip_addr})
    except:
        return jsonify({"found": False, "error": "Invalid URL"})

# --- RECEIVER ROUTES ---
@app.route('/get_metadata')
def get_meta(): return jsonify(metadata)

@app.route('/list_files')
def list_files(): return jsonify(sorted([f for f in os.listdir(VAULT_DIR) if f.endswith('.dat')]))

@app.route('/fetch_vault/<f>')
def fetch_vault(f): return send_from_directory(VAULT_DIR, f)

@app.route('/fetch_keys/<f>')
def fetch_keys(f): return send_from_directory(KEY_DIR, f)

if __name__ == '__main__':
    # Azure will automatically set the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)