let currentCamera = 1;
let alerts = [];
let totalPeople = 0;
let fallIncidents = 0;
let maxCrowd = 0;
let activeCameras = 0;

// Initialize video feeds
$(document).ready(function() {
    // Start video feeds for all cameras
    for (let i = 1; i <= 4; i++) {
        startVideoFeed(i);
    }
    
    // Start status updates
    setInterval(updateSystemStatus, 2000);
    
    // Add initial alert
    addAlert('System started successfully. Ready to monitor.', 'info');
});

function startVideoFeed(cameraId) {
    const img = document.getElementById(`feed-${cameraId}`);
    img.src = `/test_feed/${cameraId}`;
}

function openCameraMenu(cameraId) {
    // Close all other menus
    for (let i = 1; i <= 4; i++) {
        if (i !== cameraId) {
            document.getElementById(`menu-${i}`).classList.remove('show');
        }
    }
    
    // Toggle current menu
    const menu = document.getElementById(`menu-${cameraId}`);
    menu.classList.toggle('show');
}

// Close menus when clicking elsewhere
document.addEventListener('click', function(event) {
    if (!event.target.closest('.camera-controls')) {
        for (let i = 1; i <= 4; i++) {
            document.getElementById(`menu-${i}`).classList.remove('show');
        }
    }
});

function uploadVideo(event, cameraId) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('camera_id', cameraId);
    
    $.ajax({
        url: '/upload',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function(response) {
            if (response.success) {
                updateCameraStatus(cameraId, 'video_file', file.name);
                addAlert(`Video uploaded to Camera ${cameraId}: ${file.name}`, 'info');
            }
        },
        error: function(xhr) {
            addAlert(`Failed to upload video to Camera ${cameraId}`, 'danger');
        }
    });
}

function connectIPCamera(cameraId) {
    currentCamera = cameraId;
    document.getElementById('cameraId').value = cameraId;
    document.getElementById('ipModal').classList.add('show');
}

function closeModal() {
    document.getElementById('ipModal').classList.remove('show');
}

function connectCamera() {
    const cameraId = document.getElementById('cameraId').value;
    let ipAddress = document.getElementById('ipAddress').value.trim();
    const port = document.getElementById('port').value.trim() || '80';
    
    // If no IP provided, use simulated feed
    if (!ipAddress) {
        ipAddress = 'simulated';
    }
    
    const fullUrl = ipAddress === 'simulated' ? 'simulated' : `http://${ipAddress}:${port}`;
    
    $.ajax({
        url: '/set_ip',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            camera_id: parseInt(cameraId),
            ip: fullUrl
        }),
        success: function(response) {
            if (response.success) {
                updateCameraStatus(cameraId, 'ip_camera', fullUrl);
                addAlert(`IP Camera connected to Camera ${cameraId}`, 'info');
                closeModal();
            }
        },
        error: function(xhr) {
            addAlert(`Failed to connect IP Camera to Camera ${cameraId}`, 'danger');
        }
    });
}

function closeCamera(cameraId) {
    $.ajax({
        url: `/close_camera/${cameraId}`,
        type: 'POST',
        success: function(response) {
            if (response.success) {
                updateCameraStatus(cameraId, 'offline', null);
                addAlert(`Camera ${cameraId} turned off`, 'info');
            }
        },
        error: function(xhr) {
            addAlert(`Failed to turn off Camera ${cameraId}`, 'danger');
        }
    });
}

function updateCameraStatus(cameraId, type, url) {
    const statusElement = document.getElementById(`status-${cameraId}`);
    const statusText = type === 'offline' ? 'Offline' : 
                      type === 'ip_camera' ? 'IP Camera' : 'Video File';
    const statusClass = type === 'offline' ? 'status-offline' : 'status-online';
    
    statusElement.textContent = statusText;
    statusElement.className = statusClass;
}

function updateSystemStatus() {
    $.ajax({
        url: '/status',
        type: 'GET',
        success: function(data) {
            updateDashboard(data);
        },
        error: function(xhr) {
            console.error('Failed to get system status');
        }
    });
}

function updateDashboard(cameraData) {
    let total = 0;
    let active = 0;
    let falls = 0;
    let max = 0;
    
    for (let i = 1; i <= 4; i++) {
        const cam = cameraData[i] || { count: 0, fall: false };
        
        // Update camera display
        const countElement = document.getElementById(`count-${i}`);
        const alertElement = document.getElementById(`alert-${i}`);
        
        if (countElement) {
            countElement.textContent = `${cam.count} people`;
        }
        
        if (alertElement) {
            if (cam.fall) {
                alertElement.textContent = 'FALL DETECTED!';
                alertElement.style.display = 'block';
                
                // Check if this fall is new
                if (!alerts.some(a => a.camera === i && a.type === 'fall')) {
                    addAlert(`Fall detected on Camera ${i}! Immediate attention required.`, 'danger', i);
                }
            } else {
                alertElement.textContent = '';
                alertElement.style.display = 'none';
            }
        }
        
        // Update totals
        total += cam.count;
        if (cam.count > 0 || cameraData[i]?.type !== 'offline') {
            active++;
        }
        if (cam.fall) falls++;
        max = Math.max(max, cam.count);
    }
    
    // Update dashboard
    totalPeople = total;
    activeCameras = active;
    fallIncidents = falls;
    maxCrowd = Math.max(maxCrowd, max);
    
    document.getElementById('total-people').textContent = total;
    document.getElementById('active-cameras').textContent = `${active}/4`;
    document.getElementById('fall-incidents').textContent = falls;
    document.getElementById('max-crowd').textContent = maxCrowd;
}

function addAlert(message, type, camera = null) {
    const alert = {
        id: Date.now(),
        message: message,
        type: type,
        camera: camera,
        time: new Date().toLocaleTimeString()
    };
    
    alerts.unshift(alert); // Add to beginning
    
    // Keep only last 10 alerts
    if (alerts.length > 10) {
        alerts.pop();
    }
    
    // Update alerts list
    updateAlertsList();
}

function updateAlertsList() {
    const list = document.getElementById('alerts-list');
    list.innerHTML = '';
    
    alerts.forEach(alert => {
        const alertItem = document.createElement('div');
        alertItem.className = `alert-item ${alert.type}`;
        
        let icon = 'fa-info-circle';
        if (alert.type === 'warning') icon = 'fa-exclamation-triangle';
        if (alert.type === 'danger') icon = 'fa-exclamation-circle';
        
        alertItem.innerHTML = `
            <i class="fas ${icon}"></i>
            <div class="alert-content">
                <p>${alert.message}</p>
                <span class="alert-time">${alert.time}</span>
            </div>
        `;
        
        list.appendChild(alertItem);
    });
}

function clearAlerts() {
    alerts = [];
    updateAlertsList();
    addAlert('All alerts cleared', 'info');
}

// Add sample alert for demonstration
setTimeout(() => {
    addAlert('System calibration complete. All features active.', 'info');
}, 2000);

setTimeout(() => {
    addAlert('High crowd density detected on Camera 1. Monitoring closely.', 'warning', 1);
}, 5000);