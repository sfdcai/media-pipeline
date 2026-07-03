package com.backupgang.manager

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.backupgang.manager.service.BackupService
import com.backupgang.manager.util.BackupState
import com.backupgang.manager.util.BatteryLimiter
import com.backupgang.manager.util.MountHelper
import com.backupgang.manager.util.UsbDeviceOption
import com.topjohnwu.superuser.Shell
import java.util.Locale
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

fun formatBytes(bytes: Long): String {
    if (bytes <= 0) return "0 B"
    val units = arrayOf("B", "KB", "MB", "GB", "TB")
    val digitGroups = (Math.log10(bytes.toDouble()) / Math.log10(1024.0)).toInt()
    val value = bytes / Math.pow(1024.0, digitGroups.toDouble())
    return String.format(Locale.US, "%.2f %s", value, units[digitGroups])
}

// Premium Dark Theme Colors
val ObsidianBG = Color(0xFF0C0C0F)
val CardBackground = Color(0x1AFFFFFF)
val GlassBorder = Color(0x1FFFFFFF)

val AccentCyan = Color(0xFF00F0FF)
val AccentBlue = Color(0xFF0082FF)
val AccentGreen = Color(0xFF00FF88)
val AccentOrange = Color(0xFFFF9F00)
val AccentRed = Color(0xFFFF3B30)
val TextLight = Color(0xFFF3F3F7)
val TextMuted = Color(0x8AFFFFFF)

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Load persisted preferences
        BackupState.initialize(applicationContext)

        // Initialize shell setup
        Shell.enableVerboseLogging = true

        // Check root and start foreground service
        CoroutineScope(Dispatchers.IO).launch {
            val hasRoot = Shell.isAppGrantedRoot() == true
            withContext(Dispatchers.Main) {
                if (hasRoot) {
                    BackupState.addLog("Root Access Granted.")
                } else {
                    BackupState.addLog("WARNING: Root Access NOT detected! Magisk is required.")
                    Toast.makeText(this@MainActivity, "Please grant Magisk root access!", Toast.LENGTH_LONG).show()
                }
                // Always start service to maintain notification & Ktor
                BackupService.startService(this@MainActivity)
            }
        }

        setContent {
            MainDashboard()
        }
    }

    @Composable
    fun MainDashboard() {
        val isSyncing by BackupState.isSyncing.collectAsState()
        val currentFolder by BackupState.currentFolder.collectAsState()
        val syncedCount by BackupState.syncedCount.collectAsState()
        val totalCount by BackupState.totalCount.collectAsState()
        val completedFolders by BackupState.completedFolders.collectAsState()
        val totalFolders by BackupState.totalFolders.collectAsState()
        val cpuTemp by BackupState.cpuTemp.collectAsState()
        val batteryLevel by BackupState.batteryLevel.collectAsState()
        val isCharging by BackupState.isCharging.collectAsState()
        val isUsbMounted by BackupState.isUsbMounted.collectAsState()
        val isBatteryLimiterEnabled by BackupState.isBatteryLimiterEnabled.collectAsState()
        val usedStorageBytes by BackupState.usedStorageBytes.collectAsState()
        val totalStorageBytes by BackupState.totalStorageBytes.collectAsState()
        val networkType by BackupState.networkType.collectAsState()
        val ipAddress by BackupState.ipAddress.collectAsState()
        val logs by BackupState.logs.collectAsState()
        val availableDevices by BackupState.availableDevices.collectAsState()
        val selectedDevicePath by BackupState.selectedDevicePath.collectAsState()
        val isPixelUploadEnabled by BackupState.isPixelUploadEnabled.collectAsState()
        val isIcloudUploadEnabled by BackupState.isIcloudUploadEnabled.collectAsState()
        val isScreenAlwaysActive by BackupState.isScreenAlwaysActive.collectAsState()
        val isChargingCompletelyDisabled by BackupState.isChargingCompletelyDisabled.collectAsState()

        val scrollState = rememberScrollState()

        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(ObsidianBG)
                .verticalScroll(scrollState)
                .padding(16.dp)
        ) {
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "Backup Gang Manager",
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextLight
                    )
                    Text(
                        text = "Pixel XL Storage & Upload Hub v1.1.0",
                        fontSize = 13.sp,
                        color = TextMuted
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = "Net: $networkType | IP: $ipAddress",
                        fontSize = 12.sp,
                        color = if (networkType.contains("LAN")) AccentGreen else AccentCyan,
                        fontWeight = FontWeight.SemiBold
                    )
                }
                
                // Status Badge
                Box(
                    modifier = Modifier
                        .background(
                            if (isSyncing) AccentBlue.copy(alpha = 0.2f) else TextMuted.copy(alpha = 0.1f),
                            shape = RoundedCornerShape(12.dp)
                        )
                        .padding(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Text(
                        text = if (isSyncing) "ACTIVE SYNC" else "IDLE",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = if (isSyncing) AccentCyan else TextLight
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // System Complementarity & Linux Web Connector Card
            GlassCard {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "🌐 Linux Orchestrator Web Connector",
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                        color = AccentCyan
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "Web Dashboard: http://192.168.1.xxx:8000 (Port 8000)",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextLight
                    )
                    Text(
                        text = "Pixel Ktor REST API: http://$ipAddress:8080",
                        fontSize = 12.sp,
                        color = AccentGreen,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "• Linux Orchestrator (Brain): Manages iCloud downloads, EXIF date sorting into NAS Vault, metadata preservation (.meta.json), and age-based tiered compression.\n• Pixel App (Upload Engine): Handles hard-link staging to DCIM/Camera, MediaStore indexing, Google Photos unlimited backup, battery saver, and thermal guard.",
                        fontSize = 11.sp,
                        color = TextMuted,
                        lineHeight = 16.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Main Status Dashboard Card (HDD / Mount status)
            GlassCard {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (isUsbMounted) "External USB Storage" else "No USB Storage",
                            fontWeight = FontWeight.Bold,
                            fontSize = 16.sp,
                            color = TextLight
                        )
                        Text(
                            text = if (isUsbMounted) "MOUNTED (RW)" else "DISCONNECTED",
                            color = if (isUsbMounted) AccentGreen else AccentRed,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // Storage indicator
                    if (isUsbMounted && totalStorageBytes > 0L) {
                        val usedPct = usedStorageBytes.toFloat() / totalStorageBytes.toFloat()

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "${formatBytes(usedStorageBytes)} / ${formatBytes(totalStorageBytes)} Used",
                                fontSize = 12.sp,
                                color = TextLight
                            )
                            Text(
                                text = "${(usedPct * 100).toInt()}%",
                                fontSize = 12.sp,
                                color = TextMuted
                            )
                        }
                        Spacer(modifier = Modifier.height(6.dp))
                        LinearProgressIndicator(
                            progress = usedPct,
                            color = AccentCyan,
                            trackColor = Color.White.copy(alpha = 0.1f),
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(6.dp)
                        )
                    } else {
                        Text(
                            text = if (availableDevices.isNotEmpty()) "USB device detected. Please select a partition below and Mount." else "Please connect an external USB storage drive.",
                            fontSize = 13.sp,
                            color = TextMuted
                        )
                    }
                }
            }

            // USB Device Partition Selector Card
            if (availableDevices.isNotEmpty()) {
                Spacer(modifier = Modifier.height(12.dp))
                GlassCard {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Select USB Device Partition",
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp,
                            color = AccentCyan
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        availableDevices.forEach { device ->
                            val isSelected = device.path == selectedDevicePath || (selectedDevicePath.isEmpty() && device == availableDevices.first())
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        BackupState.setSelectedDevicePath(applicationContext, device.path)
                                    }
                                    .background(
                                        if (isSelected) AccentCyan.copy(alpha = 0.15f) else Color.Transparent,
                                        shape = RoundedCornerShape(8.dp)
                                    )
                                    .border(
                                        width = 1.dp,
                                        color = if (isSelected) AccentCyan else Color.Transparent,
                                        shape = RoundedCornerShape(8.dp)
                                    )
                                    .padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column {
                                    Text(
                                        text = device.path,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TextLight
                                    )
                                    Text(
                                        text = "Label: ${device.label} | FS: ${device.type} | Size: ${formatBytes(device.sizeBytes)}",
                                        fontSize = 11.sp,
                                        color = TextMuted
                                    )
                                }
                                if (isSelected) {
                                    Text(
                                        text = "SELECTED",
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = AccentCyan
                                    )
                                }
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
                var isFormatting by remember { mutableStateOf(false) }
                val targetDev = if (selectedDevicePath.isNotEmpty()) selectedDevicePath else availableDevices.firstOrNull()?.path ?: ""

                GlassCard {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Format & Prepare USB Partition",
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp,
                            color = AccentCyan
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "WARNING: Formatting is destructive. It will erase ALL data on the selected partition: $targetDev.",
                            fontSize = 12.sp,
                            color = AccentRed,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "This will format the partition, auto-mount it, and pre-create the necessary sync directory structures (shares/Amit/Photographs) with full read/write permissions.",
                            fontSize = 11.sp,
                            color = TextMuted
                        )
                        Spacer(modifier = Modifier.height(12.dp))

                        if (isFormatting) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                CircularProgressIndicator(color = AccentCyan, modifier = Modifier.size(20.dp))
                                Text(
                                    text = "Formatting and preparing drive...",
                                    color = AccentCyan,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        } else {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                Button(
                                    onClick = {
                                        if (targetDev.isNotEmpty()) {
                                            isFormatting = true
                                            CoroutineScope(Dispatchers.IO).launch {
                                                val success = MountHelper.formatPartition(targetDev, "fat32")
                                                withContext(Dispatchers.Main) {
                                                    isFormatting = false
                                                    if (success) {
                                                        Toast.makeText(this@MainActivity, "FAT32 Format Complete", Toast.LENGTH_LONG).show()
                                                        BackupState.setUsbMounted(MountHelper.isDriveMounted())
                                                        val (used, total) = MountHelper.getStorageInfo()
                                                        BackupState.setStorageInfo(used, total)
                                                    } else {
                                                        Toast.makeText(this@MainActivity, "FAT32 Format Failed!", Toast.LENGTH_LONG).show()
                                                    }
                                                }
                                            }
                                        }
                                    },
                                    modifier = Modifier.weight(1f),
                                    colors = ButtonDefaults.buttonColors(containerColor = AccentOrange.copy(alpha = 0.8f))
                                ) {
                                    Text("Format FAT32", color = Color.Black, fontWeight = FontWeight.Bold)
                                }

                                Button(
                                    onClick = {
                                        if (targetDev.isNotEmpty()) {
                                            isFormatting = true
                                            CoroutineScope(Dispatchers.IO).launch {
                                                val success = MountHelper.formatPartition(targetDev, "ext4")
                                                withContext(Dispatchers.Main) {
                                                    isFormatting = false
                                                    if (success) {
                                                        Toast.makeText(this@MainActivity, "EXT4 Format Complete", Toast.LENGTH_LONG).show()
                                                        BackupState.setUsbMounted(MountHelper.isDriveMounted())
                                                        val (used, total) = MountHelper.getStorageInfo()
                                                        BackupState.setStorageInfo(used, total)
                                                    } else {
                                                        Toast.makeText(this@MainActivity, "EXT4 Format Failed!", Toast.LENGTH_LONG).show()
                                                    }
                                                }
                                            }
                                        }
                                    },
                                    modifier = Modifier.weight(1f),
                                    colors = ButtonDefaults.buttonColors(containerColor = AccentRed.copy(alpha = 0.8f))
                                ) {
                                    Text("Format EXT4", color = TextLight, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Sync orchestrator panel
            GlassCard {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Pipeline Orchestration",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = TextLight
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    if (isSyncing) {
                        Text(
                            text = "Processing Batch: $currentFolder",
                            fontSize = 13.sp,
                            color = AccentCyan,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = "Folders: $completedFolders / $totalFolders completed",
                                    fontSize = 12.sp,
                                    color = TextLight
                                )
                                Text(
                                    text = "Staged batch sync: $syncedCount / $totalCount files",
                                    fontSize = 12.sp,
                                    color = TextMuted
                                )
                            }
                            CircularProgressIndicator(
                                progress = if (totalCount > 0) syncedCount.toFloat() / totalCount.toFloat() else 0f,
                                color = AccentCyan,
                                trackColor = Color.White.copy(alpha = 0.1f),
                                modifier = Modifier.size(36.dp)
                            )
                        }
                    } else {
                        Text(
                            text = "Pipeline is idle. Mount drive and press Start Sync.",
                            fontSize = 13.sp,
                            color = TextMuted
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Thermal and Battery health
            GlassCard {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "System Diagnostics & Safety",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = TextLight
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            val tempColor = when {
                                cpuTemp > 45f -> AccentRed
                                cpuTemp > 42f -> AccentOrange
                                else -> AccentGreen
                            }
                            Text(
                                text = "CPU Temperature: ${String.format("%.1f", cpuTemp)}°C",
                                color = tempColor,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Battery: $batteryLevel% (${if (isCharging) "Charging" else "Suspended/Discharging"})",
                                fontSize = 12.sp,
                                color = TextLight
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Upload & System Control Settings Card
            GlassCard {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Upload & System Controls",
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = AccentCyan
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Enable Google Photos Upload", fontSize = 14.sp, color = TextLight)
                            Text("Pixel 1 OG Free Unlimited Backup Engine", fontSize = 11.sp, color = TextMuted)
                        }
                        Switch(
                            checked = isPixelUploadEnabled,
                            onCheckedChange = { BackupState.setPixelUploadEnabled(applicationContext, it) },
                            colors = SwitchDefaults.colors(checkedThumbColor = AccentCyan, checkedTrackColor = AccentCyan.copy(alpha = 0.3f))
                        )
                    }
                    
                    Divider(color = Color.White.copy(alpha = 0.1f), modifier = Modifier.padding(vertical = 8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Screen Always Active (Upload Mode)", fontSize = 14.sp, color = TextLight)
                            Text("Keeps Google Photos actively syncing", fontSize = 11.sp, color = TextMuted)
                        }
                        Switch(
                            checked = isScreenAlwaysActive,
                            onCheckedChange = { BackupState.setScreenAlwaysActive(applicationContext, it) },
                            colors = SwitchDefaults.colors(checkedThumbColor = AccentOrange, checkedTrackColor = AccentOrange.copy(alpha = 0.3f))
                        )
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Battery Saver (Limit 70-80%)", fontSize = 14.sp, color = TextLight)
                            Text("Saves battery life & NAND health", fontSize = 11.sp, color = TextMuted)
                        }
                        Switch(
                            checked = isBatteryLimiterEnabled,
                            onCheckedChange = { BackupState.setBatteryLimiterEnabled(applicationContext, it) },
                            colors = SwitchDefaults.colors(checkedThumbColor = AccentGreen, checkedTrackColor = AccentGreen.copy(alpha = 0.3f))
                        )
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Disable Charging Completely", fontSize = 14.sp, color = TextLight)
                            Text("Bypass battery to increase lifespan", fontSize = 11.sp, color = TextMuted)
                        }
                        Switch(
                            checked = isChargingCompletelyDisabled,
                            onCheckedChange = { BackupState.setChargingCompletelyDisabled(applicationContext, it) },
                            colors = SwitchDefaults.colors(checkedThumbColor = AccentRed, checkedTrackColor = AccentRed.copy(alpha = 0.3f))
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Control Buttons Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Mount / Unmount Toggle Button
                Button(
                    onClick = {
                        CoroutineScope(Dispatchers.IO).launch {
                            if (isUsbMounted) {
                                val unmounted = MountHelper.unmountDrive()
                                withContext(Dispatchers.Main) {
                                    if (unmounted) {
                                        Toast.makeText(this@MainActivity, "Cleanly Unmounted", Toast.LENGTH_SHORT).show()
                                    } else {
                                        Toast.makeText(this@MainActivity, "Unmount Failed!", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            } else {
                                val mounted = MountHelper.mountDrive()
                                withContext(Dispatchers.Main) {
                                    if (mounted) {
                                        Toast.makeText(this@MainActivity, "Mounted successfully", Toast.LENGTH_SHORT).show()
                                    } else {
                                        Toast.makeText(this@MainActivity, "Mount failed! Check logs.", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            }
                        }
                    },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isUsbMounted) AccentOrange else AccentGreen
                    )
                ) {
                    Text(
                        text = if (isUsbMounted) "Unmount Drive" else "Mount Drive",
                        color = Color.Black,
                        fontWeight = FontWeight.Bold
                    )
                }

                // Sync Start / Stop Button
                Button(
                    onClick = {
                        val serviceIntent = Intent(this@MainActivity, BackupService::class.java).apply {
                            action = if (isSyncing) "STOP_SYNC" else "START_SYNC"
                        }
                        startService(serviceIntent)
                    },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isSyncing) AccentRed else AccentBlue
                    )
                ) {
                    Text(
                        text = if (isSyncing) "Stop Sync" else "Start Sync",
                        color = TextLight,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Terminal Console card
            Text(
                text = "Console logs",
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                color = TextLight,
                modifier = Modifier.padding(bottom = 6.dp)
            )

            Box(
                modifier = Modifier
                    .height(240.dp)
                    .fillMaxWidth()
                    .border(1.dp, GlassBorder, RoundedCornerShape(12.dp))
                    .background(Color(0xFF08080A))
                    .padding(8.dp)
            ) {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    reverseLayout = false
                ) {
                    items(logs) { log ->
                        Text(
                            text = log,
                            fontFamily = FontFamily.Monospace,
                            fontSize = 11.sp,
                            color = if (log.contains("ERROR")) AccentRed else if (log.contains(">>>") || log.contains("<<<")) AccentCyan else TextLight,
                            modifier = Modifier.padding(vertical = 1.dp)
                        )
                    }
                }
            }
        }
    }

    @Composable
    fun GlassCard(
        content: @Composable ColumnScope.() -> Unit
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .border(1.dp, GlassBorder, RoundedCornerShape(16.dp)),
            colors = CardDefaults.cardColors(containerColor = CardBackground),
            shape = RoundedCornerShape(16.dp),
            content = content
        )
    }
}
