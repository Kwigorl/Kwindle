package fr.kwigorl.kwindle

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat

/**
 * Service « au premier plan » : garde Rekindle en vie (avec une notification)
 * pendant qu'il télécharge, répare ou envoie, même écran éteint.
 */
class TravailService : Service() {
    private var verrou: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val texte = intent?.getStringExtra("texte") ?: "Rekindle travaille…"
        ServiceCompat.startForeground(this, ID, notification(this, texte), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (verrou == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            verrou = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "rekindle:travail").apply {
                acquire(3 * 60 * 60 * 1000L)
            }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        verrou?.let { if (it.isHeld) it.release() }
        verrou = null
        super.onDestroy()
    }

    companion object {
        private const val ID = 1

        private fun notification(c: Context, texte: String): Notification {
            val ouvrir = PendingIntent.getActivity(
                c, 0,
                Intent(c, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            return NotificationCompat.Builder(c, RekindleApp.CANAL)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle("Rekindle")
                .setContentText(texte)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(ouvrir)
                .build()
        }

        fun demarrer(c: Context, texte: String) {
            try {
                ContextCompat.startForegroundService(c, Intent(c, TravailService::class.java).putExtra("texte", texte))
            } catch (e: Exception) {
                // sans service, le travail continue tant que l'appli est ouverte
            }
        }

        fun maj(c: Context, texte: String) {
            try {
                c.getSystemService(NotificationManager::class.java).notify(ID, notification(c, texte))
            } catch (e: Exception) {
                // notifications refusées : pas grave
            }
        }

        fun arreter(c: Context) {
            c.stopService(Intent(c, TravailService::class.java))
            try {
                c.getSystemService(NotificationManager::class.java).cancel(ID)
            } catch (e: Exception) {
                // rien à faire
            }
        }
    }
}
