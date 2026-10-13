package com.local.deviceagent

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import java.io.BufferedWriter
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException
import java.util.concurrent.Semaphore
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Manually started, credential-free LAN adapter for the existing TitanHandsReceiver.
 * It adds only TCP/JSONL transport; handset perception and action remain in the LDA bridge.
 */
class TitanHandsLanService : Service() {
    companion object {
        const val ACTION_START = "com.local.deviceagent.TITAN_HANDS_LAN_START"
        const val ACTION_STOP = "com.local.deviceagent.TITAN_HANDS_LAN_STOP"
        private const val CHANNEL_ID = "commons_titan_hands_lan"
        private const val NOTIFICATION_ID = 42171
        private const val RESULT_TIMEOUT_SECONDS = 50L

        @Volatile var isRunning: Boolean = false
            private set
    }

    private val open = AtomicBoolean(false)
    private val listener = Executors.newSingleThreadExecutor()
    private val clients = ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        ArrayBlockingQueue(16),
        ThreadPoolExecutor.AbortPolicy()
    )
    private val bridgeSingleFlight = Semaphore(1, true)
    @Volatile private var server: ServerSocket? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        enterForeground()
        startListener()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        open.set(false)
        isRunning = false
        try { server?.close() } catch (_: Throwable) {}
        server = null
        listener.shutdownNow()
        clients.shutdownNow()
        super.onDestroy()
    }

    private fun enterForeground() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Commons LAN bridge", NotificationManager.IMPORTANCE_LOW)
        )
        val stopIntent = Intent(this, TitanHandsLanService::class.java).setAction(ACTION_STOP)
        val stopPending = PendingIntent.getService(
            this,
            NOTIFICATION_ID,
            stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("Commons Titan Hands LAN")
            .setContentText("Listening on 0.0.0.0:${TitanHandsLanProtocol.DEFAULT_PORT}")
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPending)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun startListener() {
        if (!open.compareAndSet(false, true)) return
        listener.execute {
            try {
                val listening = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress("0.0.0.0", TitanHandsLanProtocol.DEFAULT_PORT), 16)
                }
                server = listening
                isRunning = true
                while (open.get()) {
                    val socket = try { listening.accept() } catch (_: Throwable) { break }
                    try {
                        clients.execute { handle(socket) }
                    } catch (_: RejectedExecutionException) {
                        // A saturated/reset peer must not escape into the listener's outer catch
                        // and stop the whole service. BUSY is best-effort; closing is the invariant.
                        try {
                            socket.use {
                                writeLine(
                                    it,
                                    TitanHandsLanProtocol.failure(
                                        "BRIDGE_BUSY",
                                        "LAN transport is at its bounded connection capacity"
                                    )
                                )
                            }
                        } catch (_: Throwable) {}
                    }
                }
            } catch (_: Throwable) {
                stopSelf()
            } finally {
                isRunning = false
                open.set(false)
                try { server?.close() } catch (_: Throwable) {}
                server = null
            }
        }
    }

    private fun handle(socket: Socket) {
        socket.use { client ->
            client.soTimeout = 15_000
            val response = try {
                val line = TitanHandsLanProtocol.readRequest(client.getInputStream())
                    ?: return@use writeLine(client, TitanHandsLanProtocol.failure("EMPTY_REQUEST", "send one JSON line"))
                val command = TitanHandsLanProtocol.parseRequest(line)
                bridge(command)
            } catch (t: Throwable) {
                TitanHandsLanProtocol.failure(
                    "INVALID_REQUEST",
                    t.message ?: t.javaClass.simpleName
                )
            }
            writeLine(client, response)
        }
    }

    private fun bridge(command: TitanHandsLanCommand): String {
        bridgeSingleFlight.acquire()
        try {
            return bridgeSingleFlight(command)
        } finally {
            bridgeSingleFlight.release()
        }
    }

    /** LDA observations/actions share currentNodes and busy state, so bridge calls never overlap. */
    private fun bridgeSingleFlight(command: TitanHandsLanCommand): String {
        val done = CountDownLatch(1)
        var encoded: String? = null
        var resultCode = Activity.RESULT_CANCELED
        val finalReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                encoded = resultData
                resultCode = this.resultCode
                done.countDown()
            }
        }
        val request = Intent(this, TitanHandsReceiver::class.java)
            .setAction(TitanHandsReceiver.ACTION)
            .putExtra("op", command.op)
        command.actionBase64?.let { request.putExtra("action_b64", it) }
        sendOrderedBroadcast(
            request,
            null,
            finalReceiver,
            Handler(Looper.getMainLooper()),
            Activity.RESULT_CANCELED,
            null,
            null
        )
        if (!done.await(RESULT_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
            return TitanHandsLanProtocol.failure("BRIDGE_TIMEOUT", "LDA bridge did not finish", command.requestId)
        }
        val payload = encoded
            ?: return TitanHandsLanProtocol.failure(
                "EMPTY_BRIDGE_RESULT",
                "LDA bridge returned no payload (result=$resultCode)",
                command.requestId
            )
        return try {
            TitanHandsLanProtocol.decorateReceiverResponse(
                TitanHandsLanProtocol.decodeReceiverResult(payload),
                command.requestId
            )
        } catch (t: Throwable) {
            TitanHandsLanProtocol.failure(
                "INVALID_BRIDGE_RESULT",
                t.message ?: t.javaClass.simpleName,
                command.requestId
            )
        }
    }

    private fun writeLine(socket: Socket, value: String) {
        BufferedWriter(OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8)).use {
            it.write(value)
            it.newLine()
            it.flush()
        }
    }
}
