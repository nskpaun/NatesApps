package com.natesapps.fastchat

import android.app.Application

class FastChatApp : Application() {
    lateinit var fastChat: FastChat
        private set

    override fun onCreate() {
        super.onCreate()
        fastChat = FastChat(this)
    }
}
