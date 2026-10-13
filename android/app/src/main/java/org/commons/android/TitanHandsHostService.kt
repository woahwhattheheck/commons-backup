package org.commons.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONArray
import java.net.Inet4Address
import java.net.NetworkInterface

class TitanHandsHostService : Service() {
    companion object {
        const val ACTION_STOP = "org.commons.android.STOP_HANDS"
        @Volatile var running: Boolean = false
            private set
        @Volatile var lastError: String = ""
            private set
        fun addresses(): List<String> {
            val found = ArrayList<String>()
            NetworkInterface.getNetworkInterfaces()?.toList()?.forEach { iface ->
                iface.inetAddresses.toList().forEach { addr ->
                    if (!addr.isLoopbackAddress && addr is Inet4Address) {
                        found += addr.hostAddress ?: addr.hostName
                    }
                }
            }
            return found
        }
    }

    private var server: HttpJsonServer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(7, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(7, notification())
        }
        if (server == null) {
            val engineHolder = arrayOfNulls<HandsEngine>(1)
            val server = HttpJsonServer(
                port = HANDS_PORT,
                handler = { request ->
                    val backend = HandsAccessibilityService.instance
                    if (backend == null) {
                        failure("ACCESSIBILITY_UNAVAILABLE", "enable the Commons accessibility setting on this phone")
                    } else {
                        val engine = engineHolder[0] ?: HandsEngine(backend).also { engineHolder[0] = it }
                        engine.handle(request)
                    }
                },
                health = {
                    val backend = HandsAccessibilityService.instance
                    val engine = if (backend != null) HandsEngine(backend) else null
                    val caps = engine?.capabilities() ?: failure(
                        "ACCESSIBILITY_UNAVAILABLE",
                        "enable the Commons accessibility setting on this phone",
                    )
                    caps.put("lan", JSONArray(addresses()))
                    caps.put("port", HANDS_PORT)
                    caps.put("host_running", true)
                    caps.put("pairing", "none")
                    caps.put("note", "POST observe/act/capture to the LAN URL after Start host")
                    caps
                },
                bindHost = "0.0.0.0",
            )
            try {
                server.start()
                this.server = server
                running = true
                lastError = ""
            } catch (exc: Exception) {
                lastError = exc.message ?: exc.javaClass.simpleName
                running = false
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        server?.stop()
        server = null
        super.onDestroy()
    }

    private fun notification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel("hands", getString(R.string.host_channel), NotificationManager.IMPORTANCE_LOW),
            )
        }
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, TitanHandsHostService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val ip = addresses().firstOrNull() ?: "0.0.0.0"
        val builder = if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(this, "hands")
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("Commons Titan Hands")
            .setContentText("LAN $ip:$HANDS_PORT — user-started, credential-free")
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentIntent(open)
            .addAction(0, "Stop", stop)
            .setOngoing(true)
            .build()
    }
}
