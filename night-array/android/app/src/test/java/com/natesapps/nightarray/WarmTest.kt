package com.natesapps.nightarray

import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WarmTest { @Test fun warm() { android.webkit.WebView(org.robolectric.RuntimeEnvironment.getApplication()).loadUrl("about:blank") } }
