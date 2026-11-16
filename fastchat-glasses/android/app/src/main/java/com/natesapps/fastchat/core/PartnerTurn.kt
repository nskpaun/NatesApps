package com.natesapps.fastchat.core

/** The partner only needs to know whether to speak, wait, or resume the conversation. */
enum class PartnerTurn { YOUR_TURN, WEARERS_TURN, RECONNECTING, PAUSED }

fun partnerTurn(phase: Phase, glassesReady: Boolean): PartnerTurn = when {
    phase == Phase.Off -> PartnerTurn.PAUSED
    !glassesReady -> PartnerTurn.RECONNECTING
    phase == Phase.Listening -> PartnerTurn.YOUR_TURN
    else -> PartnerTurn.WEARERS_TURN
}
