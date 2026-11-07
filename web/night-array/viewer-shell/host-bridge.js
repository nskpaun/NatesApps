/* Browser stand-in for the Android NightArrayHost JavascriptInterface.
   The parent page drives window.NA and receives the same events the app does.
   Messages are accepted only from this origin. Nothing here talks to hardware. */
(function () {
  var queue = [];

  function deliver(msg) {
    var na = window.NA;
    if (!na) return false;
    try {
      if (msg.op === 'setState') na.setState(msg.partial);
      else if (msg.op === 'camera') na.camera(msg.name);
      else if (msg.op === 'dock') na.dock(msg.step);
      else if (msg.op === 'frame') na.frame(msg.group);
    } catch (err) {
      console.error('[NightArray bridge]', err);
    }
    return true;
  }

  window.NightArrayHost = {
    post: function (json) {
      var evt;
      try {
        evt = JSON.parse(json);
      } catch (err) {
        evt = { type: 'error', message: String(json) };
      }
      try {
        parent.postMessage({ source: 'night-array-viewer', event: evt }, location.origin);
      } catch (err) {
        /* parent navigated away */
      }
    },
  };

  window.addEventListener('message', function (e) {
    if (e.origin !== location.origin) return;
    var msg = e.data;
    if (!msg || msg.source !== 'night-array-host') return;
    if (!deliver(msg)) queue.push(msg);
  });

  var tries = 0;
  var timer = setInterval(function () {
    tries += 1;
    if (window.NA) {
      queue.splice(0).forEach(deliver);
      clearInterval(timer);
    } else if (tries > 625) {
      clearInterval(timer);
    }
  }, 16);
})();
