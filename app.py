import os, subprocess, time, shutil, socket
from flask import Flask, request, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from cryptography.fernet import Fernet
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
IS_AZURE = os.environ.get('WEBSITE_INSTANCE_ID') is not None
BASE_PATH = "/mounts/sender" if IS_AZURE else r"C:\Sender"

UPLOAD_DIR = os.path.join(BASE_PATH, 'uploads')
VAULT_DIR = os.path.join(BASE_PATH, 'vault')
KEY_DIR = os.path.join(BASE_PATH, 'secure_keys')
MASTER_DIR = os.path.join(BASE_PATH, 'final_stream')
MASTER_VIDEO = os.path.join(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")

metadata = {"filename": "ShieldStream_Broadcast"}

def initialize_folders():
    for d in [BASE_PATH, UPLOAD_DIR, VAULT_DIR, KEY_DIR, MASTER_DIR]:
        os.makedirs(d, exist_ok=True)

initialize_folders()

def get_ffmpeg_exe():
    return "ffmpeg" if IS_AZURE else os.path.join(os.getcwd(), "ffmpeg.exe")

# --- SENDER ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/sender_upload', methods=['POST'])
def sender():
    if 'video' not in request.files: return jsonify({"error": "No file"}), 400
    file = request.files['video']
    metadata["filename"] = os.path.splitext(file.filename)[0]
    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    output_template = os.path.join(UPLOAD_DIR, "part_%03d.mp4")
    cmd = (f'"{get_ffmpeg_exe()}" -i "{video_path}" -vf "drawtext=text=\'SHIELD-ID\':x=w-tw-20:y=h-th-20:fontcolor=white@0.02" '
           f'-f segment -segment_time 60 "{output_template}"')
    subprocess.run(cmd, shell=True)

    filenames = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("part_")]
    def encrypt_work(fname):
        key = Fernet.generate_key()
        with open(os.path.join(KEY_DIR, f"{fname}.key"), "wb") as kf: kf.write(key)
        with open(os.path.join(UPLOAD_DIR, fname), "rb") as f:
            data = Fernet(key).encrypt(f.read())
        with open(os.path.join(VAULT_DIR, f"{fname}.dat"), "wb") as f: f.write(data)
    
    with ThreadPoolExecutor(max_workers=4) as exe: exe.map(encrypt_work, filenames)
    return jsonify({"status": "Success", "parts": len(filenames)})

# --- RECEIVER LOGIC (Integrated) ---
@app.route('/run_receiver_task', methods=['POST'])
def run_receiver_task():
    vault_files = sorted([f for f in os.listdir(VAULT_DIR) if f.endswith('.dat')])
    if not vault_files: return jsonify({"status": "Empty", "message": "No segments in vault."})

    current_segments = []
    for filename in vault_files:
        chunk_id = filename.replace(".dat", "")
        # Paths
        enc_path = os.path.join(VAULT_DIR, filename)
        key_path = os.path.join(KEY_DIR, f"{chunk_id}.mp4.key") # Adjusted to match sender naming
        if not os.path.exists(key_path): continue

        with open(enc_path, "rb") as f: enc_data = f.read()
        with open(key_path, "rb") as f: key_data = f.read()
        
        decrypted = Fernet(key_data).decrypt(enc_data)
        tmp_ts = os.path.join(MASTER_DIR, f"{chunk_id}.ts")
        tmp_mp4 = os.path.join(MASTER_DIR, f"dec_{chunk_id}.mp4")

        with open(tmp_mp4, "wb") as f: f.write(decrypted)
        subprocess.run([get_ffmpeg_exe(), "-i", tmp_mp4, "-c", "copy", "-f", "mpegts", "-y", tmp_ts], capture_output=True)
        
        if os.path.exists(tmp_ts): current_segments.append(tmp_ts)
        if os.path.exists(tmp_mp4): os.remove(tmp_mp4)

    if current_segments:
        concat_file = os.path.join(MASTER_DIR, "join_list.txt")
        with open(concat_file, "w") as f:
            for ts in current_segments: f.write(f"file '{ts.replace('\\', '/')}'\n")
        
        subprocess.run([get_ffmpeg_exe(), "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", "-y", MASTER_VIDEO], capture_output=True)
    
    return jsonify({"status": "Success", "decrypted_count": len(current_segments)})

@app.route('/stream_video')
def stream_video():
    # This route allows the <video> tag to read the file even while it's being updated
    return send_from_directory(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
