/**
 * SF-NVR Timeline Selector
 * Interactive 24-hour timeline with event visualization for selecting playback ranges
 */

class TimelineSelector {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Timeline selector container '${containerId}' not found`);
            return;
        }

        this.options = {
            height: options.height || 150,
            onRangeSelected: options.onRangeSelected || null,
            cameras: options.cameras || [],
            date: options.date || new Date(),
            showHeatmap: options.showHeatmap !== false,
            showMotionBars: options.showMotionBars !== false,
            showRecordingSegments: options.showRecordingSegments !== false,
            ...options
        };

        this.state = {
            segments: [],
            motionEvents: [],
            aiEvents: [],
            bookmarks: [],
            startSelection: null,
            endSelection: null,
            isSelecting: false,
            hoveredTime: null
        };

        this.init();
    }

    init() {
        this.render();
        this.attachEvents();
        this.loadData();
    }

    render() {
        this.container.innerHTML = `
            <div class="timeline-selector">
                <div class="timeline-selector-header">
                    <h3>Select Playback Range</h3>
                    <div class="timeline-selector-info">
                        <span id="timeline-selection-info">Click and drag to select time range</span>
                    </div>
                </div>

                <div class="timeline-canvas-container">
                    <!-- 24-hour timeline with event overlay -->
                    <canvas id="timeline-canvas" class="timeline-canvas"></canvas>

                    <!-- Time labels -->
                    <div class="timeline-labels" id="timeline-labels"></div>

                    <!-- Selection overlay -->
                    <div class="timeline-selection-overlay" id="timeline-selection-overlay"></div>

                    <!-- Hover indicator -->
                    <div class="timeline-hover-indicator" id="timeline-hover-indicator"></div>

                    <!-- Tooltip -->
                    <div class="timeline-tooltip" id="timeline-tooltip"></div>
                </div>

                <div class="timeline-selector-legend">
                    <div class="legend-item">
                        <div class="legend-color" style="background: #4a9eff;"></div>
                        <span>Recordings</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ff4a4a;"></div>
                        <span>Motion</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #4caf50;"></div>
                        <span>Person</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #2196f3;"></div>
                        <span>Vehicle</span>
                    </div>
                </div>

                <div class="timeline-selector-actions">
                    <button class="btn btn-secondary" onclick="timelineSelector.clearSelection()">Clear</button>
                    <button class="btn btn-primary" onclick="timelineSelector.applySelection()" id="apply-selection-btn" disabled>
                        Load Playback
                    </button>
                </div>
            </div>
        `;

        this.initCanvas();
        this.renderTimeLabels();
    }

    initCanvas() {
        this.canvas = document.getElementById('timeline-canvas');
        this.ctx = this.canvas.getContext('2d');

        // Set canvas size
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = this.options.height * window.devicePixelRatio;
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = this.options.height + 'px';

        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }

    renderTimeLabels() {
        const labelsContainer = document.getElementById('timeline-labels');
        labelsContainer.innerHTML = '';

        // Generate 24 hour labels (every 2 hours)
        for (let hour = 0; hour <= 24; hour += 2) {
            const label = document.createElement('div');
            label.className = 'timeline-label';
            label.style.left = ((hour / 24) * 100) + '%';
            label.textContent = hour === 24 ? '12 AM' : this.formatHour(hour);
            labelsContainer.appendChild(label);
        }
    }

    formatHour(hour) {
        if (hour === 0) return '12 AM';
        if (hour === 12) return '12 PM';
        if (hour < 12) return hour + ' AM';
        return (hour - 12) + ' PM';
    }

    attachEvents() {
        // Mouse events for selection
        this.canvas.addEventListener('mousedown', this.onMouseDown.bind(this));
        this.canvas.addEventListener('mousemove', this.onMouseMove.bind(this));
        this.canvas.addEventListener('mouseup', this.onMouseUp.bind(this));
        this.canvas.addEventListener('mouseleave', this.onMouseLeave.bind(this));

        // Touch events for mobile
        this.canvas.addEventListener('touchstart', this.onTouchStart.bind(this));
        this.canvas.addEventListener('touchmove', this.onTouchMove.bind(this));
        this.canvas.addEventListener('touchend', this.onTouchEnd.bind(this));

        // Window resize
        window.addEventListener('resize', debounce(() => {
            this.initCanvas();
            this.drawTimeline();
        }, 250));
    }

    getMaxAllowedPercent() {
        // If viewing today, limit selection to current time
        const now = new Date();
        const selectedDate = new Date(this.options.date);

        // Check if selected date is today
        const isToday = now.toDateString() === selectedDate.toDateString();

        if (isToday) {
            // Calculate percentage of day that has passed
            const hoursNow = now.getHours() + now.getMinutes() / 60 + now.getSeconds() / 3600;
            return hoursNow / 24;
        }

        // For past dates, allow full 24 hours
        return 1.0;
    }

    onMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const maxPercent = this.getMaxAllowedPercent();
        const percent = Math.min(x / rect.width, maxPercent);

        this.state.isSelecting = true;
        this.state.startSelection = percent;
        this.state.endSelection = percent;

        this.updateSelectionOverlay();
    }

    onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const maxPercent = this.getMaxAllowedPercent();
        const percent = Math.max(0, Math.min(maxPercent, x / rect.width));

        // Update hover indicator
        this.state.hoveredTime = percent;
        this.updateHoverIndicator(e.clientX, e.clientY);

        // Update selection if dragging
        if (this.state.isSelecting) {
            this.state.endSelection = percent;
            this.updateSelectionOverlay();
        }
    }

    onMouseUp(e) {
        if (this.state.isSelecting) {
            this.state.isSelecting = false;

            // Enforce future limit on final selection
            const maxPercent = this.getMaxAllowedPercent();
            this.state.startSelection = Math.min(this.state.startSelection, maxPercent);
            this.state.endSelection = Math.min(this.state.endSelection, maxPercent);

            // Normalize selection (ensure start < end)
            if (this.state.startSelection > this.state.endSelection) {
                [this.state.startSelection, this.state.endSelection] =
                    [this.state.endSelection, this.state.startSelection];
            }

            // Minimum 1 minute selection
            const minSelection = 1 / (24 * 60); // 1 minute
            if (Math.abs(this.state.endSelection - this.state.startSelection) < minSelection) {
                this.clearSelection();
                showNotification('Selection too small. Minimum 1 minute range required.', 'warning');
                return;
            }

            this.updateSelectionInfo();
            document.getElementById('apply-selection-btn').disabled = false;

            // Auto-load playback on drag release
            this.applySelection();
        }
    }

    onMouseLeave(e) {
        this.state.hoveredTime = null;
        this.hideHoverIndicator();
    }

    onTouchStart(e) {
        e.preventDefault();
        const touch = e.touches[0];
        const mouseEvent = new MouseEvent('mousedown', {
            clientX: touch.clientX,
            clientY: touch.clientY
        });
        this.canvas.dispatchEvent(mouseEvent);
    }

    onTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        const mouseEvent = new MouseEvent('mousemove', {
            clientX: touch.clientX,
            clientY: touch.clientY
        });
        this.canvas.dispatchEvent(mouseEvent);
    }

    onTouchEnd(e) {
        e.preventDefault();
        const mouseEvent = new MouseEvent('mouseup', {});
        this.canvas.dispatchEvent(mouseEvent);
    }

    updateHoverIndicator(clientX, clientY) {
        const indicator = document.getElementById('timeline-hover-indicator');
        const tooltip = document.getElementById('timeline-tooltip');
        const rect = this.canvas.getBoundingClientRect();

        indicator.style.left = (clientX - rect.left) + 'px';
        indicator.style.display = 'block';

        // Show time tooltip
        const time = this.percentToTime(this.state.hoveredTime);
        tooltip.textContent = this.formatTime(time);
        tooltip.style.left = (clientX - rect.left) + 'px';
        tooltip.style.top = (clientY - rect.top - 30) + 'px';
        tooltip.style.display = 'block';
    }

    hideHoverIndicator() {
        document.getElementById('timeline-hover-indicator').style.display = 'none';
        document.getElementById('timeline-tooltip').style.display = 'none';
    }

    updateSelectionOverlay() {
        const overlay = document.getElementById('timeline-selection-overlay');

        if (this.state.startSelection === null || this.state.endSelection === null) {
            overlay.style.display = 'none';
            return;
        }

        const start = Math.min(this.state.startSelection, this.state.endSelection);
        const end = Math.max(this.state.startSelection, this.state.endSelection);

        overlay.style.left = (start * 100) + '%';
        overlay.style.width = ((end - start) * 100) + '%';
        overlay.style.display = 'block';
    }

    updateSelectionInfo() {
        const info = document.getElementById('timeline-selection-info');

        if (this.state.startSelection === null || this.state.endSelection === null) {
            info.textContent = 'Click and drag to select time range';
            return;
        }

        const startTime = this.percentToTime(this.state.startSelection);
        const endTime = this.percentToTime(this.state.endSelection);
        const duration = (endTime - startTime) / 1000; // seconds

        info.innerHTML = `
            <strong>Selected:</strong>
            ${this.formatTime(startTime)} - ${this.formatTime(endTime)}
            <span style="color: #4a9eff;">(${formatDuration(duration)})</span>
        `;
    }

    percentToTime(percent) {
        const date = new Date(this.options.date);
        date.setHours(0, 0, 0, 0);
        return date.getTime() + (percent * 24 * 60 * 60 * 1000);
    }

    timeToPercent(timestamp) {
        const date = new Date(this.options.date);
        date.setHours(0, 0, 0, 0);
        const dayStart = date.getTime();
        const dayEnd = dayStart + (24 * 60 * 60 * 1000);

        return (timestamp - dayStart) / (dayEnd - dayStart);
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    }

    async loadData() {
        const loading = showLoading('Loading timeline data...');

        try {
            // Load segments
            await this.loadSegments();

            // Load motion events
            await this.loadMotionEvents();

            // Load AI events
            await this.loadAIEvents();

            // Load bookmarks
            await this.loadBookmarks();

            // Draw timeline
            this.drawTimeline();

            loading.dismiss();
            showNotification('Timeline loaded successfully', 'success');
        } catch (error) {
            console.error('Error loading timeline data:', error);
            loading.dismiss();
            showNotification('Error loading timeline data', 'error');
        }
    }

    async loadSegments() {
        const date = this.options.date;
        const dateStr = date.toISOString().split('T')[0];

        // Format as YYYY-MM-DDTHH:MM:SS (no timezone suffix, matching existing API usage)
        const startTimeStr = `${dateStr}T00:00:00`;
        const endTimeStr = `${dateStr}T23:59:59`;

        const response = await fetch(
            `/api/playback/recordings?start_time=${encodeURIComponent(startTimeStr)}&end_time=${encodeURIComponent(endTimeStr)}`
        );

        if (!response.ok) throw new Error('Failed to load segments');

        const data = await response.json();

        // Convert response format: { cameras: { camera_name: [segments], ... } }
        // to flat array of segments with camera_name field
        this.state.segments = [];
        if (data.cameras) {
            Object.entries(data.cameras).forEach(([cameraName, segments]) => {
                // Only include selected cameras
                if (this.options.cameras.includes(cameraName)) {
                    segments.forEach(segment => {
                        this.state.segments.push({
                            ...segment,
                            camera_name: cameraName
                        });
                    });
                }
            });
        }
    }

    async loadMotionEvents() {
        const date = this.options.date;
        const dateStr = date.toISOString().split('T')[0];

        // Format as YYYY-MM-DDTHH:MM:SS (no timezone suffix)
        const startTimeStr = `${dateStr}T00:00:00`;
        const endTimeStr = `${dateStr}T23:59:59`;

        // Use aggregated data for much faster loading (returns counts per 5-min bucket instead of individual events)
        const response = await fetch(
            `/api/playback/motion-events?start_time=${encodeURIComponent(startTimeStr)}&end_time=${encodeURIComponent(endTimeStr)}&aggregate=true`
        );

        if (!response.ok) throw new Error('Failed to load motion events');

        const data = await response.json();

        // Convert aggregated response format: { cameras: { camera_name: [{bucket_time, count, avg_intensity}], ... } }
        // to flat array for rendering
        this.state.motionEvents = [];
        this.state.aggregatedMotion = true;  // Flag that we have aggregated data
        if (data.cameras) {
            Object.entries(data.cameras).forEach(([cameraName, buckets]) => {
                // Only include selected cameras
                if (this.options.cameras.includes(cameraName)) {
                    buckets.forEach(bucket => {
                        this.state.motionEvents.push({
                            event_time: bucket.bucket_time,
                            count: bucket.count,
                            intensity: bucket.avg_intensity,
                            camera_name: cameraName
                        });
                    });
                }
            });
        }
    }

    async loadAIEvents() {
        const date = this.options.date;
        const dateStr = date.toISOString().split('T')[0];

        // Format as YYYY-MM-DDTHH:MM:SS (no timezone suffix)
        const startTimeStr = `${dateStr}T00:00:00`;
        const endTimeStr = `${dateStr}T23:59:59`;

        const response = await fetch(
            `/api/playback/motion-events?start_time=${encodeURIComponent(startTimeStr)}&end_time=${encodeURIComponent(endTimeStr)}`
        );

        if (!response.ok) {
            // AI events are optional
            this.state.aiEvents = [];
            return;
        }

        const data = await response.json();

        // Filter for AI events (event_type contains 'ai_')
        this.state.aiEvents = [];
        if (data.cameras) {
            Object.entries(data.cameras).forEach(([cameraName, events]) => {
                // Only include selected cameras
                if (this.options.cameras.includes(cameraName)) {
                    events.forEach(event => {
                        // Check if this is an AI event
                        if (event.event_type && (event.event_type === 'ai_person' || event.event_type === 'ai_vehicle')) {
                            this.state.aiEvents.push({
                                ...event,
                                camera_name: cameraName
                            });
                        }
                    });
                }
            });
        }
    }

    async loadBookmarks() {
        const date = this.options.date;
        const dateStr = date.toISOString().split('T')[0];

        // Format as YYYY-MM-DDTHH:MM:SS (no timezone suffix)
        const startTimeStr = `${dateStr}T00:00:00`;
        const endTimeStr = `${dateStr}T23:59:59`;

        const response = await fetch(
            `/api/playback/bookmarks?start_time=${encodeURIComponent(startTimeStr)}&end_time=${encodeURIComponent(endTimeStr)}`
        );

        if (!response.ok) {
            this.state.bookmarks = [];
            return;
        }

        const data = await response.json();

        // Filter bookmarks for selected cameras only
        this.state.bookmarks = [];
        if (data.bookmarks) {
            data.bookmarks.forEach(bookmark => {
                if (this.options.cameras.includes(bookmark.camera_name)) {
                    this.state.bookmarks.push(bookmark);
                }
            });
        }
    }

    drawTimeline() {
        const width = this.canvas.width / window.devicePixelRatio;
        const height = this.canvas.height / window.devicePixelRatio;

        // Clear canvas
        this.ctx.clearRect(0, 0, width, height);

        // Draw background
        this.ctx.fillStyle = '#1a1a1a';
        this.ctx.fillRect(0, 0, width, height);

        // Draw hour grid lines
        this.drawGridLines(width, height);

        // Draw recording segments (green bars)
        if (this.options.showRecordingSegments) {
            this.drawRecordingSegments(width, height);
        }

        // Draw motion heatmap (orange gradient)
        if (this.options.showHeatmap) {
            this.drawMotionHeatmap(width, height);
        }

        // Draw motion bars (orange spikes)
        if (this.options.showMotionBars) {
            this.drawMotionBars(width, height);
        }

        // Draw AI detections (purple markers)
        this.drawAIDetections(width, height);

        // Draw bookmarks (yellow stars)
        this.drawBookmarks(width, height);

        // Draw future zone overlay (grayed out area for times that haven't happened yet)
        this.drawFutureZone(width, height);
    }

    drawFutureZone(width, height) {
        const maxPercent = this.getMaxAllowedPercent();

        // Only draw if viewing today and there's future time to block
        if (maxPercent < 1.0) {
            const futureX = maxPercent * width;

            // Draw semi-transparent overlay over future time
            this.ctx.fillStyle = 'rgba(30, 30, 30, 0.7)';
            this.ctx.fillRect(futureX, 0, width - futureX, height);

            // Draw "NOW" marker line
            this.ctx.strokeStyle = '#ff9800';
            this.ctx.lineWidth = 2;
            this.ctx.setLineDash([5, 3]);
            this.ctx.beginPath();
            this.ctx.moveTo(futureX, 0);
            this.ctx.lineTo(futureX, height);
            this.ctx.stroke();
            this.ctx.setLineDash([]);

            // Draw "NOW" label
            this.ctx.fillStyle = '#ff9800';
            this.ctx.font = '10px sans-serif';
            this.ctx.textAlign = 'center';
            this.ctx.fillText('NOW', futureX, 12);
        }
    }

    drawGridLines(width, height) {
        this.ctx.strokeStyle = '#333';
        this.ctx.lineWidth = 1;

        // Draw vertical lines every hour
        for (let hour = 0; hour <= 24; hour++) {
            const x = (hour / 24) * width;

            this.ctx.beginPath();
            this.ctx.moveTo(x, 0);
            this.ctx.lineTo(x, height);
            this.ctx.stroke();

            // Draw thicker line every 6 hours
            if (hour % 6 === 0) {
                this.ctx.strokeStyle = '#444';
                this.ctx.lineWidth = 2;
                this.ctx.stroke();
                this.ctx.strokeStyle = '#333';
                this.ctx.lineWidth = 1;
            }
        }
    }

    drawRecordingSegments(width, height) {
        this.ctx.fillStyle = 'rgba(74, 158, 255, 0.4)';  // Blue to match playback

        this.state.segments.forEach(segment => {
            const startPercent = this.timeToPercent(new Date(segment.start_time).getTime());
            const endPercent = this.timeToPercent(new Date(segment.end_time).getTime());

            if (startPercent >= 0 && startPercent <= 1) {
                const x = startPercent * width;
                const w = (endPercent - startPercent) * width;

                this.ctx.fillRect(x, 0, w, height);
            }
        });
    }

    drawMotionHeatmap(width, height) {
        // Data is already aggregated in 5-minute buckets from server
        const bucketSize = 5 * 60 * 1000; // 5 minutes in ms
        const buckets = new Map();

        this.state.motionEvents.forEach(event => {
            const timestamp = new Date(event.event_time).getTime();
            const bucketIndex = Math.floor((timestamp - this.percentToTime(0)) / bucketSize);
            // Use pre-aggregated count if available, otherwise count as 1
            const count = event.count || 1;
            buckets.set(bucketIndex, (buckets.get(bucketIndex) || 0) + count);
        });

        // Find max count for normalization
        const maxCount = Math.max(...Array.from(buckets.values()), 1);

        // Draw heatmap
        buckets.forEach((count, bucketIndex) => {
            const startTime = this.percentToTime(0) + (bucketIndex * bucketSize);
            const startPercent = this.timeToPercent(startTime);
            const widthPercent = bucketSize / (24 * 60 * 60 * 1000);

            const x = startPercent * width;
            const w = widthPercent * width;

            const intensity = count / maxCount;
            const alpha = 0.2 + (intensity * 0.4); // 0.2 to 0.6

            this.ctx.fillStyle = `rgba(255, 74, 74, ${alpha})`;  // Red to match playback
            this.ctx.fillRect(x, height * 0.3, w, height * 0.4);
        });
    }

    drawMotionBars(width, height) {
        // Data is pre-aggregated in 5-minute buckets, use same bucket size for display
        const bucketSize = 5 * 60 * 1000; // 5 minutes (matching server aggregation)
        const buckets = new Map();

        this.state.motionEvents.forEach(event => {
            const timestamp = new Date(event.event_time).getTime();
            const bucketIndex = Math.floor((timestamp - this.percentToTime(0)) / bucketSize);
            // Use pre-aggregated count if available, otherwise count as 1
            const count = event.count || 1;
            buckets.set(bucketIndex, (buckets.get(bucketIndex) || 0) + count);
        });

        // Find max for normalization
        const maxCount = Math.max(...Array.from(buckets.values()), 1);

        // Draw bars
        buckets.forEach((count, bucketIndex) => {
            const startTime = this.percentToTime(0) + (bucketIndex * bucketSize);
            const startPercent = this.timeToPercent(startTime);
            const widthPercent = bucketSize / (24 * 60 * 60 * 1000);

            const x = startPercent * width;
            const w = Math.max(2, widthPercent * width);

            const barHeight = (count / maxCount) * height * 0.6;

            this.ctx.fillStyle = 'rgba(255, 74, 74, 0.8)';  // Red to match playback
            this.ctx.fillRect(x, height - barHeight, w, barHeight);
        });
    }

    drawAIDetections(width, height) {
        this.state.aiEvents.forEach(event => {
            const timestamp = new Date(event.event_time).getTime();
            const percent = this.timeToPercent(timestamp);

            if (percent >= 0 && percent <= 1) {
                const x = percent * width;

                // Color by event type to match playback page
                const eventType = (event.event_type || '').toLowerCase();
                if (eventType.includes('person')) {
                    this.ctx.fillStyle = 'rgba(76, 175, 80, 0.9)';  // Green for person
                } else if (eventType.includes('vehicle') || eventType.includes('car')) {
                    this.ctx.fillStyle = 'rgba(33, 150, 243, 0.9)';  // Blue for vehicle
                } else {
                    this.ctx.fillStyle = 'rgba(156, 39, 176, 0.9)';  // Purple for other AI
                }

                // Draw vertical line
                this.ctx.fillRect(x - 1, 0, 3, height);

                // Draw triangle marker at top
                this.ctx.beginPath();
                this.ctx.moveTo(x, 0);
                this.ctx.lineTo(x - 5, 10);
                this.ctx.lineTo(x + 5, 10);
                this.ctx.closePath();
                this.ctx.fill();
            }
        });
    }

    drawBookmarks(width, height) {
        this.ctx.fillStyle = 'rgba(255, 193, 7, 0.9)';

        this.state.bookmarks.forEach(bookmark => {
            const timestamp = new Date(bookmark.timestamp).getTime();
            const percent = this.timeToPercent(timestamp);

            if (percent >= 0 && percent <= 1) {
                const x = percent * width;
                const y = 15;
                const size = 8;

                // Draw star
                this.drawStar(x, y, size, 5, 0.5);
            }
        });
    }

    drawStar(cx, cy, outerRadius, points, innerRadiusRatio) {
        const innerRadius = outerRadius * innerRadiusRatio;
        const angle = Math.PI / points;

        this.ctx.beginPath();

        for (let i = 0; i < points * 2; i++) {
            const radius = i % 2 === 0 ? outerRadius : innerRadius;
            const x = cx + Math.cos(i * angle - Math.PI / 2) * radius;
            const y = cy + Math.sin(i * angle - Math.PI / 2) * radius;

            if (i === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        }

        this.ctx.closePath();
        this.ctx.fill();
    }

    clearSelection() {
        this.state.startSelection = null;
        this.state.endSelection = null;
        this.updateSelectionOverlay();
        this.updateSelectionInfo();
        document.getElementById('apply-selection-btn').disabled = true;
    }

    applySelection() {
        if (this.state.startSelection === null || this.state.endSelection === null) {
            showNotification('No time range selected', 'warning');
            return;
        }

        const startTime = this.percentToTime(this.state.startSelection);
        const endTime = this.percentToTime(this.state.endSelection);

        if (this.options.onRangeSelected) {
            this.options.onRangeSelected({
                startTime: new Date(startTime),
                endTime: new Date(endTime)
            });
        }
    }

    setDate(date) {
        this.options.date = date;
        this.clearSelection();
        this.loadData();
    }

    setCameras(cameras) {
        this.options.cameras = cameras;
        this.clearSelection();
        this.loadData();
    }

    refresh() {
        this.clearSelection();
        this.loadData();
    }
}

// Add CSS for timeline selector
if (!document.getElementById('timeline-selector-styles')) {
    const style = document.createElement('style');
    style.id = 'timeline-selector-styles';
    style.textContent = `
        .timeline-selector {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }

        .timeline-selector-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .timeline-selector-header h3 {
            color: #4a9eff;
            margin: 0;
        }

        .timeline-selector-info {
            color: #888;
            font-size: 0.9em;
        }

        .timeline-canvas-container {
            position: relative;
            background: #1a1a1a;
            border-radius: 6px;
            margin-bottom: 15px;
            padding: 10px 0;
        }

        .timeline-canvas {
            display: block;
            width: 100%;
            cursor: crosshair;
            border-radius: 6px;
        }

        .timeline-labels {
            position: relative;
            height: 20px;
            margin-top: 5px;
        }

        .timeline-label {
            position: absolute;
            transform: translateX(-50%);
            font-size: 0.75em;
            color: #666;
            white-space: nowrap;
        }

        .timeline-selection-overlay {
            position: absolute;
            top: 10px;
            bottom: 25px;
            background: rgba(74, 158, 255, 0.3);
            border: 2px solid #4a9eff;
            border-radius: 4px;
            pointer-events: none;
            display: none;
        }

        .timeline-hover-indicator {
            position: absolute;
            top: 10px;
            bottom: 25px;
            width: 2px;
            background: rgba(255, 255, 255, 0.5);
            pointer-events: none;
            display: none;
        }

        .timeline-tooltip {
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 0.85em;
            pointer-events: none;
            display: none;
            transform: translateX(-50%);
            white-space: nowrap;
            z-index: 100;
        }

        .timeline-selector-legend {
            display: flex;
            gap: 20px;
            justify-content: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85em;
            color: #aaa;
        }

        .legend-color {
            width: 20px;
            height: 12px;
            border-radius: 2px;
        }

        .timeline-selector-actions {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
        }

        @media (max-width: 768px) {
            .timeline-selector-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }

            .timeline-selector-legend {
                gap: 10px;
            }

            .legend-item {
                font-size: 0.75em;
            }
        }
    `;
    document.head.appendChild(style);
}
