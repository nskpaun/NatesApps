# The viewer calls NightArrayHost.post(String) from JavaScript.
-keepclassmembers class * { @android.webkit.JavascriptInterface <methods>; }
-keepattributes JavascriptInterface
