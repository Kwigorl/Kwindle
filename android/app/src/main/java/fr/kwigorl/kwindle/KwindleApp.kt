package fr.kwigorl.kwindle

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class KwindleApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        val canal = NotificationChannel(CANAL, "Travail en cours", NotificationManager.IMPORTANCE_LOW)
        canal.description = "Affichée pendant que Kwindle télécharge, répare ou envoie des livres"
        getSystemService(NotificationManager::class.java).createNotificationChannel(canal)
    }

    companion object {
        const val CANAL = "travail"
    }
}
