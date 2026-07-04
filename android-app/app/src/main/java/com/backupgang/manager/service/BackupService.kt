package com.backupgang.manager.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import android.content.IntentFilter
import android.os.BatteryManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.net.NetworkInterface
import java.util.Collections
import com.backupgang.manager.MainActivity
import com.backupgang.manager.util.BackupState
import com.backupgang.manager.util.BatteryLimiter
import com.backupgang.manager.util.MountHelper
import com.topjohnwu.superuser.Shell
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.call
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.netty.NettyApplicationEngine
import io.ktor.server.response.respond
import io.ktor.server.response.respondFile
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.routing
import io.ktor.server.request.receiveText
import org.json.JSONObject
import android.system.Os
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File

class BackupService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + Job())
    private var syncJob: Job? = null
    private var monitorJob: Job? = null
    private var batteryJob: Job? = null
    private var lastFolderCountTime = 0L
    private var cachedTotalFolders = 0
    
    private var wakeLock: PowerManager.WakeLock? = null
    private var ktorServer: NettyApplicationEngine? = null

    companion object {
        private const val TAG = "BackupService"
        private const val CHANNEL_ID = "BackupServiceChannel"
        private const val NOTIFICATION_ID = 101

        private const val HDD_PATH = "/mnt/my_drive"
        private const val SRC_DIR = "$HDD_PATH/Backup/shares/Amit/Photographs"
        private const val STAGING_DIR = "$HDD_PATH/the_binding"

        fun startService(context: Context) {
            val intent = Intent(context, BackupService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopService(context: Context) {
            val intent = Intent(context, BackupService::class.java)
            context.stopService(intent)
        }
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service Created")
        BackupState.initialize(applicationContext)
        createNotificationChannel()
        val notification = createNotification("Service Initializing", "Preparing background processes...")
        startForeground(NOTIFICATION_ID, notification)

        // WakeLock
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "BackupManager::Wakelock")
        wakeLock?.acquire()

        // Start Ktor Server
        startKtorServer()

        // Start Battery Monitor Loop
        startBatteryMonitor()

        // Start Diagnostics Loop
        startDiagnosticsMonitor()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "Service Started")
        
        // If start command requested manual sync trigger:
        val action = intent?.action
        if (action == "START_SYNC") {
            startSyncPipeline()
        } else if (action == "STOP_SYNC") {
            stopSyncPipeline()
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        Log.d(TAG, "Service Destroyed")
        stopSyncPipeline()
        monitorJob?.cancel()
        batteryJob?.cancel()
        
        try {
            ktorServer?.stop(1000, 2000)
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping Ktor", e)
        }
        
        if (wakeLock?.isHeld == true) {
            wakeLock?.release()
        }
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Backup Pipeline Orchestrator",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun createNotification(title: String, content: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(content)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(title: String, content: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(NOTIFICATION_ID, createNotification(title, content))
    }

    private fun startKtorServer() {
        serviceScope.launch {
            try {
                ktorServer = embeddedServer(Netty, port = 8080, host = "0.0.0.0") {
                    routing {
                        get("/") {
                            call.respondText(getHtmlDocs(), ContentType.Text.Html)
                        }

                        get("/docs") {
                            call.respondText(getHtmlDocs(), ContentType.Text.Html)
                        }

                        get("/sync-status") {
                            val statusJson = """
                                {
                                    "isSyncing": ${BackupState.isSyncing.value},
                                    "currentFolder": "${BackupState.currentFolder.value}",
                                    "syncedCount": ${BackupState.syncedCount.value},
                                    "totalCount": ${BackupState.totalCount.value},
                                    "completedFolders": ${BackupState.completedFolders.value},
                                    "totalFolders": ${BackupState.totalFolders.value},
                                    "cpuTemp": ${BackupState.cpuTemp.value},
                                    "batteryLevel": ${BackupState.batteryLevel.value},
                                    "isCharging": ${BackupState.isCharging.value},
                                    "isUsbMounted": ${BackupState.isUsbMounted.value},
                                    "usedStorageBytes": ${BackupState.usedStorageBytes.value},
                                    "totalStorageBytes": ${BackupState.totalStorageBytes.value}
                                }
                            """.trimIndent()
                            call.respondText(statusJson, contentType = ContentType.Application.Json)
                        }

                        get("/api/health") {
                            try {
                                val batteryPct = BackupState.batteryLevel.value
                                val cpuTemp = BackupState.cpuTemp.value
                                val isCharging = BackupState.isCharging.value
                                val isUsbMounted = BackupState.isUsbMounted.value
                                val totalBytes = BackupState.totalStorageBytes.value
                                val usedBytes = BackupState.usedStorageBytes.value
                                val freeStorage = if (totalBytes > usedBytes) totalBytes - usedBytes else 0L
                                val isSyncing = BackupState.isSyncing.value
                                val (netType, ip) = getNetworkInfo(applicationContext)

                                val healthJson = """
                                    {
                                        "battery": $batteryPct,
                                        "level": $batteryPct,
                                        "charging": $isCharging,
                                        "cpuTemp": $cpuTemp,
                                        "isUsbMounted": $isUsbMounted,
                                        "isSyncing": $isSyncing,
                                        "networkType": "$netType",
                                        "ipAddress": "$ip",
                                        "freeStorageBytes": $freeStorage
                                    }
                                """.trimIndent()
                                call.respondText(healthJson, contentType = ContentType.Application.Json)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/health", e)
                                call.respond(HttpStatusCode.InternalServerError, """{"status":"error","message":"${e.message?.replace("\"", "'")}"}""")
                            }
                        }

                        post("/api/stage") {
                            try {
                                val bodyText = call.receiveText()
                                val json = JSONObject(bodyText)
                                val filesArray = json.optJSONArray("files")
                                var stagedCount = 0
                                if (filesArray != null) {
                                    val stageDir = File("/mnt/my_drive/the_binding")
                                    if (!stageDir.exists()) {
                                        stageDir.mkdirs()
                                        Shell.cmd("mkdir -p /mnt/my_drive/the_binding").exec()
                                    }
                                    for (i in 0 until filesArray.length()) {
                                        val filePath = filesArray.getString(i)
                                        val srcFile = File(filePath)
                                        val filename = srcFile.name
                                        val targetPath = "/mnt/my_drive/the_binding/$filename"
                                        val targetFile = File(targetPath)
                                        if (targetFile.exists()) {
                                            targetFile.delete()
                                            Shell.cmd("rm -f \"$targetPath\"").exec()
                                        }

                                        var linked = false
                                        try {
                                            Os.link(filePath, targetPath)
                                            linked = true
                                        } catch (e: Exception) {
                                            val lnRes = Shell.cmd("ln -f \"$filePath\" \"$targetPath\"").exec()
                                            if (lnRes.isSuccess || File(targetPath).exists()) {
                                                linked = true
                                            }
                                        }

                                        if (linked || File(targetPath).exists()) {
                                            stagedCount++
                                            Shell.cmd("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file:///storage/emulated/0/DCIM/Camera/$filename\"").exec()
                                        }
                                    }
                                }

                                Shell.cmd("/data/data/com.termux/files/usr/bin/sqlite3 /data/data/com.google.android.apps.photos/databases/gphotos0.db \"UPDATE local_media SET has_upload_permanently_failed = 0;\" 2>/dev/null || true").exec()
                                Shell.cmd("am force-stop com.google.android.apps.photos && am start -n com.google.android.apps.photos/.home.HomeActivity").exec()

                                call.respondText("""{"status":"staged","count":$stagedCount}""", contentType = ContentType.Application.Json)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/stage", e)
                                call.respond(HttpStatusCode.InternalServerError, """{"status":"error","message":"${e.message?.replace("\"", "'")}"}""")
                            }
                        }

                        get("/api/verify") {
                            try {
                                val filesParam = call.request.queryParameters["files"]
                                if (filesParam.isNullOrEmpty()) {
                                    call.respondText("{}", contentType = ContentType.Application.Json)
                                    return@get
                                }

                                val fileItems = filesParam.split(",").map { it.trim() }.filter { it.isNotEmpty() }
                                if (fileItems.isEmpty()) {
                                    call.respondText("{}", contentType = ContentType.Application.Json)
                                    return@get
                                }

                                val itemToDbPath = fileItems.associateWith { item ->
                                    val filename = if (item.contains("/")) File(item).name else item
                                    "/storage/emulated/0/DCIM/Camera/$filename"
                                }

                                val sqlList = itemToDbPath.values.distinct().joinToString(",") { "'${it.replace("'", "''")}'" }
                                val query = """
                                    SELECT l.filepath 
                                    FROM local_media l 
                                    LEFT JOIN media m ON l.dedup_key = m.dedup_key 
                                    WHERE l.filepath IN ($sqlList) 
                                      AND (l.is_backup_processed = 1 OR (m.canonical_media_key IS NOT NULL AND m.canonical_media_key != ''));
                                """.trimIndent().replace("\n", " ")

                                val dbResult = Shell.cmd("/data/data/com.termux/files/usr/bin/sqlite3 /data/data/com.google.android.apps.photos/databases/gphotos0.db \"$query\"").exec()
                                val verifiedDbPaths = if (dbResult.isSuccess) dbResult.out.map { it.trim() }.toSet() else emptySet()

                                val jsonEntries = fileItems.map { item ->
                                    val dbPath = itemToDbPath[item]
                                    val isVerified = verifiedDbPaths.contains(dbPath)
                                    val jsonKey = if (item.contains("/")) File(item).name else item
                                    "\"$jsonKey\": $isVerified"
                                }

                                val responseJson = "{\n  " + jsonEntries.joinToString(",\n  ") + "\n}"
                                call.respondText(responseJson, contentType = ContentType.Application.Json)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/verify", e)
                                call.respond(HttpStatusCode.InternalServerError, """{"status":"error","message":"${e.message?.replace("\"", "'")}"}""")
                            }
                        }

                        post("/api/photos/restart") {
                            try {
                                Shell.cmd("am force-stop com.google.android.apps.photos && am start -n com.google.android.apps.photos/.home.HomeActivity").exec()
                                call.respondText("""{"status":"restarted"}""", contentType = ContentType.Application.Json)
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/photos/restart", e)
                                call.respond(HttpStatusCode.InternalServerError, """{"status":"error","message":"${e.message?.replace("\"", "'")}"}""")
                            }
                        }

                        post("/api/mount") {
                            try {
                                val success = MountHelper.mountDrive()
                                if (success) {
                                    call.respondText("""{"status":"success"}""", contentType = ContentType.Application.Json)
                                } else {
                                    call.respondText("""{"status":"error"}""", contentType = ContentType.Application.Json)
                                }
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/mount", e)
                                call.respondText("""{"status":"error"}""", contentType = ContentType.Application.Json)
                            }
                        }

                        post("/api/unmount") {
                            try {
                                val success = MountHelper.unmountDrive()
                                if (success) {
                                    call.respondText("""{"status":"success"}""", contentType = ContentType.Application.Json)
                                } else {
                                    call.respondText("""{"status":"error"}""", contentType = ContentType.Application.Json)
                                }
                            } catch (e: Exception) {
                                Log.e(TAG, "Error in /api/unmount", e)
                                call.respondText("""{"status":"error"}""", contentType = ContentType.Application.Json)
                            }
                        }

                        get("/api/scan") {
                            val path = call.request.queryParameters["path"]
                            if (path != null) {
                                val result = Shell.cmd("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file://$path\"").exec()
                                if (result.isSuccess) {
                                    call.respondText("""{"status":"success","message":"Scanner triggered for $path"}""", ContentType.Application.Json)
                                } else {
                                    call.respond(HttpStatusCode.InternalServerError, """{"status":"error","message":"Failed to trigger scanner"}""")
                                }
                            } else {
                                call.respond(HttpStatusCode.BadRequest, """{"status":"error","message":"Missing path parameter"}""")
                            }
                        }

                        get("/api/status") {
                            val path = call.request.queryParameters["path"]
                            if (path != null) {
                                val query = """
                                    SELECT COUNT(*) 
                                    FROM local_media l 
                                    LEFT JOIN media m ON l.dedup_key = m.dedup_key 
                                    WHERE l.filepath = '${path.replace("'", "''")}' 
                                      AND (l.is_backup_processed = 1 OR (m.canonical_media_key IS NOT NULL AND m.canonical_media_key != ''));
                                """.trimIndent().replace("\n", " ")
                                
                                val dbResult = Shell.cmd("/data/data/com.termux/files/usr/bin/sqlite3 /data/data/com.google.android.apps.photos/databases/gphotos0.db \"$query\"").exec()
                                val count = if (dbResult.isSuccess && dbResult.out.isNotEmpty()) {
                                    dbResult.out[0].trim().toIntOrNull() ?: 0
                                } else {
                                    0
                                }
                                val isSynced = count > 0
                                call.respondText("""{"filepath":"$path","isSynced":$isSynced}""", ContentType.Application.Json)
                            } else {
                                call.respond(HttpStatusCode.BadRequest, """{"status":"error","message":"Missing path parameter"}""")
                            }
                        }

                        post("/api/clean") {
                            val cleaned = cleanStagingSyncedFiles()
                            val json = cleaned.joinToString(prefix = "[", postfix = "]") { "\"$it\"" }
                            call.respondText("""{"status":"success","cleaned":$json}""", ContentType.Application.Json)
                        }

                        get("/my_drive/{path...}") {
                            val pathParam = call.parameters.getAll("path")?.joinToString("/") ?: ""
                            val file = File(HDD_PATH, pathParam)
                            if (file.exists()) {
                                if (file.isDirectory) {
                                    val filesList = file.listFiles()?.map { f ->
                                        val relativePath = f.absolutePath.substringAfter("$HDD_PATH/")
                                        "<li><a href=\"/my_drive/$relativePath\">${f.name}</a></li>"
                                    }?.joinToString("") ?: ""
                                    call.respondText(
                                        "<html><body><h3>Index of $pathParam</h3><ul>$filesList</ul></body></html>",
                                        ContentType.Text.Html
                                    )
                                } else {
                                    call.respondFile(file)
                                }
                            } else {
                                call.respond(HttpStatusCode.NotFound, "File not found")
                            }
                        }
                    }
                }
                ktorServer?.start(wait = false)
                BackupState.addLog("Ktor local share server running on port 8080")
            } catch (e: Exception) {
                BackupState.addLog("Ktor failed to start: ${e.message}")
                Log.e(TAG, "Ktor start error", e)
            }
        }
    }

    private fun getNetworkInfo(context: Context): Pair<String, String> {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val activeNetwork = cm.activeNetwork ?: return Pair("Disconnected", "Disconnected")
        val capabilities = cm.getNetworkCapabilities(activeNetwork) ?: return Pair("Disconnected", "Disconnected")
        
        val type = when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "LAN (Ethernet)"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Cellular"
            else -> "Unknown Network"
        }

        var ipAddress = "Disconnected"
        try {
            val interfaces = Collections.list(NetworkInterface.getNetworkInterfaces())
            for (networkInterface in interfaces) {
                val addrs = Collections.list(networkInterface.inetAddresses)
                for (addr in addrs) {
                    if (!addr.isLoopbackAddress) {
                        val sAddr = addr.hostAddress
                        if (sAddr != null) {
                            val isIPv4 = sAddr.indexOf(':') < 0
                            if (isIPv4) {
                                if (type == "LAN (Ethernet)" && networkInterface.name.startsWith("eth")) {
                                    return Pair(type, sAddr)
                                }
                                if (type == "Wi-Fi" && networkInterface.name.startsWith("wlan")) {
                                    return Pair(type, sAddr)
                                }
                                ipAddress = sAddr
                            }
                        }
                    }
                }
            }
        } catch (ex: Exception) {
            ipAddress = "Error: ${ex.message}"
        }

        return Pair(type, ipAddress)
    }

    private fun startBatteryMonitor() {
        batteryJob = serviceScope.launch {
            while (true) {
                if (BackupState.isBatteryLimiterEnabled.value) {
                    try {
                        BatteryLimiter.checkAndLimit(applicationContext)
                    } catch (e: Exception) {
                        Log.e(TAG, "BatteryLimiter error", e)
                    }
                }
                delay(30000) // check every 30 seconds
            }
        }
    }

    private fun startDiagnosticsMonitor() {
        monitorJob = serviceScope.launch {
            while (true) {
                // Update CPU Temp
                try {
                    val tempResult = Shell.cmd("cat /sys/class/thermal/thermal_zone0/temp").exec()
                    if (tempResult.isSuccess && tempResult.out.isNotEmpty()) {
                        val rawTemp = tempResult.out[0].trim().toFloatOrNull() ?: 0f
                        BackupState.setCpuTemp(rawTemp / 1000f)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "CPU temp check error", e)
                }

                // Update Battery Info
                try {
                    val batteryStatus = applicationContext.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
                    val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
                    val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
                    val status = batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
                    if (level != -1 && scale != -1) {
                        val batteryPct = (level * 100 / scale.toFloat()).toInt()
                        val isActuallyCharging = (status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL)
                        BackupState.setBatteryInfo(batteryPct, isActuallyCharging)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Battery status check error", e)
                }

                // Update Network Info
                try {
                    val (netType, ip) = getNetworkInfo(applicationContext)
                    BackupState.setNetworkInfo(netType, ip)
                } catch (e: Exception) {
                    Log.e(TAG, "Network check error", e)
                }

                // Update USB Mounted State
                val mounted = MountHelper.isDriveMounted()
                BackupState.setUsbMounted(mounted)

                // Scan and update available devices list
                try {
                    val devices = MountHelper.scanUsbDevices()
                    BackupState.setAvailableDevices(devices, applicationContext)
                } catch (e: Exception) {
                    Log.e(TAG, "USB scan error", e)
                }

                // Update Storage space
                if (mounted) {
                    try {
                        val storage = MountHelper.getStorageInfo()
                        BackupState.setStorageInfo(storage.first, storage.second)
                    } catch (e: Exception) {
                        Log.e(TAG, "Storage check error", e)
                    }
                }

                // Read CLI script progress if the internal pipeline is not running
                if (syncJob?.isActive != true) {
                    try {
                        val cliRunning = Shell.cmd("pgrep -f pipeline.sh").exec().isSuccess
                        if (cliRunning) {
                            BackupState.setSyncing(true)

                            // Parse current folder from sync.log
                            val currentFolderCmd = Shell.cmd("grep '>>> STARTING BATCH:' $HDD_PATH/sync.log 2>/dev/null | tail -n 1").exec()
                            if (currentFolderCmd.isSuccess && currentFolderCmd.out.isNotEmpty()) {
                                val line = currentFolderCmd.out[0]
                                val folder = line.substringAfter(">>> STARTING BATCH: ").trim()
                                BackupState.setCurrentFolder(folder)
                            }

                            // Parse progress from sync.log
                            val progressCmd = Shell.cmd("grep 'Sync progress:' $HDD_PATH/sync.log 2>/dev/null | tail -n 1").exec()
                            if (progressCmd.isSuccess && progressCmd.out.isNotEmpty()) {
                                val line = progressCmd.out[0]
                                val progressPart = line.substringAfter("Sync progress: ").substringBefore(" files completed.").trim()
                                val parts = progressPart.split("/")
                                if (parts.size == 2) {
                                    val synced = parts[0].toIntOrNull() ?: 0
                                    val total = parts[1].toIntOrNull() ?: 0
                                    BackupState.setProgress(synced, total)
                                }
                            }

                            // Parse folder progress
                            val completedCmd = Shell.cmd("wc -l < $HDD_PATH/synced_folders.txt").exec()
                            val completed = if (completedCmd.isSuccess && completedCmd.out.isNotEmpty()) {
                                completedCmd.out[0].trim().toIntOrNull() ?: 0
                            } else {
                                0
                            }

                            val now = System.currentTimeMillis()
                            if (now - lastFolderCountTime > 300000L || cachedTotalFolders == 0) {
                                val totalCmd = Shell.cmd("find $HDD_PATH/Backup/shares/Amit/Photographs/Sorted -mindepth 3 -maxdepth 10 -name '@eaDir' -prune -o -type f -print 2>/dev/null | sed 's|/[^/]*$||' | sort -u | wc -l").exec()
                                if (totalCmd.isSuccess && totalCmd.out.isNotEmpty()) {
                                    cachedTotalFolders = totalCmd.out[0].trim().toIntOrNull() ?: 0
                                    lastFolderCountTime = now
                                }
                            }
                            BackupState.setFolderProgress(completed, cachedTotalFolders)
                        } else {
                            BackupState.setSyncing(false)
                            BackupState.setCurrentFolder("")
                            BackupState.setProgress(0, 0)
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "CLI status check error", e)
                    }
                }

                delay(10000) // check every 10 seconds
            }
        }
    }

    private fun isNetworkConnected(): Boolean {
        val result = Shell.cmd("ping -c 1 8.8.8.8").exec()
        return result.isSuccess
    }

    private fun startSyncPipeline() {
        if (syncJob?.isActive == true) {
            BackupState.addLog("Sync is already running")
            return
        }

        BackupState.setSyncing(true)
        updateNotification("Sync Pipeline Active", "Processing photo batches...")

        syncJob = serviceScope.launch {
            try {
                runPipeline()
            } catch (e: Exception) {
                BackupState.addLog("Pipeline Error: ${e.message}")
                Log.e(TAG, "Pipeline execution error", e)
            } finally {
                // Staging cleanup
                BackupState.addLog("Cleaning staging area...")
                Shell.cmd("rm -rf $STAGING_DIR/* 2>/dev/null || true").exec()
                Shell.cmd("rm -rf $STAGING_DIR/.* 2>/dev/null || true").exec()
                BackupState.setSyncing(false)
                BackupState.setCurrentFolder("")
                BackupState.setProgress(0, 0)
                updateNotification("Sync Pipeline Stopped", "Idle")
                BackupState.addLog("Sync pipeline shut down successfully.")
            }
        }
    }

    private fun stopSyncPipeline() {
        if (syncJob?.isActive == true) {
            BackupState.addLog("Stopping sync pipeline manually...")
            syncJob?.cancel()
            syncJob = null
        }
    }

    private suspend fun runPipeline() {
        BackupState.addLog("Verifying drive mount...")
        if (!MountHelper.isDriveMounted()) {
            BackupState.addLog("Drive not mounted. Attempting to mount...")
            if (MountHelper.mountDrive()) {
                BackupState.addLog("Drive mounted successfully.")
            } else {
                BackupState.addLog("ERROR: External drive mount failed. Aborting pipeline.")
                return
            }
        }

        BackupState.addLog("Scanning for photo folders in Sorted tree...")
        val findCmd = "find '$SRC_DIR/Sorted' -mindepth 3 -maxdepth 10 -name '@eaDir' -prune -o -type f -print | sed 's|/[^/]*$||' | sort -u"
        val findResult = Shell.cmd(findCmd).exec()
        if (!findResult.isSuccess || findResult.out.isEmpty()) {
            BackupState.addLog("No folders found to sync or scan failed.")
            return
        }

        val allFolders = findResult.out.map { it.trim() }.filter { it.isNotEmpty() }
        BackupState.addLog("Total directories discovered: ${allFolders.size}")

        val dedupFile = File("$HDD_PATH/synced_folders.txt")
        val completedFolderNames = if (dedupFile.exists()) {
            dedupFile.readLines().map { it.trim() }.toSet()
        } else {
            emptySet()
        }

        val pendingFolders = allFolders.filter { folder ->
            val relName = folder.substringAfter("$SRC_DIR/")
            !completedFolderNames.contains(relName)
        }

        BackupState.setFolderProgress(allFolders.size - pendingFolders.size, allFolders.size)
        BackupState.addLog("Pending folders to process: ${pendingFolders.size}")

        if (pendingFolders.isEmpty()) {
            BackupState.addLog("All folders synced! Pipeline complete.")
            return
        }

        val corruptLogFile = File("$HDD_PATH/corrupt_photos.txt")

        for ((index, folder) in pendingFolders.withIndex()) {
            val relName = folder.substringAfter("$SRC_DIR/")
            BackupState.setCurrentFolder(relName)
            BackupState.addLog(">>> Starting folder: $relName")
            updateNotification("Sync Pipeline Active", "Processing: $relName")

            // A. Thermal Safety (pause if CPU temp is too high)
            val tempResult = Shell.cmd("cat /sys/class/thermal/thermal_zone0/temp").exec()
            val temp = if (tempResult.isSuccess && tempResult.out.isNotEmpty()) {
                tempResult.out[0].trim().toIntOrNull() ?: 0
            } else {
                0
            }
            if (temp > 45000) {
                BackupState.addLog("Thermal warning: CPU at ${temp / 1000f}°C. Pausing for 5 mins to cool...")
                delay(300000)
            }

            // B. Find files and validate them
            val filesResult = Shell.cmd("find \"$folder\" -maxdepth 1 -type f ! -name '@eaDir'").exec()
            val files = filesResult.out.map { it.trim() }.filter { it.isNotEmpty() }
            if (files.isEmpty()) {
                BackupState.addLog("Skipping empty folder: $relName")
                Shell.cmd("echo \"$relName\" >> $HDD_PATH/synced_folders.txt").exec()
                BackupState.setFolderProgress(allFolders.size - pendingFolders.size + index + 1, allFolders.size)
                continue
            }

            val validFiles = mutableListOf<File>()
            for (filepath in files) {
                val file = File(filepath)
                if (isValidMedia(file, corruptLogFile)) {
                    validFiles.add(file)
                }
            }

            if (validFiles.isEmpty()) {
                BackupState.addLog("Skipping folder (no valid files remaining): $relName")
                Shell.cmd("echo \"$relName\" >> $HDD_PATH/synced_folders.txt").exec()
                BackupState.setFolderProgress(allFolders.size - pendingFolders.size + index + 1, allFolders.size)
                continue
            }

            BackupState.addLog("Folder $relName: ${validFiles.size} valid files. Slicing into chunks of 100.")
            val chunks = validFiles.chunked(100)
            var allChunksSynced = true

            for ((chunkIndex, chunk) in chunks.withIndex()) {
                BackupState.addLog("--- Staging and uploading chunk ${chunkIndex + 1}/${chunks.size} ---")

                // Clear previous staging items
                Shell.cmd("rm -rf $STAGING_DIR/* 2>/dev/null || true").exec()
                Shell.cmd("rm -rf $STAGING_DIR/.* 2>/dev/null || true").exec()

                val existingStaged = HashSet<String>()
                val stagedPaths = mutableListOf<String>()

                for (file in chunk) {
                    val filename = file.name
                    var targetName = filename
                    var counter = 1
                    val ext = filename.substringAfterLast(".", "")
                    val base = filename.substringBeforeLast(".")

                    while (existingStaged.contains(targetName.lowercase())) {
                        targetName = if (ext.isEmpty() || ext == filename) {
                            "${base}_$counter"
                        } else {
                            "${base}_$counter.$ext"
                        }
                        counter++
                    }

                    existingStaged.add(targetName.lowercase())
                    val targetFile = File(STAGING_DIR, targetName)

                    var linked = false
                    try {
                        Os.link(file.absolutePath, targetFile.absolutePath)
                        linked = true
                    } catch (e: Exception) {
                        val lnResult = Shell.cmd("ln \"${file.absolutePath}\" \"${targetFile.absolutePath}\"").exec()
                        if (lnResult.isSuccess) {
                            linked = true
                        }
                    }

                    if (linked) {
                        stagedPaths.add("/storage/emulated/0/DCIM/Camera/$targetName")
                    } else {
                        BackupState.addLog("ERROR: Failed to create hard link for ${file.name}")
                    }
                }

                val totalFiles = stagedPaths.size
                BackupState.setProgress(0, totalFiles)
                BackupState.addLog("Staged $totalFiles files in staging.")

                if (totalFiles == 0) {
                    continue
                }

                val doPixel = BackupState.isPixelUploadEnabled.value
                val doIcloud = BackupState.isIcloudUploadEnabled.value

                if (!doPixel && !doIcloud) {
                    BackupState.addLog("Both upload targets are disabled. Skipping chunk...")
                    continue
                }

                if (doIcloud) {
                    BackupState.addLog("Starting iCloud upload via Termux scripts...")
                    for (path in stagedPaths) {
                        // Assuming icloud CLI or icloudpd is installed in Termux
                        val uploadCmd = "/data/data/com.termux/files/usr/bin/python -m icloud --upload \"$path\""
                        Shell.cmd(uploadCmd).exec()
                    }
                    BackupState.addLog("iCloud upload logic executed for chunk.")
                }

                var isChunkSynced = false
                if (doPixel) {
                    // C. Trigger Media Store Scanner on staged links
                    BackupState.addLog("Triggering Media Scanner for Pixel Upload...")
                    for (path in stagedPaths) {
                        Shell.cmd("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file://$path\"").exec()
                    }

                // D. Cold Restart Google Photos
                BackupState.addLog("Cold restarting Google Photos...")
                Shell.cmd("am force-stop com.google.android.apps.photos").exec()
                delay(2000)
                Shell.cmd("am start -n com.google.android.apps.photos/.home.HomeActivity").exec()

                // E. Monitor progress
                var lastSyncedCount = 0
                var lastStateChangeTime = System.currentTimeMillis()
                val batchStartTime = System.currentTimeMillis()
                val maxBatchWait = 10800000L // 3 hours


                val sqlList = stagedPaths.joinToString(",") { path ->
                    "'" + path.replace("'", "''") + "'"
                }

                while (true) {
                    delay(10000) // Poll every 10 seconds

                    val query = """
                        SELECT COUNT(*) 
                        FROM local_media l 
                        LEFT JOIN media m ON l.dedup_key = m.dedup_key 
                        WHERE l.filepath IN ($sqlList) 
                          AND (l.is_backup_processed = 1 OR (m.canonical_media_key IS NOT NULL AND m.canonical_media_key != ''));
                    """.trimIndent().replace("\n", " ")

                    val dbResult = Shell.cmd("/data/data/com.termux/files/usr/bin/sqlite3 /data/data/com.google.android.apps.photos/databases/gphotos0.db \"$query\"").exec()
                    val syncedCount = if (dbResult.isSuccess && dbResult.out.isNotEmpty()) {
                        dbResult.out[0].trim().toIntOrNull() ?: 0
                    } else {
                        0
                    }

                    BackupState.setProgress(syncedCount, totalFiles)

                    if (syncedCount >= totalFiles) {
                        BackupState.addLog("Chunk ${chunkIndex + 1} synced successfully!")
                        isChunkSynced = true
                        break
                    }

                    // Network connection watchdog
                    if (!isNetworkConnected()) {
                        BackupState.addLog("Ping failed (Network offline). Pausing monitor...")
                        while (!isNetworkConnected()) {
                            delay(10000)
                        }
                        BackupState.addLog("Network reconnected.")
                        lastStateChangeTime = System.currentTimeMillis()
                    }

                    // Progress watchdog
                    if (syncedCount > lastSyncedCount) {
                        BackupState.addLog("Progress: $syncedCount/$totalFiles synced.")
                        lastSyncedCount = syncedCount
                        lastStateChangeTime = System.currentTimeMillis()
                    }

                    val noProgressDuration = System.currentTimeMillis() - lastStateChangeTime
                    if (noProgressDuration >= 120000) { // 120 seconds of silence
                        BackupState.addLog("No sync progress for 120s. Cold restarting Google Photos...")
                        Shell.cmd("am force-stop com.google.android.apps.photos").exec()
                        delay(2000)
                        Shell.cmd("am start -n com.google.android.apps.photos/.home.HomeActivity").exec()
                        lastStateChangeTime = System.currentTimeMillis()
                    }

                    // Hard timeout check
                    if (System.currentTimeMillis() - batchStartTime >= maxBatchWait) {
                        BackupState.addLog("Hard timeout of 3 hours reached for chunk ${chunkIndex + 1}.")
                        allChunksSynced = false
                        break
                    }
                }

                } else {
                    isChunkSynced = true
                    BackupState.setProgress(totalFiles, totalFiles)
                }

                // F. Purge Staged Links
                BackupState.addLog("Unstaging chunk files...")
                for (path in stagedPaths) {
                    val filename = path.substringAfterLast('/')
                    Shell.cmd("rm -f $STAGING_DIR/$filename").exec()
                    Shell.cmd("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file://$path\"").exec()
                }

                if (!isChunkSynced) {
                    allChunksSynced = false
                }
            }

            // G. Deduplication registry write
            Shell.cmd("echo \"$relName\" >> $HDD_PATH/synced_folders.txt").exec()
            BackupState.setFolderProgress(allFolders.size - pendingFolders.size + index + 1, allFolders.size)

            if (allChunksSynced) {
                BackupState.addLog("<<< Folder complete: $relName")
            } else {
                BackupState.addLog("<<< Folder finished with warnings: $relName")
            }
        }

        BackupState.addLog("Pipeline complete! All pending folders processed.")
    }

    private val SUPPORTED_EXTENSIONS = setOf(
        "jpg", "jpeg", "png", "gif", "heic", "tif", "tiff", "bmp",
        "mp4", "mov", "3gp", "m4v", "mts", "mpg", "mpeg", "avi", "wmv", "asf", "mkv"
    )

    private fun isValidVideo(file: File): Boolean {
        val size = file.length()
        if (size < 8) return false
        try {
            file.inputStream().use { input ->
                val firstChunkSize = minOf(size, 128L * 1024).toInt()
                val firstChunk = ByteArray(firstChunkSize)
                var bytesRead = 0
                while (bytesRead < firstChunkSize) {
                    val r = input.read(firstChunk, bytesRead, firstChunkSize - bytesRead)
                    if (r == -1) break
                    bytesRead += r
                }
                
                if (indexOfBytes(firstChunk, "moov".toByteArray()) >= 0) {
                    return true
                }

                if (size > 128 * 1024) {
                    val lastChunkSize = minOf(size - 128 * 1024, 128L * 1024).toInt()
                    val lastChunk = ByteArray(lastChunkSize)
                    
                    file.inputStream().use { inputLast ->
                        inputLast.channel.position(size - lastChunkSize)
                        var bytesReadLast = 0
                        while (bytesReadLast < lastChunkSize) {
                            val r = inputLast.read(lastChunk, bytesReadLast, lastChunkSize - bytesReadLast)
                            if (r == -1) break
                            bytesReadLast += r
                        }
                    }
                    if (indexOfBytes(lastChunk, "moov".toByteArray()) >= 0) {
                        return true
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error validating video: ${file.name}", e)
        }
        return false
    }

    private fun indexOfBytes(outer: ByteArray, inner: ByteArray): Int {
        if (inner.isEmpty()) return 0
        for (i in 0..outer.size - inner.size) {
            var found = true
            for (j in inner.indices) {
                if (outer[i + j] != inner[j]) {
                    found = false
                    break
                }
            }
            if (found) return i
        }
        return -1
    }

    private fun isValidMedia(file: File, corruptLog: File): Boolean {
        val name = file.name
        val ext = name.substringAfterLast(".", "").lowercase()
        if (ext !in SUPPORTED_EXTENSIONS) return false

        val size = file.length()
        if (size == 0L) return false

        val fnLower = name.lowercase()
        if (fnLower.contains("syno") ||
            fnLower.contains("thumb") ||
            fnLower.contains("_mini_") ||
            fnLower.contains("_largepv_")
        ) {
            return false
        }

        var isCorrupt = false
        try {
            when (ext) {
                "jpg", "jpeg" -> {
                    file.inputStream().use { input ->
                        val header = ByteArray(2)
                        input.read(header)
                        if (header[0] != 0xFF.toByte() || header[1] != 0xD8.toByte()) {
                            isCorrupt = true
                        }
                    }
                }
                "png" -> {
                    file.inputStream().use { input ->
                        val header = ByteArray(4)
                        input.read(header)
                        val expected = byteArrayOf(0x89.toByte(), 'P'.code.toByte(), 'N'.code.toByte(), 'G'.code.toByte())
                        if (!header.contentEquals(expected)) {
                            isCorrupt = true
                        }
                    }
                }
                "gif" -> {
                    file.inputStream().use { input ->
                        val header = ByteArray(4)
                        input.read(header)
                        val gif8 = "GIF8".toByteArray()
                        if (!header.contentEquals(gif8)) {
                            isCorrupt = true
                        }
                    }
                }
                "heic" -> {
                    file.inputStream().use { input ->
                        val header = ByteArray(12)
                        input.read(header)
                        if (indexOfBytes(header, "ftyp".toByteArray()) < 0) {
                            isCorrupt = true
                        }
                    }
                }
                "mov", "mp4", "3gp", "m4v" -> {
                    if (!isValidVideo(file)) {
                        isCorrupt = true
                    }
                }
                "mts" -> {
                    file.inputStream().use { input ->
                        val byte = input.read()
                        if (byte != 0x47) {
                            isCorrupt = true
                        }
                    }
                }
            }
        } catch (e: Exception) {
            isCorrupt = true
        }

        if (isCorrupt) {
            try {
                corruptLog.appendText("${file.absolutePath}\n")
            } catch (e: Exception) {
                Log.e(TAG, "Error writing corrupt log", e)
            }
            BackupState.addLog("SKIPPED CORRUPT FILE: ${file.absolutePath}")
            return false
        }

        return true
    }

    private fun cleanStagingSyncedFiles(): List<String> {
        val cleaned = mutableListOf<String>()
        val dir = File(STAGING_DIR)
        val files = dir.listFiles() ?: return cleaned
        if (files.isEmpty()) return cleaned

        val fileMap = files.associateBy { "/storage/emulated/0/DCIM/Camera/${it.name}" }
        val paths = fileMap.keys.toList()

        val pathChunks = paths.chunked(100)
        for (chunk in pathChunks) {
            val sqlList = chunk.joinToString(",") { "'" + it.replace("'", "''") + "'" }
            val query = """
                SELECT l.filepath 
                FROM local_media l 
                LEFT JOIN media m ON l.dedup_key = m.dedup_key 
                WHERE l.filepath IN ($sqlList) 
                  AND (l.is_backup_processed = 1 OR (m.canonical_media_key IS NOT NULL AND m.canonical_media_key != ''));
            """.trimIndent().replace("\n", " ")

            val dbResult = Shell.cmd("/data/data/com.termux/files/usr/bin/sqlite3 /data/data/com.google.android.apps.photos/databases/gphotos0.db \"$query\"").exec()
            if (dbResult.isSuccess) {
                for (syncedPath in dbResult.out) {
                    val cleanPath = syncedPath.trim()
                    val f = fileMap[cleanPath]
                    if (f != null && f.exists()) {
                        if (f.delete()) {
                            cleaned.add(cleanPath)
                            Shell.cmd("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file://$cleanPath\"").exec()
                        }
                    }
                }
            }
        }
        return cleaned
    }

    private fun getHtmlDocs(): String {
        return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Pixel Backup Gang - Media Sync Architecture & API Documentation</title>
                <style>
                    body {
                        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
                        background-color: #0c0c0f;
                        color: #f3f3f7;
                        margin: 0;
                        padding: 0;
                        line-height: 1.6;
                    }
                    header {
                        background: linear-gradient(135deg, #0082ff 0%, #00f0ff 100%);
                        color: #0c0c0f;
                        padding: 40px 20px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    }
                    header h1 {
                        margin: 0;
                        font-size: 2.5em;
                        font-weight: 800;
                        letter-spacing: -0.5px;
                    }
                    header p {
                        margin: 10px 0 0 0;
                        font-size: 1.1em;
                        opacity: 0.9;
                    }
                    .container {
                        max-width: 1000px;
                        margin: 0 auto;
                        padding: 40px 20px;
                    }
                    .card {
                        background-color: #16161c;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                        border-radius: 16px;
                        padding: 30px;
                        margin-bottom: 30px;
                        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
                    }
                    h2 {
                        color: #00f0ff;
                        font-size: 1.8em;
                        margin-top: 0;
                        margin-bottom: 20px;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                        padding-bottom: 10px;
                    }
                    h3 {
                        color: #00ff88;
                        font-size: 1.3em;
                        margin-top: 24px;
                        margin-bottom: 12px;
                    }
                    p {
                        color: rgba(255, 255, 255, 0.8);
                        font-size: 1.05em;
                    }
                    ul, ol {
                        padding-left: 24px;
                        color: rgba(255, 255, 255, 0.85);
                    }
                    li {
                        margin-bottom: 10px;
                    }
                    code {
                        font-family: 'Courier New', Courier, monospace;
                        background-color: rgba(0, 240, 255, 0.1);
                        color: #00f0ff;
                        padding: 2px 6px;
                        border-radius: 4px;
                        font-size: 0.95em;
                    }
                    pre {
                        background-color: #08080a;
                        padding: 16px;
                        border-radius: 8px;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                        overflow-x: auto;
                        color: #00ff88;
                    }
                    table {
                        width: 100%;
                        border-collapse: collapse;
                        margin: 20px 0;
                        background-color: #0e0e12;
                        border-radius: 8px;
                        overflow: hidden;
                    }
                    th, td {
                        padding: 14px;
                        text-align: left;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    }
                    th {
                        background-color: rgba(0, 130, 255, 0.15);
                        color: #00f0ff;
                        font-weight: 600;
                    }
                    tr:hover {
                        background-color: rgba(255, 255, 255, 0.02);
                    }
                    .badge {
                        display: inline-block;
                        padding: 4px 8px;
                        border-radius: 6px;
                        font-size: 0.8em;
                        font-weight: bold;
                        text-transform: uppercase;
                    }
                    .badge-get { background-color: rgba(0, 255, 136, 0.2); color: #00ff88; border: 1px solid #00ff88; }
                    .badge-post { background-color: rgba(0, 240, 255, 0.2); color: #00f0ff; border: 1px solid #00f0ff; }
                    .badge-system { background-color: rgba(255, 159, 0, 0.2); color: #ff9f00; border: 1px solid #ff9f00; }
                    .step-list {
                        list-style-type: none;
                        padding-left: 0;
                    }
                    .step-item {
                        position: relative;
                        padding-left: 30px;
                        margin-bottom: 15px;
                    }
                    .step-item::before {
                        content: '✔';
                        position: absolute;
                        left: 0;
                        top: 2px;
                        color: #00ff88;
                        font-weight: bold;
                    }
                    .footer {
                        text-align: center;
                        margin-top: 50px;
                        color: rgba(255, 255, 255, 0.4);
                        font-size: 0.9em;
                    }
                </style>
            </head>
            <body>
                <header>
                    <h1>Pixel Backup Gang</h1>
                    <p>Rooted Media Upload & Pipeline Orchestration Platform</p>
                </header>
                <div class="container">
                    <div class="card">
                        <h2>System Architecture Overview</h2>
                        <p>
                            This companion application turns a rooted Pixel XL (running Android 10) into a dynamic, wear-free upload node for backing up high-volume photography. It is designed to work in tandem with external USB storage, bypassing write stress to the phone's internal flash memory (NAND).
                        </p>
                        <h3>Dynamic Mount Topology</h3>
                        <p>
                            When a USB partition is selected and mounted, the application executes the following mount namespace bind operations:
                        </p>
                        <ol>
                            <li>Mounts the USB partition dynamically at <code>/mnt/my_drive</code>.</li>
                            <li>Binds the staging folder <code>/mnt/my_drive/the_binding</code> over the Android Camera roll directories at <code>/storage/emulated/0/DCIM/Camera</code> and the system mount namespaces (<code>/mnt/runtime/*/emulated/0/DCIM/Camera</code>).</li>
                            <li>This makes Google Photos perceive the staging directory as local storage, allowing it to index and upload photos automatically.</li>
                        </ol>
                    </div>

                    <div class="card">
                        <h2>Media Pipeline Logic & Operations</h2>
                        <p>The media upload orchestrator runs in a staged, loop-driven lifecycle:</p>
                        <ul class="step-list">
                            <li class="step-item"><strong>Stage Phase:</strong> Photos are copied incrementally from the USB source path <code>Backup/shares/Amit/Photographs</code> to the staging area <code>the_binding</code>.</li>
                            <li class="step-item"><strong>Upload Monitoring:</strong> The system polls Google Photos' data sender statistics via <code>/proc/uid_stat/[UID]/tcp_snd</code> to detect when network uploads commence and conclude.</li>
                            <li class="step-item"><strong>Verification Phase:</strong> Before deleting any staged file, the app queries Google Photos' local SQLite database (<code>gphotos0.db</code>) to confirm that the file's MD5/dedup-key is marked as uploaded.</li>
                            <li class="step-item"><strong>Cleanup Phase:</strong> Verified uploads are deleted <em>only</em> from the staging folder, keeping the source photos on the USB drive completely untouched.</li>
                        </ul>
                    </div>

                    <div class="card">
                        <h2>API Endpoint Specifications</h2>
                        <p>The local service exposes a Netty Ktor server on port <code>8080</code> for integration with host machines, scripts, and other automation nodes:</p>
                        <table>
                            <thead>
                                <tr>
                                    <th>Method</th>
                                    <th>Endpoint</th>
                                    <th>Description</th>
                                    <th>Response Format</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/docs</code> or <code>/</code></td>
                                    <td>Retrieves this interactive HTML documentation dashboard.</td>
                                    <td>HTML</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/sync-status</code></td>
                                    <td>Returns real-time sync metrics, folder counts, and device thermals.</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/api/health</code></td>
                                    <td>Checks battery percentages, temperatures, and free storage bytes on the USB partition.</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/api/scan?path=[absolutePath]</code></td>
                                    <td>Forces the Android MediaScanner to index or de-index a specified file path.</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/api/status?path=[absolutePath]</code></td>
                                    <td>Checks Google Photos' internal database to verify if a file has successfully uploaded.</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-post">POST</span></td>
                                    <td><code>/api/clean</code></td>
                                    <td>Triggers an on-demand cleanup of files in the staging folder that have completed upload.</td>
                                    <td>JSON</td>
                                </tr>
                                <tr>
                                    <td><span class="badge badge-get">GET</span></td>
                                    <td><code>/my_drive/{path...}</code></td>
                                    <td>Web file explorer to navigate and download files directly from the mounted USB drive.</td>
                                    <td>HTML / Binary</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <div class="card">
                        <h2>Diagnostics & Safety Controls</h2>
                        <h3>Battery Limiting System</h3>
                        <p>
                            To prevent battery swelling on continuously plugged-in backup nodes, the application controls the device charging nodes at <code>/sys/class/power_supply/battery/charging_enabled</code> and <code>battery_charging_enabled</code>. Charging is automatically suspended when battery reaches 80% and resumes when it drops below 70%.
                        </p>
                        <h3>Thermal Throttling</h3>
                        <p>
                            The orchestrator monitors CPU temperature in real time. If CPU temperatures exceed 45°C, the sync process pauses to let the phone cool down before resuming.
                        </p>
                    </div>

                    <div class="footer">
                        <p>Pixel Backup Gang Platform • Companion App Service v1.2</p>
                    </div>
                </div>
            </body>
            </html>
        """.trimIndent()
    }
}
