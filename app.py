from flask import Flask, request, render_template_string, jsonify, send_from_directory
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import yt_dlp
import os
import threading
from collections import defaultdict

app = Flask(__name__)
auth = HTTPBasicAuth()

# Define a user and hashed password
users = {
    "admin": generate_password_hash("123")  # Replace "your_password_here" with your desired password
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# Define the download folder and gallery folder for Android
DOWNLOAD_FOLDER = 'downloads'
GALLERY_FOLDER = '/storage/emulated/0/Download/Web downloader/'  # Android gallery path
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(GALLERY_FOLDER, exist_ok=True)

# Store download progress globally
download_status = defaultdict(dict)

def download_task(url, download_id):
    try:
        ydl_opts = {
            'outtmpl': os.path.join(GALLERY_FOLDER, '%(title)s.%(ext)s'),  # Save directly to the gallery
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'quiet': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_status[download_id]['status'] = 'downloading'
            info = ydl.extract_info(url, download=True)
            download_status[download_id]['status'] = 'completed'
            download_status[download_id]['filename'] = ydl.prepare_filename(info)
    except Exception as e:
        download_status[download_id]['status'] = 'error'
        download_status[download_id]['error'] = str(e)

def progress_hook(d, download_id):
    if d['status'] == 'downloading':
        downloaded = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes', 1)  # Avoid division by zero
        remaining = total - downloaded
        percent = (downloaded / total) * 100 if total > 0 else 0

        download_status[download_id]['progress'] = f"{percent:.2f}%"
        download_status[download_id]['downloaded'] = f"{downloaded / (1024 * 1024):.2f} MB"
        download_status[download_id]['remaining'] = f"{remaining / (1024 * 1024):.2f} MB"
        download_status[download_id]['speed'] = d.get('_speed_str', 'N/A')
        download_status[download_id]['eta'] = d.get('_eta_str', 'N/A')

@app.route('/')
@auth.login_required
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Parallel Video Downloader</title>
            <style>
                body { font-family: Arial; max-width: 800px; margin: 0 auto; padding: 20px; }
                .download-item { border: 1px solid #ddd; padding: 10px; margin: 10px 0; }
                .progress-bar { height: 20px; background: #f0f0f0; margin: 5px 0; }
                .progress { height: 100%; background: #4CAF50; width: 0%; }
            </style>
        </head>
        <body>
            <h1>Video Downloader</h1>
            <form id="download-form">
                <input type="url" name="url" placeholder="Enter video URL" required>
                <button type="submit">Start Download</button>
            </form>
            
            <div id="downloads-container"></div>
            
            <script>
                const form = document.getElementById('download-form');
                const container = document.getElementById('downloads-container');
                
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const url = form.url.value;
                    form.url.value = '';
                    
                    // Start new download
                    const response = await fetch('/start_download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: `url=${encodeURIComponent(url)}`
                    });
                    const { download_id } = await response.json();
                    
                    // Create download item UI
                    const item = document.createElement('div');
                    item.className = 'download-item';
                    item.id = `download-${download_id}`;
                    item.innerHTML = `
                        <h3>Downloading: ${url}</h3>
                        <div class="progress-bar"><div class="progress" id="progress-${download_id}"></div></div>
                        <div>Status: <span id="status-${download_id}">Starting...</span></div>
                        <div>Downloaded: <span id="downloaded-${download_id}">0 MB</span></div>
                        <div>Remaining: <span id="remaining-${download_id}">0 MB</span></div>
                        <div>Speed: <span id="speed-${download_id}">N/A</span></div>
                        <div>ETA: <span id="eta-${download_id}">N/A</span></div>
                    `;
                    container.prepend(item);
                    
                    // Poll for progress updates
                    const updateProgress = async () => {
                        const res = await fetch(`/progress/${download_id}`);
                        const data = await res.json();
                        
                        document.getElementById(`progress-${download_id}`).style.width = data.progress || '0%';
                        document.getElementById(`status-${download_id}`).textContent = data.status;
                        document.getElementById(`downloaded-${download_id}`).textContent = data.downloaded || '0 MB';
                        document.getElementById(`remaining-${download_id}`).textContent = data.remaining || '0 MB';
                        document.getElementById(`speed-${download_id}`).textContent = data.speed || 'N/A';
                        document.getElementById(`eta-${download_id}`).textContent = data.eta || 'N/A';
                        
                        if (data.status === 'completed') {
                            item.innerHTML += `<a href="/download/${data.filename}">Download File</a>`;
                        } else if (data.status !== 'error') {
                            setTimeout(updateProgress, 1000);
                        }
                    };
                    updateProgress();
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/start_download', methods=['POST'])
@auth.login_required
def start_download():
    url = request.form['url']
    download_id = os.urandom(4).hex()
    download_status[download_id] = {'url': url}
    
    # Start download in background thread
    threading.Thread(target=download_task, args=(url, download_id)).start()
    
    return jsonify({'download_id': download_id})

@app.route('/progress/<download_id>')
@auth.login_required
def get_progress(download_id):
    return jsonify(download_status.get(download_id, {'status': 'unknown'}))

@app.route('/download/<filename>')
@auth.login_required
def download_file(filename):
    return send_from_directory(GALLERY_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)