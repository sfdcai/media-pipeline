package com.backupgang.manager.util

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class UsbDeviceOption(val path: String, val label: String, val type: String, val sizeBytes: Long = 0L)

object BackupState {
    private val _isSyncing = MutableStateFlow(false)
    val isSyncing: StateFlow<Boolean> = _isSyncing.asStateFlow()

    private val _currentFolder = MutableStateFlow("")
    val currentFolder: StateFlow<String> = _currentFolder.asStateFlow()

    private val _syncedCount = MutableStateFlow(0)
    val syncedCount: StateFlow<Int> = _syncedCount.asStateFlow()

    private val _totalCount = MutableStateFlow(0)
    val totalCount: StateFlow<Int> = _totalCount.asStateFlow()

    private val _completedFolders = MutableStateFlow(0)
    val completedFolders: StateFlow<Int> = _completedFolders.asStateFlow()

    private val _totalFolders = MutableStateFlow(0)
    val totalFolders: StateFlow<Int> = _totalFolders.asStateFlow()

    private val _cpuTemp = MutableStateFlow(0f)
    val cpuTemp: StateFlow<Float> = _cpuTemp.asStateFlow()

    private val _batteryLevel = MutableStateFlow(0)
    val batteryLevel: StateFlow<Int> = _batteryLevel.asStateFlow()

    private val _isCharging = MutableStateFlow(false)
    val isCharging: StateFlow<Boolean> = _isCharging.asStateFlow()

    private val _isUsbMounted = MutableStateFlow(false)
    val isUsbMounted: StateFlow<Boolean> = _isUsbMounted.asStateFlow()

    private val _isBatteryLimiterEnabled = MutableStateFlow(false)
    val isBatteryLimiterEnabled: StateFlow<Boolean> = _isBatteryLimiterEnabled.asStateFlow()

    private val _isPixelUploadEnabled = MutableStateFlow(true)
    val isPixelUploadEnabled: StateFlow<Boolean> = _isPixelUploadEnabled.asStateFlow()

    private val _isIcloudUploadEnabled = MutableStateFlow(false)
    val isIcloudUploadEnabled: StateFlow<Boolean> = _isIcloudUploadEnabled.asStateFlow()

    private val _isScreenAlwaysActive = MutableStateFlow(false)
    val isScreenAlwaysActive: StateFlow<Boolean> = _isScreenAlwaysActive.asStateFlow()

    private val _isChargingCompletelyDisabled = MutableStateFlow(false)
    val isChargingCompletelyDisabled: StateFlow<Boolean> = _isChargingCompletelyDisabled.asStateFlow()

    private val _availableDevices = MutableStateFlow<List<UsbDeviceOption>>(emptyList())
    val availableDevices: StateFlow<List<UsbDeviceOption>> = _availableDevices.asStateFlow()

    private val _selectedDevicePath = MutableStateFlow("")
    val selectedDevicePath: StateFlow<String> = _selectedDevicePath.asStateFlow()

    private val _usedStorageBytes = MutableStateFlow(0L)
    val usedStorageBytes: StateFlow<Long> = _usedStorageBytes.asStateFlow()

    private val _totalStorageBytes = MutableStateFlow(0L)
    val totalStorageBytes: StateFlow<Long> = _totalStorageBytes.asStateFlow()

    private val _networkType = MutableStateFlow("Disconnected")
    val networkType: StateFlow<String> = _networkType.asStateFlow()

    private val _ipAddress = MutableStateFlow("Disconnected")
    val ipAddress: StateFlow<String> = _ipAddress.asStateFlow()

    private val _logs = MutableStateFlow<List<String>>(emptyList())
    val logs: StateFlow<List<String>> = _logs.asStateFlow()

    fun setNetworkInfo(type: String, ip: String) {
        _networkType.value = type
        _ipAddress.value = ip
    }

    fun setSyncing(syncing: Boolean) {
        _isSyncing.value = syncing
    }

    fun setCurrentFolder(folder: String) {
        _currentFolder.value = folder
    }

    fun setProgress(synced: Int, total: Int) {
        _syncedCount.value = synced
        _totalCount.value = total
    }

    fun setFolderProgress(completed: Int, total: Int) {
        _completedFolders.value = completed
        _totalFolders.value = total
    }

    fun setCpuTemp(temp: Float) {
        _cpuTemp.value = temp
    }

    fun setBatteryInfo(level: Int, charging: Boolean) {
        _batteryLevel.value = level
        _isCharging.value = charging
    }

    fun setUsbMounted(mounted: Boolean) {
        _isUsbMounted.value = mounted
    }

    fun initialize(context: Context) {
        val prefs = context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE)
        _isBatteryLimiterEnabled.value = prefs.getBoolean("battery_limiter_enabled", false)
        _selectedDevicePath.value = prefs.getString("selected_device_path", "") ?: ""
        _isPixelUploadEnabled.value = prefs.getBoolean("pixel_upload", true)
        _isIcloudUploadEnabled.value = prefs.getBoolean("icloud_upload", false)
        _isScreenAlwaysActive.value = prefs.getBoolean("screen_active", false)
        _isChargingCompletelyDisabled.value = prefs.getBoolean("charging_disabled", false)
    }

    fun setBatteryLimiterEnabled(context: Context, enabled: Boolean) {
        _isBatteryLimiterEnabled.value = enabled
        val prefs = context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE)
        prefs.edit().putBoolean("battery_limiter_enabled", enabled).apply()
        if (!enabled) {
            BatteryLimiter.setChargingEnabled(true)
        }
    }

    fun setPixelUploadEnabled(context: Context, enabled: Boolean) {
        _isPixelUploadEnabled.value = enabled
        context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE).edit().putBoolean("pixel_upload", enabled).apply()
    }

    fun setIcloudUploadEnabled(context: Context, enabled: Boolean) {
        _isIcloudUploadEnabled.value = enabled
        context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE).edit().putBoolean("icloud_upload", enabled).apply()
    }

    fun setScreenAlwaysActive(context: Context, enabled: Boolean) {
        _isScreenAlwaysActive.value = enabled
        context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE).edit().putBoolean("screen_active", enabled).apply()
        if (enabled) {
            com.topjohnwu.superuser.Shell.cmd("settings put global stay_on_while_plugged_in 7").exec()
        } else {
            com.topjohnwu.superuser.Shell.cmd("settings put global stay_on_while_plugged_in 0").exec()
        }
    }

    fun setChargingCompletelyDisabled(context: Context, disabled: Boolean) {
        _isChargingCompletelyDisabled.value = disabled
        context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE).edit().putBoolean("charging_disabled", disabled).apply()
        if (disabled) {
            BatteryLimiter.setChargingEnabled(false)
        } else {
            BatteryLimiter.setChargingEnabled(true)
        }
    }

    fun setAvailableDevices(devices: List<UsbDeviceOption>, context: Context) {
        _availableDevices.value = devices
        if (_selectedDevicePath.value.isEmpty() && devices.isNotEmpty()) {
            val best = devices.firstOrNull { it.label.equals("BACKUPUSB", ignoreCase = true) }
                ?: devices.firstOrNull { it.type.equals("ext4", ignoreCase = true) || it.type.equals("f2fs", ignoreCase = true) }
                ?: devices.maxByOrNull { it.sizeBytes }
                ?: devices.first()
            setSelectedDevicePath(context, best.path)
        }
    }

    fun setSelectedDevicePath(context: Context, path: String) {
        _selectedDevicePath.value = path
        val prefs = context.getSharedPreferences("backup_prefs", Context.MODE_PRIVATE)
        prefs.edit().putString("selected_device_path", path).apply()
    }

    fun setStorageInfo(used: Long, total: Long) {
        _usedStorageBytes.value = used
        _totalStorageBytes.value = total
    }

    fun addLog(message: String) {
        val timestamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val logLine = "[$timestamp] $message"
        val currentLogs = _logs.value.toMutableList()
        currentLogs.add(0, logLine) // Insert at beginning for reverse chronological view
        if (currentLogs.size > 200) {
            currentLogs.removeLast()
        }
        _logs.value = currentLogs
    }

    fun clearLogs() {
        _logs.value = emptyList()
    }
}
