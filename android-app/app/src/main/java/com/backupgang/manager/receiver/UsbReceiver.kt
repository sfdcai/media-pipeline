package com.backupgang.manager.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbManager
import android.util.Log
import android.widget.Toast
import com.backupgang.manager.util.MountHelper

class UsbReceiver : BroadcastReceiver() {
    private val TAG = "UsbReceiver"

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.d(TAG, "USB Broadcast Received: $action")

        if (UsbManager.ACTION_USB_DEVICE_ATTACHED == action) {
            Toast.makeText(context, "USB Device Detected. Mounting...", Toast.LENGTH_SHORT).show()
            val success = MountHelper.mountDrive()
            if (success) {
                Toast.makeText(context, "USB Drive Mounted Successfully!", Toast.LENGTH_LONG).show()
            } else {
                Toast.makeText(context, "Failed to mount USB Drive. Ensure Magisk root is granted.", Toast.LENGTH_LONG).show()
            }
        } else if (UsbManager.ACTION_USB_DEVICE_DETACHED == action) {
            Toast.makeText(context, "USB Device Detached. Unmounting...", Toast.LENGTH_SHORT).show()
            MountHelper.unmountDrive()
            Toast.makeText(context, "USB Drive Unmounted Cleanly.", Toast.LENGTH_LONG).show()
        }
    }
}
