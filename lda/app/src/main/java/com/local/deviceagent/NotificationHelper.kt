package com.local.deviceagent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat

object NotificationHelper {
    const val CHANNEL_ID = "local_agent_channel"
    const val SERVICE_NOTIFICATION_ID = 1

    fun createChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Local Agent Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Local Agent running in the background"
                setSound(null, null)
            }
            context.getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    fun buildNotification(context: Context, contentText: String, showResume: Boolean): Notification {
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT

        val stopIntent = PendingIntent.getService(
            context, 0,
            Intent(context, AgentService::class.java).setAction(AgentService.ACTION_STOP),
            flags
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle("Local Agent")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopIntent)

        if (showResume) {
            val resumeIntent = PendingIntent.getService(
                context, 1,
                Intent(context, AgentService::class.java).setAction(AgentService.ACTION_RESUME),
                flags
            )
            builder.addAction(android.R.drawable.ic_media_play, "Resume", resumeIntent)
        }

        return builder.build()
    }
}
