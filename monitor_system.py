#!/usr/bin/env python3
"""
Continuous system monitoring for SF-NVR
Monitors: disk space, memory, CPU, camera streams, errors in logs, and system health
"""

import os
import sys
import time
import psutil
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration
CHECK_INTERVAL = 30  # seconds between checks
LOG_FILE = "system_monitor.log"
NVR_LOG_FILE = "nvr.log"
DISK_WARNING_THRESHOLD = 85  # percentage
DISK_CRITICAL_THRESHOLD = 95  # percentage
MEMORY_WARNING_THRESHOLD = 90  # percentage
CPU_WARNING_THRESHOLD = 95  # percentage (sustained)
ERROR_CHECK_LINES = 100  # number of log lines to check

class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def log(message, level="INFO", color=None):
    """Log message to both console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] [{level}] {message}"

    # Write to file
    with open(LOG_FILE, "a") as f:
        f.write(log_msg + "\n")

    # Print to console with color
    if color:
        print(f"{color}{log_msg}{Colors.END}")
    else:
        print(log_msg)

def check_nvr_process():
    """Check if NVR process is running"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'main.py' in ' '.join(cmdline):
                return {
                    'running': True,
                    'pid': proc.info['pid'],
                    'cpu_percent': proc.cpu_percent(interval=0.1),
                    'memory_percent': proc.memory_percent(),
                    'memory_mb': proc.memory_info().rss / 1024 / 1024
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {'running': False}

def check_disk_space():
    """Check disk space for recordings directory"""
    recordings_path = Path("./recordings")
    if recordings_path.exists():
        usage = psutil.disk_usage(recordings_path)
        return {
            'total_gb': usage.total / (1024**3),
            'used_gb': usage.used / (1024**3),
            'free_gb': usage.free / (1024**3),
            'percent': usage.percent
        }
    else:
        # Fall back to current directory
        usage = psutil.disk_usage(".")
        return {
            'total_gb': usage.total / (1024**3),
            'used_gb': usage.used / (1024**3),
            'free_gb': usage.free / (1024**3),
            'percent': usage.percent
        }

def check_system_resources():
    """Check overall system resources"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()

    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_used_gb': memory.used / (1024**3),
        'memory_total_gb': memory.total / (1024**3)
    }

def check_recent_errors():
    """Check for recent errors in NVR log"""
    if not os.path.exists(NVR_LOG_FILE):
        return []

    errors = []
    try:
        # Read last N lines
        with open(NVR_LOG_FILE, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-ERROR_CHECK_LINES:] if len(lines) > ERROR_CHECK_LINES else lines

        # Look for ERROR or CRITICAL
        for line in recent_lines:
            if 'ERROR' in line or 'CRITICAL' in line:
                # Skip known non-critical errors
                if 'devicemgmt.wsdl' in line:  # ONVIF discovery errors are non-critical
                    continue
                errors.append(line.strip())

        return errors
    except Exception as e:
        return [f"Error reading log file: {e}"]

def check_camera_streams():
    """Check if camera streams are active by looking at recent log entries"""
    if not os.path.exists(NVR_LOG_FILE):
        return {'status': 'unknown', 'details': 'Log file not found'}

    try:
        with open(NVR_LOG_FILE, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-50:] if len(lines) > 50 else lines

        # Look for "Stream opened" or "Started new segment" messages
        active_cameras = set()
        for line in recent_lines:
            if 'Stream opened' in line or 'Started new segment' in line:
                # Extract camera name from log line
                for camera in ['Alley', 'Patio Gate', 'Tool Room', 'Liquor Storage', 'Patio']:
                    if camera in line:
                        active_cameras.add(camera)

        return {
            'status': 'active' if active_cameras else 'no_recent_activity',
            'active_cameras': list(active_cameras),
            'count': len(active_cameras)
        }
    except Exception as e:
        return {'status': 'error', 'details': str(e)}

def check_recording_size():
    """Check total size of recordings directory"""
    recordings_path = Path("./recordings")
    if not recordings_path.exists():
        return {'total_gb': 0, 'status': 'not_found'}

    try:
        # Use du command for accurate size (faster than Python walking)
        result = subprocess.run(
            ['du', '-sh', str(recordings_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        size_str = result.stdout.split()[0]

        return {
            'size_str': size_str,
            'status': 'ok'
        }
    except Exception as e:
        return {'status': 'error', 'details': str(e)}

def display_status_dashboard(nvr_proc, disk, system, cameras, recordings, errors):
    """Display a formatted status dashboard"""
    # Clear screen (optional - comment out if you want scrolling history)
    # os.system('clear' if os.name != 'nt' else 'cls')

    print("\n" + "="*80)
    print(f"{Colors.BOLD}{Colors.CYAN}SF-NVR System Monitor{Colors.END}".center(90))
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(80))
    print("="*80 + "\n")

    # NVR Process Status
    print(f"{Colors.BOLD}NVR Process Status:{Colors.END}")
    if nvr_proc['running']:
        print(f"  {Colors.GREEN}✓ Running{Colors.END} (PID: {nvr_proc['pid']})")
        print(f"    CPU: {nvr_proc['cpu_percent']:.1f}%  |  Memory: {nvr_proc['memory_mb']:.1f} MB ({nvr_proc['memory_percent']:.1f}%)")
    else:
        log("NVR process is NOT running!", "CRITICAL", Colors.RED)
        print(f"  {Colors.RED}✗ NOT RUNNING{Colors.END}")
    print()

    # Camera Streams
    print(f"{Colors.BOLD}Camera Streams:{Colors.END}")
    if cameras['status'] == 'active':
        print(f"  {Colors.GREEN}✓ Active{Colors.END} - {cameras['count']} camera(s) streaming")
        for cam in cameras['active_cameras']:
            print(f"    • {cam}")
    else:
        print(f"  {Colors.YELLOW}⚠ {cameras['status']}{Colors.END}")
    print()

    # Disk Space
    print(f"{Colors.BOLD}Disk Space:{Colors.END}")
    disk_color = Colors.GREEN
    disk_status = "✓ OK"
    if disk['percent'] >= DISK_CRITICAL_THRESHOLD:
        disk_color = Colors.RED
        disk_status = "✗ CRITICAL"
        log(f"Disk space critical: {disk['percent']:.1f}% used", "CRITICAL", Colors.RED)
    elif disk['percent'] >= DISK_WARNING_THRESHOLD:
        disk_color = Colors.YELLOW
        disk_status = "⚠ WARNING"
        log(f"Disk space warning: {disk['percent']:.1f}% used", "WARNING", Colors.YELLOW)

    print(f"  {disk_color}{disk_status}{Colors.END}")
    print(f"    Used: {disk['used_gb']:.1f} GB / {disk['total_gb']:.1f} GB ({disk['percent']:.1f}%)")
    print(f"    Free: {disk['free_gb']:.1f} GB")
    print()

    # System Resources
    print(f"{Colors.BOLD}System Resources:{Colors.END}")

    # CPU
    cpu_color = Colors.GREEN if system['cpu_percent'] < CPU_WARNING_THRESHOLD else Colors.YELLOW
    print(f"  CPU: {cpu_color}{system['cpu_percent']:.1f}%{Colors.END}")

    # Memory
    mem_color = Colors.GREEN
    if system['memory_percent'] >= MEMORY_WARNING_THRESHOLD:
        mem_color = Colors.YELLOW
        log(f"Memory usage high: {system['memory_percent']:.1f}%", "WARNING", Colors.YELLOW)

    print(f"  Memory: {mem_color}{system['memory_percent']:.1f}%{Colors.END} ({system['memory_used_gb']:.1f} GB / {system['memory_total_gb']:.1f} GB)")
    print()

    # Recordings Storage
    print(f"{Colors.BOLD}Recordings Storage:{Colors.END}")
    if recordings['status'] == 'ok':
        print(f"  Total size: {recordings['size_str']}")
    else:
        print(f"  {Colors.YELLOW}Status: {recordings['status']}{Colors.END}")
    print()

    # Recent Errors
    print(f"{Colors.BOLD}Recent Errors (last {ERROR_CHECK_LINES} log lines):{Colors.END}")
    if errors:
        print(f"  {Colors.RED}✗ {len(errors)} error(s) found:{Colors.END}")
        for i, error in enumerate(errors[-5:], 1):  # Show last 5 errors
            print(f"    {i}. {error[:100]}...")  # Truncate long errors
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more errors")
    else:
        print(f"  {Colors.GREEN}✓ No critical errors{Colors.END}")
    print()

    print("="*80)
    print(f"Next check in {CHECK_INTERVAL} seconds... (Press Ctrl+C to stop)")
    print("="*80 + "\n")

def main():
    """Main monitoring loop"""
    log("System monitoring started", "INFO", Colors.GREEN)
    print(f"\n{Colors.BOLD}{Colors.CYAN}SF-NVR Continuous System Monitor{Colors.END}")
    print(f"Checking every {CHECK_INTERVAL} seconds")
    print(f"Logs saved to: {LOG_FILE}\n")

    try:
        while True:
            # Perform all checks
            nvr_proc = check_nvr_process()
            disk = check_disk_space()
            system = check_system_resources()
            cameras = check_camera_streams()
            recordings = check_recording_size()
            errors = check_recent_errors()

            # Display dashboard
            display_status_dashboard(nvr_proc, disk, system, cameras, recordings, errors)

            # Critical alerts
            if not nvr_proc['running']:
                log("ALERT: NVR process has stopped!", "CRITICAL", Colors.RED)

            if disk['percent'] >= DISK_CRITICAL_THRESHOLD:
                log(f"ALERT: Disk space critically low! {disk['free_gb']:.1f} GB remaining", "CRITICAL", Colors.RED)

            # Sleep until next check
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        log("\nMonitoring stopped by user", "INFO", Colors.CYAN)
        print(f"\n{Colors.CYAN}Monitoring stopped. Logs saved to {LOG_FILE}{Colors.END}\n")
    except Exception as e:
        log(f"Monitoring error: {e}", "ERROR", Colors.RED)
        raise

if __name__ == "__main__":
    main()
