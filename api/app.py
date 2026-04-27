import os, subprocess, time, shutil, socket
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from cryptography.fernet import Fernet
from concurrent.futures import ThreadPoolExecutor
from static_ffmpeg import add_paths

# Add FFmpeg to the system path automatically for Vercel
add_paths()

app = Flask(__name__)
CORS(app)

# Vercel only allows writing to the /tmp directory.
# We use a subfolder to keep things organized.
BASE_PATH = "/tmp/shieldstream"
UPLOAD_DIR = os.path.join(BASE_PATH, 'uploads')
VAULT_DIR = os.path.join(BASE_PATH, 'vault')
KEY_DIR = os.path.join(BASE_PATH, 'secure_keys')
MASTER_DIR = os.path.join(BASE_PATH, 'final_stream')
MASTER_VIDEO = os.path.join(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")

metadata = {"filename": "ShieldStream_Broadcast"}

def initialize_folders():
    """Ensures directories exist in the ephemeral /tmp storage."""
    for d in [UPLOAD_DIR, VAULT_DIR, KEY_DIR, MASTER_DIR]:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)

# --- SENDER ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sender_upload', methods=['POST'])
def sender():
    if 'video' not in request.files: 
        return jsonify({"error": "No file"}), 400
    
    initialize_folders()
    
    file = request.files['video']
    metadata["filename"] = os.path.splitext(file.filename)[0]
    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    output_template = os.path.join(UPLOAD_DIR, "part_%03d.mp4")
    
    # Process video: Watermark and Split
    cmd = [
        "ffmpeg", "-i", video_path, 
        "-vf", "drawtext=text='SHIELD-ID':x=w-tw-20:y=h-th-20:fontcolor=white@0.02",
        "-f", "segment", "-segment_time", "30", 
        output_template
    ]
    subprocess.run(cmd, capture_output=True)

    filenames = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("part_")]
    
    def encrypt_work(fname):
        key = Fernet.generate_key()
        with open(os.path.join(KEY_DIR, f"{fname}.key"), "wb") as kf: 
            kf.write(key)
        with open(os.path.join(UPLOAD_DIR, fname), "rb") as f:
            data = Fernet(key).encrypt(f.read())
        with open(os.path.join(VAULT_DIR, f"{fname}.dat"), "wb") as f: 
            f.write(data)
    
    with ThreadPoolExecutor(max_workers=2) as exe:
        exe.map(encrypt_work, filenames)
    
    return jsonify({"status": "Success", "parts": len(filenames)})

# --- RECEIVER ROUTES ---

@app.route('/run_receiver_task', methods=['POST'])
def run_receiver_task():
    initialize_folders()
    
    vault_files = sorted([f for f in os.listdir(VAULT_DIR) if f.endswith('.dat')])
    if not vault_files: 
        return jsonify({"status": "Empty", "message": "Nothing in vault."})

    current_segments = []
    for filename in vault_files:
        chunk_id = filename.replace(".dat", "")
        enc_path = os.path.join(VAULT_DIR, filename)
        key_path = os.path.join(KEY_DIR, f"{chunk_id}.mp4.key")
        
        if not os.path.exists(key_path): 
            continue

        with open(enc_path, "rb") as f: enc_data = f.read()
        with open(key_path, "rb") as f: key_data = f.read()
        
        try:
            decrypted = Fernet(key_data).decrypt(enc_data)
        except Exception:
            continue

        tmp_ts = os.path.join(MASTER_DIR, f"{chunk_id}.ts")
        tmp_mp4 = os.path.join(MASTER_DIR, f"dec_{chunk_id}.mp4")

        with open(tmp_mp4, "wb") as f: 
            f.write(decrypted)
            
        # Convert to streamable TS format
        subprocess.run(["ffmpeg", "-i", tmp_mp4, "-c", "copy", "-f", "mpegts", "-y", tmp_ts], capture_output=True)
        
        if os.path.exists(tmp_ts): 
            current_segments.append(tmp_ts)
        if os.path.exists(tmp_mp4): 
            os.remove(tmp_mp4)

    if current_segments:
        concat_file = os.path.join(MASTER_DIR, "join_list.txt")
        with open(concat_file, "w") as f:
            for ts in current_segments: 
                f.write(f"file '{ts}'\n")
        
        subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-y", MASTER_VIDEO], capture_output=True)
    
    return jsonify({"status": "Success", "decrypted_count": len(current_segments)})

@app.route('/stream_video')
def stream_video():
    return send_from_directory(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")

@app.route('/scan_link', methods=['POST'])
def scan_link():
    url = request.json.get('url', '')
    is_piracy = any(word in url.lower() for word in ['stream', 'live', 'tv', 'watch'])
    return jsonify({"found": is_piracy, "url": url})

# Required for Vercel: Disable debug mode
app.debug = False
