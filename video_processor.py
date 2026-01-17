import cv2
import numpy as np
import time
from threading import Thread, Lock
from datetime import datetime
from ultralytics import YOLO
import torch

class VideoProcessor:
    def __init__(self, camera_id, frame_queue):
        self.camera_id = camera_id
        self.frame_queue = frame_queue
        self.running = False
        self.process_thread = None
        self.model = None
        self.status = {}
        self.status_lock = Lock()
        self.fall_history = []
        self.total_people_count = 0
        self.max_people_count = 0
        self.frame_count = 0
        
        # Load YOLO model (automatically downloads if not present)
        self.load_model()
    
    def load_model(self):
        """Load YOLO model for person detection"""
        try:
            # Load YOLOv8n model (smallest and fastest)
            self.model = YOLO('yolov8n.pt')
            print(f"Model loaded for camera {self.camera_id}")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
    
    def update_status(self, status):
        with self.status_lock:
            self.status = status
    
    def detect_people(self, frame):
        """Detect people in frame using YOLO"""
        if self.model is None:
            return frame, 0, []
        
        try:
            # Run inference
            results = self.model(frame, verbose=False)
            
            people_count = 0
            detections = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        
                        # Only detect people (class 0 in COCO)
                        if cls == 0 and conf > 0.5:
                            people_count += 1
                            
                            # Get bounding box coordinates
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            detections.append({
                                'bbox': [x1, y1, x2, y2],
                                'confidence': conf,
                                'id': len(detections)
                            })
            
            return frame, people_count, detections
        except Exception as e:
            print(f"Detection error: {e}")
            return frame, 0, []
    
    def detect_fall(self, detections, frame):
        """Simple fall detection based on aspect ratio and position"""
        fall_detected = False
        fall_bbox = None
        
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            width = x2 - x1
            height = y2 - y1
            
            # Calculate aspect ratio (height/width)
            if width > 0:
                aspect_ratio = height / width
                
                # Fall detection logic:
                # 1. Person is lying down (aspect ratio < 0.8)
                # 2. Person is near the bottom of the frame
                # 3. Person is relatively large in frame
                frame_height, frame_width = frame.shape[:2]
                bbox_center_y = (y1 + y2) / 2
                
                if (aspect_ratio < 0.8 and 
                    bbox_center_y > frame_height * 0.6 and
                    height > frame_height * 0.3):
                    fall_detected = True
                    fall_bbox = detection['bbox']
                    break
        
        return fall_detected, fall_bbox
    
    def draw_detections(self, frame, detections, people_count, fall_detected, fall_bbox):
        """Draw bounding boxes and information on frame"""
        frame_copy = frame.copy()
        
        # Draw bounding boxes for all people
        for detection in detections:
            x1, y1, x2, y2 = detection['bbox']
            conf = detection['confidence']
            
            # Draw bounding box
            color = (0, 255, 0)  # Green for normal
            if fall_detected and detection['bbox'] == fall_bbox:
                color = (0, 0, 255)  # Red for fallen person
            
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"Person {detection['id']+1}: {conf:.2f}"
            cv2.putText(frame_copy, label, (x1, y1-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw statistics overlay
        self.draw_statistics(frame_copy, people_count, fall_detected)
        
        return frame_copy
    
    def draw_statistics(self, frame, people_count, fall_detected):
        """Draw statistics overlay on frame"""
        height, width = frame.shape[:2]
        
        # Update counters
        self.total_people_count += people_count
        self.frame_count += 1
        self.max_people_count = max(self.max_people_count, people_count)
        
        # Create semi-transparent overlay
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 80), (40, 44, 52), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw camera info
        cv2.putText(frame, f"Camera {self.camera_id}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # Draw people count
        count_color = (0, 255, 0) if people_count <= 10 else (0, 165, 255) if people_count <= 20 else (0, 0, 255)
        cv2.putText(frame, f"People: {people_count}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, count_color, 2)
        
        # Draw fall alert if detected
        if fall_detected:
            cv2.rectangle(frame, (width//2 - 150, 10), (width//2 + 150, 50), 
                         (0, 0, 255), -1)
            cv2.putText(frame, "FALL DETECTED!", (width//2 - 120, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        
        # Draw average count
        avg_count = self.total_people_count / max(self.frame_count, 1)
        cv2.putText(frame, f"Avg: {avg_count:.1f} | Max: {self.max_people_count}", 
                   (width - 300, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Draw timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (width - 250, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    
    def process_video_file(self, file_path):
        """Process video file"""
        cap = cv2.VideoCapture(file_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_delay = 1 / fps
        
        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Detect people
            frame, people_count, detections = self.detect_people(frame)
            
            # Detect falls
            fall_detected, fall_bbox = self.detect_fall(detections, frame)
            
            # Draw detections
            processed_frame = self.draw_detections(frame, detections, people_count, 
                                                  fall_detected, fall_bbox)
            
            # Update status
            with self.status_lock:
                self.status['count'] = people_count
                self.status['fall'] = fall_detected
                self.status['timestamp'] = datetime.now().isoformat()
            
            # Add to queue
            if self.frame_queue.full():
                self.frame_queue.get()
            self.frame_queue.put(processed_frame)
            
            time.sleep(frame_delay)
        
        cap.release()
    
    def process_ip_camera(self, ip_url):
        """Process IP camera stream"""
        # For simulation, we'll create a synthetic feed
        # In real implementation, you would connect to the IP camera
        
        frame_width, frame_height = 640, 480
        person_positions = [
            {'x': 100, 'y': 200, 'dx': 2, 'dy': 1, 'fallen': False},
            {'x': 300, 'y': 300, 'dx': -1, 'dy': 0, 'fallen': False},
            {'x': 500, 'y': 250, 'dx': 0, 'dy': -1, 'fallen': False},
        ]
        
        while self.running:
            # Create blank frame
            frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
            frame[:] = (60, 63, 65)  # Dark gray background
            
            # Add some floor texture
            cv2.rectangle(frame, (0, frame_height-50), (frame_width, frame_height), 
                         (100, 100, 100), -1)
            
            # Simulate moving people
            detections = []
            fall_detected = False
            fall_bbox = None
            
            for i, person in enumerate(person_positions):
                # Update position
                if not person['fallen']:
                    person['x'] += person['dx']
                    person['y'] += person['dy']
                    
                    # Bounce off walls
                    if person['x'] < 50 or person['x'] > frame_width - 50:
                        person['dx'] *= -1
                    if person['y'] < 100 or person['y'] > frame_height - 100:
                        person['dy'] *= -1
                
                # Randomly simulate fall
                if np.random.random() < 0.001 and not person['fallen']:
                    person['fallen'] = True
                    person['dx'] = 0
                    person['dy'] = 0
                
                # Create bounding box
                box_size = 30 if not person['fallen'] else 60
                x1 = int(person['x'] - box_size//2)
                y1 = int(person['y'] - box_size//(2 if not person['fallen'] else 1))
                x2 = int(person['x'] + box_size//2)
                y2 = int(person['y'] + box_size//(2 if person['fallen'] else 1))
                
                detections.append({
                    'bbox': [x1, y1, x2, y2],
                    'confidence': 0.9,
                    'id': i
                })
                
                if person['fallen']:
                    fall_detected = True
                    fall_bbox = [x1, y1, x2, y2]
            
            # Draw everything
            processed_frame = self.draw_detections(
                frame, detections, len(detections), fall_detected, fall_bbox
            )
            
            # Update status
            with self.status_lock:
                self.status['count'] = len(detections)
                self.status['fall'] = fall_detected
                self.status['timestamp'] = datetime.now().isoformat()
            
            # Add to queue
            if self.frame_queue.full():
                self.frame_queue.get()
            self.frame_queue.put(processed_frame)
            
            time.sleep(0.033)  # ~30 FPS
    
    def start_video_file(self, file_path):
        """Start processing video file"""
        self.running = True
        self.process_thread = Thread(target=self.process_video_file, args=(file_path,))
        self.process_thread.start()
    
    def start_ip_camera(self, ip_url):
        """Start processing IP camera"""
        self.running = True
        self.process_thread = Thread(target=self.process_ip_camera, args=(ip_url,))
        self.process_thread.start()
    
    def stop(self):
        """Stop processing"""
        self.running = False
        if self.process_thread:
            self.process_thread.join(timeout=2)
        # Clear queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                pass