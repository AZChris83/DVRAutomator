"""
# Hikvision IP Seurity DVR Shutdown Automation Script
# Copyright (c) 2019 CFCS - C. Formeister, w/ assistance from G. Kessler & B. Stone
# w/ HID information by Google Open Source results
# for Chris Formeister Computer Svcs. Phoenix, AZ
#
# Version 1.1a
# This script is for use for specific purposes of client of Chris Formeister Computer Services.
# Reproduction or other use is prohibited without the express consent of Chris Formeister Computer Services
"""

#!/usr/bin/env python3

import os
import sys
import time
import logging
import datetime
import subprocess
import socket
import smtplib
from email.message import EmailMessage
from pathlib import Path

# Configure logging
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dvr_shutdown.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Default timeout values (in seconds)
DEFAULT_OPERATION_TIMEOUT = 5  # Default timeout for individual operations
STEP_TIMEOUT = 15              # Timeout for completing a step
SEQUENCE_TIMEOUT = 60          # Total timeout for the entire sequence
MAX_RETRIES = 3                # Maximum number of retries for operations

# Email notification settings
EMAIL_ENABLED = True  # Set to True to enable email notifications
EMAIL_TO = "client@domain.com"
EMAIL_SUBJECT = "DVR Shutdown Alert"
EMAIL_FILE = "/tmp/dvr_shutdown_email.txt"  # Temporary file for email content

def send_notification(message, level="info"):
    """Create an email file that can be piped to msmtp"""
    if not EMAIL_ENABLED:
        return
        
    try:
        # Create email content with proper headers
        email_content = f"""To: {EMAIL_TO}
Subject: {EMAIL_SUBJECT} - {level.upper()}
From: DVR Shutdown Script <noreply@localhost>
X-Priority: {1 if level.lower() == "error" else 3}

{message}

--
Sent from host: {socket.gethostname()}
Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # Write to file for piping to msmtp
        with open(EMAIL_FILE, 'w') as f:
            f.write(email_content)
        
        # Execute msmtp to send the email
        cmd = f"cat {EMAIL_FILE} | msmtp {EMAIL_TO}"
        result = os.system(cmd)
        
        if result == 0:
            log_message(f"Notification sent to {EMAIL_TO}", "info")
        else:
            log_message(f"Failed to send notification via msmtp (exit code: {result})", "warning")
            
    except Exception as e:
        log_message(f"Failed to create notification: {e}", "error")

# Function to log and print messages
def log_message(message, level="info"):
    print(message)
    if level.lower() == "info":
        logging.info(message)
    elif level.lower() == "warning":
        logging.warning(message)
    elif level.lower() == "error":
        logging.error(message)
    elif level.lower() == "debug":
        logging.debug(message)
        
    # For critical errors, also send notification
    if level.lower() == "error":
        send_notification(message, level)

# Screen dimensions
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# Current cursor position (initialized to screen center)
current_x = SCREEN_WIDTH // 2
current_y = SCREEN_HEIGHT // 2

# HID device path
DEVICE_PATH = "/dev/hidg0"

def reset_gadget():
    log_message("Resetting USB gadget...")
    
    # Create this as a bash script for better execution
    reset_script = """#!/bin/bash
echo "" > /sys/kernel/config/usb_gadget/mygadget/UDC
sleep 0.5
cd /sys/kernel/config/usb_gadget
rm -rf mygadget
mkdir -p mygadget
cd mygadget
echo 0x046d > idVendor
echo 0xc077 > idProduct
mkdir -p strings/0x409
echo "RPI Mouse" > strings/0x409/product
mkdir -p configs/c.1/strings/0x409
mkdir -p functions/hid.usb0
echo 2 > functions/hid.usb0/protocol
echo 1 > functions/hid.usb0/subclass
echo 8 > functions/hid.usb0/report_length
echo -ne \\\\x05\\\\x01\\\\x09\\\\x02\\\\xa1\\\\x01\\\\x09\\\\x01\\\\xa1\\\\x00\\\\x05\\\\x09\\\\x19\\\\x01\\\\x29\\\\x03\\\\x15\\\\x00\\\\x25\\\\x01\\\\x95\\\\x03\\\\x75\\\\x01\\\\x81\\\\x02\\\\x95\\\\x01\\\\x75\\\\x05\\\\x81\\\\x03\\\\x05\\\\x01\\\\x09\\\\x30\\\\x09\\\\x31\\\\x15\\\\x81\\\\x25\\\\x7f\\\\x75\\\\x08\\\\x95\\\\x02\\\\x81\\\\x06\\\\xc0\\\\xc0 > functions/hid.usb0/report_desc
ln -s functions/hid.usb0 configs/c.1/
if [ -e /sys/class/udc/fe980000.usb ]; then
    echo fe980000.usb > UDC
else
    ls /sys/class/udc | head -n1 > UDC
fi
"""
    
    try:
        # Write script to file
        with open("/tmp/reset_mouse.sh", "w") as f:
            f.write(reset_script)
        
        # Make executable and run
        os.system("chmod +x /tmp/reset_mouse.sh")
        result = os.system("sudo /tmp/reset_mouse.sh")
        
        if result != 0:
            log_message("Error: Failed to reset USB gadget", "error")
            return False
        
        # Wait for device
        time.sleep(2)
        
        if not os.path.exists(DEVICE_PATH):
            log_message("Error: HID device not found after reset", "error")
            return False
        
        # NOTE: We no longer assume cursor position here
        # Position will be reset in ensure_known_position()
        
        log_message("USB gadget hardware reset complete")
        return True
        
    except Exception as e:
        log_message(f"Error during gadget reset: {e}", "error")
        return False

def ensure_known_position():
    global current_x, current_y
    
    log_message("Resetting cursor position to known coordinates...")
    
    # edge of the screen where the cursor will stop
    for _ in range(20):  # Multiple moves to ensure we reach the edge
        send_mouse_event(0, -127, -127)  # Move maximum left and up
        time.sleep(0.01)
    
    # Now we know we're at (0,0) - the top-left corner
    current_x = 0
    current_y = 0
    
    log_message("Cursor position reset to top-left (0,0)")
    return True

def send_mouse_event(button=0, x=0, y=0, retries=MAX_RETRIES, timeout=DEFAULT_OPERATION_TIMEOUT):
    # Format report - 3 bytes: button, x, y
	# RS: took fiddling to find right combo
    report = bytes([button & 0xFF, x & 0xFF, y & 0xFF])
    
    retry_count = 0
    start_time = time.time()
    
    while retry_count < retries:
        try:
            # Check if we've exceeded the timeout
            if time.time() - start_time > timeout:
                log_message(f"Operation timed out after {timeout} seconds", "error")
                return False
                
            # Use low-level file operations to ensure immediate write
            fd = os.open(DEVICE_PATH, os.O_WRONLY)
            os.write(fd, report)
            os.close(fd)
            return True
            
        except Exception as e:
            retry_count += 1
            log_message(f"Error writing to HID device (attempt {retry_count}/{retries}): {e}", "warning")
            
            if retry_count >= retries:
                log_message(f"Failed to send mouse event after {retries} attempts", "error")
                return False
                
            # Exponential backoff for retries
            backoff_time = min(0.5 * (2 ** retry_count), 5)  # Cap at 5 seconds
            log_message(f"Retrying in {backoff_time:.2f} seconds...", "info")
            time.sleep(backoff_time)

def move_mouse_relative(dx, dy):
    global current_x, current_y
    
    # Update position tracking
    current_x += dx
    current_y += dy
    
    # Ensure within bounds
    current_x = max(0, min(current_x, SCREEN_WIDTH))
    current_y = max(0, min(current_y, SCREEN_HEIGHT))
    
    # Send movement event
    return send_mouse_event(0, dx, dy)

def move_to_absolute(target_x, target_y):
	# RS: client wants absolute so seperated relative and absolute
    global current_x, current_y
    
    # Calculate distance to move
    dx_total = target_x - current_x
    dy_total = target_y - current_y
    
    if dx_total == 0 and dy_total == 0:
        log_message("Already at target position.")
        return True
    
    log_message(f"Moving from ({current_x}, {current_y}) to ({target_x}, {target_y})")
    
    # Break the movement into smaller chunks
    steps_needed = max(1, max(abs(dx_total), abs(dy_total)) // 100)
    
    for step in range(steps_needed):
        if step == steps_needed - 1:
            # Last step - move remaining distance
            dx = dx_total - (dx_total * step // steps_needed)
            dy = dy_total - (dy_total * step // steps_needed)
        else:
            # Calculate this step's movement
            dx = dx_total // steps_needed
            dy = dy_total // steps_needed
        
        # Maximum movement per step is 127 in any direction
        while abs(dx) > 127 or abs(dy) > 127:
            dx_chunk = max(-127, min(127, dx))
            dy_chunk = max(-127, min(127, dy))
            
            if not move_mouse_relative(dx_chunk, dy_chunk):
                log_message("Movement failed during large chunk", "error")
                return False
            
            dx -= dx_chunk
            dy -= dy_chunk
        
        # Send the remaining movement
        if dx != 0 or dy != 0:
            if not move_mouse_relative(dx, dy):
                log_message("Movement failed during final movement", "error")
                return False
            
        # Small delay between movements for stability
        time.sleep(0.01)
            
    return True

def right_click():
    log_message("Performing right click...")
    
    # 1. Send button press (0x02 = right button)
    if not send_mouse_event(button=2, x=0, y=0):
        log_message("Failed to send right button press", "error")
        return False
    
    # RS crucial: very short delay between press and release (3-5ms)
    time.sleep(0.003)  # 3 milliseconds
    
    # 2. Send button release (0x00 = no buttons)
    if not send_mouse_event(button=0, x=0, y=0):
        log_message("Failed to send right button release", "error")
        return False
    
    log_message("Right click completed successfully")
    return True

def left_click():
    log_message("Performing left click...")
    
    # 1. Send button press (0x01 = left button)
    if not send_mouse_event(button=1, x=0, y=0):
        log_message("Failed to send left button press", "error")
        return False
    
    # Crucial: Very short delay between press and release (3-5ms)
    time.sleep(0.003)  # 3 milliseconds
    
    # 2. Send button release (0x00 = no buttons)
    if not send_mouse_event(button=0, x=0, y=0):
        log_message("Failed to send left button release", "error")
        return False
    
    log_message("Left click completed successfully")
    return True

def perform_shutdown_sequence():
    log_message("Starting DVR shutdown sequence...")
    
    # Set overall sequence timeout
    sequence_start = time.time()
    sequence_end = sequence_start + SEQUENCE_TIMEOUT
    
    # Track retry attempts for the entire sequence
    sequence_retry = 0
    
    while sequence_retry < MAX_RETRIES:
        try:
            # Check if overall sequence has timed out
            if time.time() > sequence_end:
                log_message(f"Shutdown sequence timed out after {SEQUENCE_TIMEOUT} seconds", "error")
                send_notification("DVR shutdown sequence failed due to timeout", "error")
                return False
                
            # Reset mouse hardware with timeout
            step_start = time.time()
            step_end = step_start + STEP_TIMEOUT
            
            log_message("Step 0: Initializing hardware...")
            if not reset_gadget():
                raise Exception("Failed to reset mouse hardware")
                
            # Now establish known position with timeout
            log_message("Step 0.5: Establishing known position...")
            if not ensure_known_position():
                raise Exception("Failed to establish known cursor position")
            
            # Move to center (better starting point)
            if not move_to_absolute(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2):
                raise Exception("Failed to move to center position")
                
            # Check if this initialization step timed out
            if time.time() > step_end:
                log_message("Initialization step timed out", "warning")
                
            # Step 1: Navigate to menu button with timeout
            step_start = time.time()
            step_end = step_start + STEP_TIMEOUT
            
            log_message("Step 1: Navigating to menu button")
            if not move_to_absolute(1800, 50):
                raise Exception("Failed to move to menu button")
            
            # Use right-click for menu
            if not right_click():
                raise Exception("Failed to right-click menu button")
                
            log_message("Step 1 complete, waiting for menu to appear...")
            time.sleep(1.0)  # Wait for menu to appear
            
            # Check if step timed out
            if time.time() > step_end:
                log_message("Step 1 timed out", "warning")
            
            # Step 2: Navigate to shutdown option with timeout
            step_start = time.time()
            step_end = step_start + STEP_TIMEOUT
            
            log_message("Step 2: Navigating to shutdown option")
            if not move_to_absolute(1750, 600):
                raise Exception("Failed to move to shutdown option")
                
            if not left_click():
                raise Exception("Failed to click shutdown option")
                
            log_message("Step 2 complete, waiting for confirmation dialog...")
            time.sleep(1.0)  # Wait for confirmation dialog
            
            # Check if step timed out
            if time.time() > step_end:
                log_message("Step 2 timed out", "warning")
            
            # Step 3: Navigate to "Yes" button to confirm shutdown with timeout
            step_start = time.time()
            step_end = step_start + STEP_TIMEOUT
            
            log_message("Step 3: Confirming shutdown")
            if not move_to_absolute(900, 500):
                raise Exception("Failed to move to confirmation button")
                
            if not left_click():
                raise Exception("Failed to click confirmation button")
            
            # Check if step timed out
            if time.time() > step_end:
                log_message("Step 3 timed out", "warning")
            
            # Successfully completed sequence
            sequence_duration = time.time() - sequence_start
            log_message(f"Shutdown sequence completed successfully in {sequence_duration:.1f} seconds")
            send_notification(f"DVR shutdown sequence completed successfully in {sequence_duration:.1f} seconds", "info")
            return True
            
        except Exception as e:
            # Handle sequence failure
            sequence_retry += 1
            log_message(f"Error during shutdown sequence (attempt {sequence_retry}/{MAX_RETRIES}): {e}", "error")
            
            if sequence_retry >= MAX_RETRIES:
                log_message(f"Shutdown sequence failed after {MAX_RETRIES} attempts", "error")
                send_notification(f"DVR shutdown sequence failed after {MAX_RETRIES} attempts: {e}", "error")
                return False
                
            # backoff for retries
            backoff_time = min(2 * (2 ** sequence_retry), 10)  # Cap at 10 seconds
            log_message(f"Retrying sequence in {backoff_time:.2f} seconds...", "warning")
            time.sleep(backoff_time)
            
            # Reset everything before retry
            reset_gadget()

if __name__ == "__main__":
    # Start logging session
    log_message("="*50)
    log_message(f"DVR Shutdown Script Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check hostname for logging purposes
    hostname = socket.gethostname()
    log_message(f"Running on host: {hostname}")
    
    # Check if running as root
    if os.geteuid() != 0:
        error_msg = "This script must be run as root (sudo)!"
        log_message(error_msg, "error")
        send_notification(f"DVR shutdown failed on {hostname}: {error_msg}", "error")
        sys.exit(1)
    
    # Check disk space for logs
    try:
        log_dir = Path(log_file).parent
        stat = os.statvfs(log_dir)
        free_space_mb = (stat.f_frsize * stat.f_bavail) / (1024 * 1024)
        if free_space_mb < 50:  # Less than 50MB free
            log_message(f"Warning: Low disk space ({free_space_mb:.1f} MB available)", "warning")
    except Exception as e:
        log_message(f"Could not check disk space: {e}", "warning")
    
    # Check if HID device exists and set it up if needed
    if not os.path.exists(DEVICE_PATH):
        log_message("HID device not found. Setting up USB gadget...", "warning")
        
        # Try to set up with timeout
        setup_timeout = time.time() + 30
        setup_success = False
        
        while time.time() < setup_timeout and not setup_success:
            if reset_gadget():
                setup_success = True
                break
            log_message("Retrying USB gadget setup...", "warning")
            time.sleep(2)
            
        if not setup_success:
            error_msg = "Failed to set up USB mouse gadget after multiple attempts"
            log_message(error_msg, "error")
            send_notification(f"DVR shutdown failed on {hostname}: {error_msg}", "error")
            sys.exit(1)
    
    # Execute the shutdown sequence
    log_message("Starting DVR shutdown process...")
    
    # Set a timeout for the entire operation
    start_time = time.time()
    max_runtime = 120  # 2 minutes max runtime
    
    try:
        # First ensure we're at a known position, regardless of what other mice might have done
        ensure_known_position()
        
        # Now run the shutdown sequence with enhanced error handling
        success = perform_shutdown_sequence()
        if not success:
            error_msg = "Shutdown sequence failed"
            log_message(error_msg, "error")
            send_notification(f"DVR shutdown failed on {hostname}: {error_msg}", "error")
            sys.exit(1)
            
        elapsed_time = time.time() - start_time
        log_message(f"Shutdown sequence completed in {elapsed_time:.1f} seconds")
        
    except KeyboardInterrupt:
        # Handle manual interruption
        log_message("\nOperation cancelled by user", "warning")
        send_notification(f"DVR shutdown cancelled by user on {hostname}", "warning")
        sys.exit(130)
    except Exception as e:
        # Handle unexpected errors
        error_msg = f"Unexpected error: {e}"
        log_message(error_msg, "error")
        send_notification(f"DVR shutdown failed on {hostname}: {error_msg}", "error")
        sys.exit(1)
    
    # Check if we exceeded the timeout
    if time.time() - start_time > max_runtime:
        log_message(f"Warning: Shutdown sequence took longer than expected ({max_runtime} seconds)", "warning")
        send_notification(f"DVR shutdown on {hostname} completed but exceeded expected runtime", "warning")
    
    log_message(f"DVR Shutdown Script Completed: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_message("="*50)
    
    # Final log message before shutdown
    log_message("DVR successfully shut down. Now shutting down Raspberry Pi...")
    send_notification(f"DVR successfully shut down on {hostname}. Raspberry Pi is now shutting down.", "info")
    
    # Flush the log file to ensure all messages are written before shutdown
    logging.shutdown()
    
    # Shutdown the Raspberry Pi
    log_message("Executing system shutdown command...")
    os.system("sudo shutdown -h now")
    
    sys.exit(0)
