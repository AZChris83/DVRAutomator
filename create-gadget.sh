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

#!/bin/bash
GADGET_PATH="/sys/kernel/config/usb_gadget/mygadget"
echo "Starting USB HID gadget setup..."

# Ensure configfs is mounted
if ! sudo mount | grep -q "/sys/kernel/config"; then
    echo "Mounting configfs..."
    sudo mount -t configfs none /sys/kernel/config
fi

# Remove old gadget if it exists
if [ -d "$GADGET_PATH" ]; then
    echo "Removing existing USB gadget..."
    # First unbind from UDC
    echo "" | sudo tee "$GADGET_PATH/UDC" > /dev/null 2>&1

    # Remove all config symlinks
    if [ -d "$GADGET_PATH/configs/c.1" ]; then
        for F in "$GADGET_PATH"/configs/c.1/*; do
            if [ -L "$F" ]; then
                sudo rm -f "$F" 2>/dev/null || true
            fi
        done
    fi

    # Change directory to avoid "device or resource busy" errors
    cd /

    # Suppress errors to make the output cleaner
    set +e

    # Proper cleanup sequence for gadget
    # 1. Remove function directory contents
    if [ -d "$GADGET_PATH/functions/hid.usb0" ]; then
        sudo find "$GADGET_PATH/functions/hid.usb0" -type f -exec sudo rm -f {} \; 2>/dev/null
        sudo rmdir "$GADGET_PATH/functions/hid.usb0" 2>/dev/null || true
    fi

    # 2. Remove string values (these are files, not directories)
    if [ -d "$GADGET_PATH/strings/0x409" ]; then
        sudo find "$GADGET_PATH/strings/0x409" -type f -exec sudo rm -f {} \; 2>/dev/null
        sudo rmdir "$GADGET_PATH/strings/0x409" 2>/dev/null || true
    fi

    if [ -d "$GADGET_PATH/configs/c.1/strings/0x409" ]; then
        sudo find "$GADGET_PATH/configs/c.1/strings/0x409" -type f -exec sudo rm -f {} \; 2>/dev/null
        sudo rmdir "$GADGET_PATH/configs/c.1/strings/0x409" 2>/dev/null || true
    fi

    # 3. Remove config values and directory
    if [ -d "$GADGET_PATH/configs/c.1" ]; then
        sudo find "$GADGET_PATH/configs/c.1" -type f -exec sudo rm -f {} \; 2>/dev/null
        sudo rmdir "$GADGET_PATH/configs/c.1" 2>/dev/null || true
    fi

    # 4. Remove top-level gadget attributes and directory
    sudo find "$GADGET_PATH" -maxdepth 1 -type f -exec sudo rm -f {} \; 2>/dev/null
    sudo find "$GADGET_PATH" -type d -empty -delete 2>/dev/null || true
    sudo rmdir "$GADGET_PATH" 2>/dev/null || true

    # Set -e back again
    set -e

    echo "Cleanup completed"
fi

## CF
## Used tcpdump/wireshark on usbmon1 to grab physical mouse data so we can replicate this


echo "Creating new USB HID gadget..."
sudo mkdir -p "$GADGET_PATH"
cd "$GADGET_PATH" || exit 1

# Configure USB device
echo 0x046d | sudo tee idVendor > /dev/null  # Logitech
echo 0xc077 | sudo tee idProduct > /dev/null # Generic Mouse
echo 0x0100 | sudo tee bcdDevice > /dev/null # Version 1.0.0
echo 0x0200 | sudo tee bcdUSB > /dev/null    # USB 2.0

# Set English (US) as the device language
sudo mkdir -p strings/0x409
echo "fedcba9876543210" | sudo tee strings/0x409/serialnumber > /dev/null
echo "Raspberry Pi" | sudo tee strings/0x409/manufacturer > /dev/null
echo "USB HID Mouse" | sudo tee strings/0x409/product > /dev/null

# Configure the gadget as a HID device
sudo mkdir -p configs/c.1/strings/0x409
echo "Mouse Configuration" | sudo tee configs/c.1/strings/0x409/configuration > /dev/null
echo 120 | sudo tee configs/c.1/MaxPower > /dev/null

# Create the HID function
sudo mkdir -p functions/hid.usb0
echo 2 | sudo tee functions/hid.usb0/protocol > /dev/null    # Mouse
echo 1 | sudo tee functions/hid.usb0/subclass > /dev/null    # Boot Interface
echo 8 | sudo tee functions/hid.usb0/report_length > /dev/null

# Write the HID report descriptor for a standard 2-button mouse
# This creates a compatible descriptor for Logitech/Microsoft mice
echo -ne \\x05\\x01\\x09\\x02\\xa1\\x01\\x09\\x01\\xa1\\x00\\x05\\x09\\x19\\x01\\x29\\x03\\x15\\x00\\x25\\x01\\x95\\x03\\x75\\x01\\x81\\x02\\x95\\x01\\x75\\x05\\x81\\x03\\x05\\x01\\x09\\x30\\x09\\x31\\x15\\x81\\x25\\x7f\\x75\\x08\\x95\\x02\\x81\\x06\\xc0\\xc0 | sudo tee functions/hid.usb0/report_desc > /dev/null

# Link the HID function to the configuration
sudo ln -s functions/hid.usb0 configs/c.1/

# Find the UDC device
UDC=$(ls /sys/class/udc | head -n1)
if [ -z "$UDC" ]; then
    echo "Error: No UDC device found. Make sure the USB controller is enabled."
    exit 1
fi

# Enable the gadget
echo "$UDC" | sudo tee UDC > /dev/null
echo "USB HID gadget setup complete! Using UDC: $UDC"
