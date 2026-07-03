package com.backupgang.manager.util

import android.util.Log
import com.topjohnwu.superuser.Shell

object MountHelper {
    private const val TAG = "MountHelper"
    private const val HDD_PATH = "/mnt/my_drive"

    fun isDriveMounted(): Boolean {
        return isDriveMountedInNamespace(true) && isDriveMountedInNamespace(false)
    }

    private fun isDriveMountedInNamespace(inInitNamespace: Boolean): Boolean {
        val cmdPrefix = if (inInitNamespace) "nsenter -t 1 -m -- " else ""
        val result = Shell.cmd("${cmdPrefix}mount").exec()
        if (result.isSuccess) {
            for (line in result.out) {
                val parts = line.split("\\s+".toRegex())
                if (parts.size >= 3) {
                    val mountPoint = parts[2]
                    if (mountPoint == HDD_PATH && line.contains("rw")) {
                        return true
                    }
                }
            }
        }
        return false
    }

    fun getStorageInfo(): Pair<Long, Long> {
        // Returns Pair(usedBytes, totalBytes)
        val result = Shell.cmd("nsenter -t 1 -m -- df $HDD_PATH").exec()
        if (result.isSuccess && result.out.size >= 2) {
            val parts = result.out[1].split("\\s+".toRegex())
            if (parts.size >= 4) {
                val total = parts[1].toLongOrNull() ?: 0L
                val used = parts[2].toLongOrNull() ?: 0L
                return Pair(used * 1024, total * 1024)
            }
        }
        return Pair(0L, 0L)
    }

    private fun getAppUid(): Int {
        return android.os.Process.myUid()
    }

    private fun getAppUsername(): String {
        val uid = getAppUid()
        val userId = uid / 100000
        val appId = uid % 100000
        return if (appId >= 10000) {
            "u${userId}_a${appId - 10000}"
        } else {
            "u${userId}_system"
        }
    }

    fun detectUsbBlockDevice(): String {
        val detectCmd = "part=\$(blkid | grep -i \"BACKUPUSB\" | cut -d: -f1 | head -n 1)\n" +
            "if [ -n \"\$part\" ]; then\n" +
            "    echo \"\$part\"\n" +
            "    exit 0\n" +
            "fi\n" +
            "for dev in /sys/block/sd*; do\n" +
            "    if [ -L \"\$dev\" ] && readlink \"\$dev\" | grep -q \"usb\"; then\n" +
            "        name=\$(basename \"\$dev\")\n" +
            "        best_part=\"\"\n" +
            "        max_size=0\n" +
            "        for p_path in /dev/block/\${name}*; do\n" +
            "            if echo \"\$p_path\" | grep -qE \"[0-9]+\$\"; then\n" +
            "                line=\$(blkid \"\$p_path\" 2>/dev/null)\n" +
            "                if [ -n \"\$line\" ]; then\n" +
            "                    if echo \"\$line\" | grep -qE 'TYPE=\"ext4\"|TYPE=\"f2fs\"'; then\n" +
            "                        echo \"\$p_path\"\n" +
            "                        exit 0\n" +
            "                    fi\n" +
            "                    size=\$(cat /sys/class/block/\$(basename \"\$p_path\")/size 2>/dev/null || echo 0)\n" +
            "                    if [ \"\$size\" -gt \"\$max_size\" ]; then\n" +
            "                        max_size=\$size\n" +
            "                        best_part=\"\$p_path\"\n" +
            "                    fi\n" +
            "                fi\n" +
            "            fi\n" +
            "        done\n" +
            "        if [ -n \"\$best_part\" ]; then\n" +
            "            echo \"\$best_part\"\n" +
            "            exit 0\n" +
            "        fi\n" +
            "        raw_fs=\$(blkid /dev/block/\$name 2>/dev/null | grep -E \"/dev/block/\$name:\" | cut -d: -f1)\n" +
            "        if [ -n \"\$raw_fs\" ]; then\n" +
            "            echo \"\$raw_fs\"\n" +
            "            exit 0\n" +
            "        fi\n" +
            "    fi\n" +
            "done\n" +
            "echo \"\""
        val result = Shell.cmd(detectCmd).exec()
        return if (result.isSuccess && result.out.isNotEmpty()) {
            result.out[0].trim()
        } else {
            ""
        }
    }

    fun detectFilesystemType(blockDev: String): String {
        if (blockDev.isEmpty()) return "auto"
        val result = Shell.cmd("blkid $blockDev | grep -o 'TYPE=\"[^\"]*\"' | cut -d'\"' -f2").exec()
        return if (result.isSuccess && result.out.isNotEmpty()) {
            result.out[0].trim()
        } else {
            "auto"
        }
    }

    fun scanUsbDevices(): List<UsbDeviceOption> {
        val detectCmd = "for dev in /sys/block/sd*; do " +
            "if [ -L \"\$dev\" ] && readlink \"\$dev\" | grep -q \"usb\"; then " +
            "  name=\$(basename \"\$dev\"); " +
            "  blkid /dev/block/\${name}* 2>/dev/null | grep -E \"/dev/block/\${name}[0-9]+:\" | while read -r line; do " +
            "    path=\$(echo \"\$line\" | cut -d: -f1); " +
            "    label=\$(echo \"\$line\" | grep -o \" LABEL=\\\"[^\\\"]*\\\"\" | cut -d\\\" -f2); " +
            "    type=\$(echo \"\$line\" | grep -o \" TYPE=\\\"[^\\\"]*\\\"\" | cut -d\\\" -f2); " +
            "    [ -z \"\$label\" ] && label=\"Unnamed\"; " +
            "    [ -z \"\$type\" ] && type=\"unknown\"; " +
            "    size_sectors=\$(cat /sys/class/block/\$(basename \"\$path\")/size 2>/dev/null || echo 0); " +
            "    echo \"\$path|\$label|\$type|\$size_sectors\"; " +
            "  done; " +
            "  blkid /dev/block/\${name} 2>/dev/null | grep -E \"/dev/block/\${name}:\" | while read -r line; do " +
            "    path=\$(echo \"\$line\" | cut -d: -f1); " +
            "    label=\$(echo \"\$line\" | grep -o \" LABEL=\\\"[^\\\"]*\\\"\" | cut -d\\\" -f2); " +
            "    type=\$(echo \"\$line\" | grep -o \" TYPE=\\\"[^\\\"]*\\\"\" | cut -d\\\" -f2); " +
            "    [ -z \"\$label\" ] && label=\"Unnamed\"; " +
            "    [ -z \"\$type\" ] && type=\"unknown\"; " +
            "    size_sectors=\$(cat /sys/class/block/\$(basename \"\$path\")/size 2>/dev/null || echo 0); " +
            "    echo \"\$path|\$label|\$type|\$size_sectors\"; " +
            "  done; " +
            "fi; " +
            "done"
        val result = Shell.cmd(detectCmd).exec()
        val list = mutableListOf<UsbDeviceOption>()
        if (result.isSuccess) {
            for (line in result.out) {
                val parts = line.split("|")
                if (parts.size >= 4) {
                    val sectors = parts[3].toLongOrNull() ?: 0L
                    val sizeBytes = sectors * 512L
                    list.add(UsbDeviceOption(parts[0], parts[1], parts[2], sizeBytes))
                } else if (parts.size >= 3) {
                    list.add(UsbDeviceOption(parts[0], parts[1], parts[2], 0L))
                }
            }
        }
        return list
    }

    fun mountDrive(): Boolean {
        Log.d(TAG, "Attempting to mount external drive...")
        val selectedPath = BackupState.selectedDevicePath.value
        val blockDev = if (selectedPath.isNotEmpty() && scanUsbDevices().any { it.path == selectedPath }) {
            selectedPath
        } else {
            detectUsbBlockDevice()
        }
        if (blockDev.isEmpty()) {
            Log.e(TAG, "No external USB block device detected!")
            return false
        }
        val fstype = detectFilesystemType(blockDev)
        val uid = getAppUid()
        val appUsername = getAppUsername()

        Log.d(TAG, "Detected USB: $blockDev, Filesystem: $fstype, App UID: $uid ($appUsername)")

        val commands = mutableListOf<String>()
        val mountPointsToUmount = listOf(
            "/mnt/my_drive/the_binding",
            "/storage/emulated/0/DCIM/Camera",
            "/mnt/runtime/write/emulated/0/DCIM/Camera",
            "/mnt/runtime/default/emulated/0/DCIM/Camera",
            "/mnt/runtime/read/emulated/0/DCIM/Camera",
            "/mnt/runtime/full/emulated/0/DCIM/Camera",
            "/mnt/my_drive"
        )
        for (point in mountPointsToUmount) {
            commands.add("nsenter -t 1 -m -- umount -l $point 2>/dev/null || true")
            commands.add("umount -l $point 2>/dev/null || true")
        }

        commands.add("nsenter -t 1 -m -- mkdir -p /mnt/my_drive")
        commands.add("mkdir -p /mnt/my_drive")

        if (fstype == "ext4" || fstype == "f2fs") {
            commands.add("nsenter -t 1 -m -- mount -t $fstype -o nosuid,nodev,noexec,noatime,rw $blockDev /mnt/my_drive")
            commands.add("mount -t $fstype -o nosuid,nodev,noexec,noatime,rw $blockDev /mnt/my_drive")

            commands.add("nsenter -t 1 -m -- chown -R $appUsername:$appUsername /mnt/my_drive")
            commands.add("chown -R $appUsername:$appUsername /mnt/my_drive")

            commands.add("nsenter -t 1 -m -- chmod -R 777 /mnt/my_drive")
            commands.add("chmod -R 777 /mnt/my_drive")
        } else {
            // exfat, vfat, ntfs, etc. or auto
            val mountCmd = "mount -t $fstype -o nosuid,nodev,noexec,noatime,rw,uid=$uid,gid=$uid,fmask=0000,dmask=0000 $blockDev /mnt/my_drive || mount -o nosuid,nodev,noexec,noatime,rw $blockDev /mnt/my_drive"
            commands.add("nsenter -t 1 -m -- $mountCmd")
            commands.add(mountCmd)

            commands.add("nsenter -t 1 -m -- chown -R $appUsername:$appUsername /mnt/my_drive 2>/dev/null || true")
            commands.add("chown -R $appUsername:$appUsername /mnt/my_drive 2>/dev/null || true")

            commands.add("nsenter -t 1 -m -- chmod -R 777 /mnt/my_drive 2>/dev/null || true")
            commands.add("chmod -R 777 /mnt/my_drive 2>/dev/null || true")
        }

        commands.add("nsenter -t 1 -m -- mkdir -p /mnt/my_drive/the_binding")
        commands.add("mkdir -p /mnt/my_drive/the_binding")

        commands.add("nsenter -t 1 -m -- chown -R $appUsername:$appUsername /mnt/my_drive/the_binding 2>/dev/null || true")
        commands.add("chown -R $appUsername:$appUsername /mnt/my_drive/the_binding 2>/dev/null || true")

        commands.add("nsenter -t 1 -m -- chmod -R 777 /mnt/my_drive/the_binding 2>/dev/null || true")
        commands.add("chmod -R 777 /mnt/my_drive/the_binding 2>/dev/null || true")
        
        // Auto-create and prepare the Photographs sync directory
        commands.add("nsenter -t 1 -m -- mkdir -p /mnt/my_drive/Backup/shares/Amit/Photographs")
        commands.add("mkdir -p /mnt/my_drive/Backup/shares/Amit/Photographs")

        commands.add("nsenter -t 1 -m -- chown -R $appUsername:$appUsername /mnt/my_drive/Backup/shares/Amit/Photographs 2>/dev/null || true")
        commands.add("chown -R $appUsername:$appUsername /mnt/my_drive/Backup/shares/Amit/Photographs 2>/dev/null || true")

        commands.add("nsenter -t 1 -m -- chmod -R 777 /mnt/my_drive/Backup/shares/Amit/Photographs 2>/dev/null || true")
        commands.add("chmod -R 777 /mnt/my_drive/Backup/shares/Amit/Photographs 2>/dev/null || true")

        // Bridges
        commands.add("nsenter -t 1 -m -- mkdir -p /storage/emulated/0/DCIM/Camera")
        commands.add("mkdir -p /storage/emulated/0/DCIM/Camera")

        val binds = listOf(
            "/storage/emulated/0/DCIM/Camera",
            "/mnt/runtime/write/emulated/0/DCIM/Camera",
            "/mnt/runtime/default/emulated/0/DCIM/Camera",
            "/mnt/runtime/read/emulated/0/DCIM/Camera",
            "/mnt/runtime/full/emulated/0/DCIM/Camera"
        )
        for (bind in binds) {
            val bindCmd = "mount -t sdcardfs -o nosuid,nodev,noexec,noatime,gid=9997 /mnt/my_drive/the_binding $bind"
            commands.add("nsenter -t 1 -m -- $bindCmd")
            commands.add(bindCmd)
        }
        commands.add("nsenter -t 1 -m -- setenforce 0")
        commands.add("setenforce 0")

        val result = Shell.cmd(*commands.toTypedArray()).exec()
        return result.isSuccess && isDriveMounted()
    }

    fun unmountDrive(): Boolean {
        Log.d(TAG, "Attempting to unmount external drive...")
        // Force stop Google Photos to release any file locks
        Shell.cmd("am force-stop com.google.android.apps.photos 2>/dev/null || true").exec()
        
        val unmountCmd = "for i in {1..10}; do\n" +
            "    # Try unmounting from init namespace\n" +
            "    if nsenter -t 1 -m -- mount | grep -q \"my_drive\"; then\n" +
            "        for target in \$(nsenter -t 1 -m -- mount | grep \"my_drive\" | awk '{print \$3}' | sort -u); do\n" +
            "            nsenter -t 1 -m -- umount -l \"\$target\" 2>/dev/null || true\n" +
            "        done\n" +
            "    fi\n" +
            "    # Try unmounting from local namespace\n" +
            "    if mount | grep -q \"my_drive\"; then\n" +
            "        for target in \$(mount | grep \"my_drive\" | awk '{print \$3}' | sort -u); do\n" +
            "            umount -l \"\$target\" 2>/dev/null || true\n" +
            "        done\n" +
            "    fi\n" +
            "    # Check if cleared in both\n" +
            "    if ! nsenter -t 1 -m -- mount | grep -q \"my_drive\" && ! mount | grep -q \"my_drive\"; then\n" +
            "        break\n" +
            "    fi\n" +
            "    sleep 0.1\n" +
            "done"
            
        Shell.cmd(unmountCmd).exec()
        return !isDriveMounted()
    }

    fun formatPartition(blockDev: String, fstype: String): Boolean {
        if (blockDev.isEmpty()) return false
        Log.d(TAG, "Formatting partition $blockDev to $fstype")
        
        // 1. Force stop Google Photos & unmount
        Shell.cmd("am force-stop com.google.android.apps.photos 2>/dev/null || true").exec()
        unmountDrive()
        
        // 2. Perform format
        val cmd = when (fstype.lowercase()) {
            "ext4" -> "mkfs.ext4 -L \"BACKUPUSB\" -F $blockDev"
            "fat32" -> "newfs_msdos -F 32 -L \"BACKUPUSB\" $blockDev"
            else -> return false
        }
        
        val formatResult = Shell.cmd(cmd).exec()
        if (!formatResult.isSuccess) {
            Log.e(TAG, "Format command failed: ${formatResult.err.joinToString("\n")}")
            return false
        }
        
        // 3. Mount and prepare
        return mountDrive()
    }
}
