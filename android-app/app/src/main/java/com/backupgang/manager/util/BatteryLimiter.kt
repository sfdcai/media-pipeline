package com.backupgang.manager.util

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.util.Log
import com.topjohnwu.superuser.Shell

object BatteryLimiter {
    private const val TAG = "BatteryLimiter"
    private const val NODE_PATH_1 = "/sys/class/power_supply/battery/charging_enabled"
    private const val NODE_PATH_2 = "/sys/class/power_supply/battery/battery_charging_enabled"

    fun setChargingEnabled(enabled: Boolean): Boolean {
        val value = if (enabled) "1" else "0"
        Log.d(TAG, "Setting charging control nodes to $value")
        val commands = mutableListOf<String>()
        commands.add("if [ -f $NODE_PATH_1 ]; then echo $value > $NODE_PATH_1; fi")
        commands.add("if [ -f $NODE_PATH_2 ]; then echo $value > $NODE_PATH_2; fi")
        val result = Shell.cmd(*commands.toTypedArray()).exec()
        return result.isSuccess
    }

    fun isChargingEnabled(): Boolean {
        var enabled1 = true
        var result = Shell.cmd("if [ -f $NODE_PATH_1 ]; then cat $NODE_PATH_1; else echo '1'; fi").exec()
        if (result.isSuccess && result.out.isNotEmpty()) {
            enabled1 = result.out[0].trim() == "1"
        }

        var enabled2 = true
        result = Shell.cmd("if [ -f $NODE_PATH_2 ]; then cat $NODE_PATH_2; else echo '1'; fi").exec()
        if (result.isSuccess && result.out.isNotEmpty()) {
            enabled2 = result.out[0].trim() == "1"
        }

        return enabled1 && enabled2
    }

    fun getCpuTemp(): Float {
        try {
            val result = Shell.cmd("cat /sys/class/thermal/thermal_zone0/temp").exec()
            if (result.isSuccess && result.out.isNotEmpty()) {
                val rawTemp = result.out[0].trim().toFloatOrNull() ?: 0f
                return rawTemp / 1000f
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error checking CPU temp", e)
        }
        return 0f
    }

    fun checkAndLimit(context: Context, minLevel: Int = 70, maxLevel: Int = 80) {
        val batteryStatus: Intent? = context.registerReceiver(
            null,
            IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        )
        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val tempRaw = batteryStatus?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1) ?: -1
        if (level == -1 || scale == -1) return

        val batteryPct = (level * 100 / scale.toFloat()).toInt()
        val batteryTemp = if (tempRaw != -1) tempRaw / 10f else 0f
        val cpuTemp = getCpuTemp()

        Log.d(TAG, "Battery Pct: $batteryPct%, Battery Temp: $batteryTemp°C, CPU Temp: $cpuTemp°C")

        val currentlyCharging = isChargingEnabled()

        if (BackupState.isChargingCompletelyDisabled.value) {
            if (currentlyCharging) setChargingEnabled(false)
            BackupState.setCpuTemp(cpuTemp)
            BackupState.setBatteryInfo(batteryPct, isChargingEnabled())
            return
        }

        // Safety thresholds
        val tempTooHigh = (batteryTemp >= 40.0f || cpuTemp >= 40.0f)
        val tempCoolEnough = (batteryTemp < 39.0f && cpuTemp < 39.0f)

        if (tempTooHigh || batteryPct >= maxLevel) {
            if (currentlyCharging) {
                val reason = if (tempTooHigh) "High temperature (Battery: $batteryTemp°C, CPU: $cpuTemp°C)" else "Battery >= $maxLevel% ($batteryPct%)"
                BackupState.addLog("Over-temperature/charge threshold hit. Disabling charging. Reason: $reason")
                setChargingEnabled(false)
            }
        } else if (tempCoolEnough && batteryPct <= minLevel) {
            if (!currentlyCharging) {
                BackupState.addLog("Temperature and charge cooled down. Re-enabling charging. (Battery: $batteryTemp°C, CPU: $cpuTemp°C)")
                setChargingEnabled(true)
            }
        }

        // Keep state updated
        BackupState.setCpuTemp(cpuTemp)
        BackupState.setBatteryInfo(batteryPct, isChargingEnabled())
    }
}

