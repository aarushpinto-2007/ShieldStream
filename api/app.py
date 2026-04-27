import os, subprocess
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from cryptography.fernet import Fernet
from concurrent.futures import ThreadPoolExecutor
from static_ffmpeg import add_paths

# Setup FFmpeg (may or may not work on Vercel reliably)
add_paths()

app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)

# Vercel only allows /tmp
BASE_PATH = "/tmp/shieldstream"
UPLOAD_DIR = os.path.join(BASE_PATH, 'uploads')
VAULT_DIR = os.path.join(BASE_PATH, 'vault')
KEY_DIR = os.path.join(BASE_PATH, 'secure_keys')
MASTER_DIR = os.path.join(BASE_PATH, 'final_stream')
MASTER_VIDEO = os.path.join(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")

metadata = {"filename": "ShieldStream_Broadcast"}

def initialize_folders():
    for d in [UPLOAD_DIR, VAULT_DIR, KEY_DIR, MASTER_DIR]:
        os.makedirs(d, exist_ok=True)

# ---------------- ROUTES ---------------- #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/sender_upload", methods=["POST"])
def sender():
    if "video" not in request.files:
        return jsonify({"error": "No file"}), 400

    initialize_folders()

    file = request.files["video"]
    metadata["filename"] = os.path.splitext(file.filename)[0]
    video_path = os.path.join(UPLOAD_DIR, file.filename)
    file.save(video_path)

    output_template = os.path.join(UPLOAD_DIR, "part_%03d.mp4")

    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", "drawtext=text='SHIELD-ID':x=w-tw-20:y=h-th-20:fontcolor=white@0.02",
            "-f", "segment", "-segment_time", "30",
            output_template
        ], capture_output=True, timeout=50)
    except Exception as e:
        return jsonify({"error": str(e)})

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

@app.route("/run_receiver_task", methods=["POST"])
def run_receiver_task():
    initialize_folders()

    vault_files = sorted([f for f in os.listdir(VAULT_DIR) if f.endswith(".dat")])
    if not vault_files:
        return jsonify({"status": "Empty"})

    current_segments = []

    for filename in vault_files:
        chunk_id = filename.replace(".dat", "")
        enc_path = os.path.join(VAULT_DIR, filename)
        key_path = os.path.join(KEY_DIR, f"{chunk_id}.mp4.key")

        if not os.path.exists(key_path):
            continue

        try:
            with open(enc_path, "rb") as f:
                enc_data = f.read()
            with open(key_path, "rb") as f:
                key_data = f.read()

            decrypted = Fernet(key_data).decrypt(enc_data)

            tmp_mp4 = os.path.join(MASTER_DIR, f"dec_{chunk_id}.mp4")
            tmp_ts = os.path.join(MASTER_DIR, f"{chunk_id}.ts")

            with open(tmp_mp4, "wb") as f:
                f.write(decrypted)

            subprocess.run([
                "ffmpeg", "-i", tmp_mp4,
                "-c", "copy", "-f", "mpegts", "-y", tmp_ts
            ], capture_output=True, timeout=50)

            if os.path.exists(tmp_ts):
                current_segments.append(tmp_ts)

            if os.path.exists(tmp_mp4):
                os.remove(tmp_mp4)

        except:
            continue

    if current_segments:
        concat_file = os.path.join(MASTER_DIR, "join_list.txt")
        with open(concat_file, "w") as f:
            for ts in current_segments:
                f.write(f"file '{ts}'\n")

        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c", "copy", "-y", MASTER_VIDEO
        ], capture_output=True, timeout=50)

    return jsonify({"status": "Success", "count": len(current_segments)})

@app.route("/stream_video")
def stream_video():
    if os.path.exists(MASTER_VIDEO):
        return send_from_directory(MASTER_DIR, "ShieldStream_LIVE_Master.mp4")
    return jsonify({"error": "No video yet"})

@app.route("/scan_link", methods=["POST"])
def scan_link():
    url = request.json.get("url", "")
    is_piracy = any(word in url.lower() for word in ["stream", "live", "tv", "watch"])
    return jsonify({"found": is_piracy})

# Required for Vercel
app.debug = False

def handler(request):
    return app(request)
