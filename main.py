from flask import Flask, render_template, Response, request, jsonify, send_from_directory
import os
import queue
import threading
import cv2
import numpy as np
import time
from datetime import datetime
from video_processor import VideoProcessor
import json

app = Flask(__name__, static_folder='static', template_folder='templates')

# Global variables
frame_queues = {
    1: queue.Queue(maxsize=10),
    2: queue.Queue(maxsize=10),
    3: queue.Queue(maxsize=10),
    4: queue.Queue(maxsize=10)
}

video_processors = {}
camera_status = {
    1: {'type': 'offline', 'url': None, 'count': 0, 'fall': False},
    2: {'type': 'offline', 'url': None, 'count': 0, 'fall': False},
    3: {'type': 'offline', 'url': None, 'count': 0, 'fall': False},
    4: {'type': 'offline', 'url': None, 'count': 0, 'fall': False}
}

# Lock for thread safety
status_lock = threading.Lock()

def get_processor(camera_id):
    if camera_id not in video_processors:
        video_processors[camera_id] = VideoProcessor(camera_id, frame_queues[camera_id])
    return video_processors[camera_id]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/status')
def get_status():
    with status_lock:
        return jsonify(camera_status)

@app.route('/set_ip', methods=['POST'])
def set_ip():
    data = request.get_json()
    camera_id = data.get('camera_id')
    ip_address = data.get('ip')
    
    if not ip_address:
        return jsonify({'error': 'IP address required'}), 400
    
    with status_lock:
        camera_status[camera_id] = {
            'type': 'ip_camera',
            'url': ip_address,
            'count': 0,
            'fall': False,
            'timestamp': datetime.now().isoformat()
        }
    
    # Start processing thread
    processor = get_processor(camera_id)
    processor.start_ip_camera(ip_address)
    
    return jsonify({
        'success': True,
        'message': f'IP camera {ip_address} set for Camera {camera_id}',
        'camera_id': camera_id
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    camera_id = int(request.form.get('camera_id', 1))
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Save file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'camera_{camera_id}_{timestamp}_{file.filename}'
    uploads_dir = 'uploads'
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, filename)
    file.save(file_path)
    
    # Update status
    with status_lock:
        camera_status[camera_id] = {
            'type': 'video_file',
            'url': filename,
            'count': 0,
            'fall': False,
            'timestamp': datetime.now().isoformat()
        }
    
    # Start processing
    processor = get_processor(camera_id)
    processor.start_video_file(file_path)
    
    return jsonify({
        'success': True,
        'message': 'File uploaded successfully',
        'filename': filename,
        'camera_id': camera_id
    })

@app.route('/close_camera/<int:camera_id>', methods=['POST'])
def close_camera(camera_id):
    with status_lock:
        camera_status[camera_id] = {
            'type': 'offline',
            'url': None,
            'count': 0,
            'fall': False
        }
    
    if camera_id in video_processors:
        video_processors[camera_id].stop()
    
    return jsonify({
        'success': True,
        'message': f'Camera {camera_id} closed'
    })

@app.route('/test_feed/<int:camera_id>')
def test_feed(camera_id):
    processor = get_processor(camera_id)
    
    def generate():
        while True:
            try:
                frame = frame_queues[camera_id].get(timeout=1)
                
                # Get current status
                with status_lock:
                    status = camera_status[camera_id]
                    processor.update_status(status)
                
                # Encode frame
                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                time.sleep(0.033)  # ~30 FPS
            except queue.Empty:
                # Send a blank frame
                blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                blank_frame[:] = (40, 44, 52)
                cv2.putText(blank_frame, f"Camera {camera_id} - No Feed", 
                           (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, 
                           (255, 255, 255), 2)
                _, buffer = cv2.imencode('.jpg', blank_frame)
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                time.sleep(1)
            except Exception as e:
                print(f"Error in feed {camera_id}: {e}")
                break
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    print("Starting Fall Detection System...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, host='0.0.0.0', port=5000)