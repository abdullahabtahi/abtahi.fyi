// Official HTMX 2.x Preload Extension (vendored locally for zero external dependency)
// Source: https://github.com/bigskysoftware/htmx-extensions/blob/main/src/preload/preload.js
htmx.defineExtension('preload', {
  onEvent: function(name, event) {
    if (name !== 'htmx:afterProcessNode') {
      return
    }

    var attr = function(node, property) {
      if (node == undefined) { return undefined }
      return node.getAttribute(property) || node.getAttribute('data-' + property) || attr(node.parentElement, property)
    }

    var load = function(node) {
      var done = function(html) {
        if (!node.preloadAlways) {
          node.preloadState = 'DONE'
        }
        if (attr(node, 'preload-images') == 'true') {
          document.createElement('div').innerHTML = html
        }
      }

      return function() {
        if (node.preloadState !== 'READY') {
          return
        }

        var hxGet = node.getAttribute('hx-get') || node.getAttribute('data-hx-get')
        if (hxGet) {
          htmx.ajax('GET', hxGet, {
            source: node,
            handler: function(elt, info) {
              done(info.xhr.responseText)
            }
          })
          return
        }

        if (node.getAttribute('href')) {
          var r = new XMLHttpRequest()
          r.open('GET', node.getAttribute('href'))
          r.onload = function() { done(r.responseText) }
          r.send()
        }
      }
    }

    var init = function(node) {
      if (node.getAttribute('href') + node.getAttribute('hx-get') + node.getAttribute('data-hx-get') == '') {
        return
      }
      if (node.preloadState !== undefined) {
        return
      }

      var on = attr(node, 'preload') || 'mousedown'
      const always = on.indexOf('always') !== -1
      if (always) {
        on = on.replace('always', '').trim()
      }

      node.addEventListener(on, function(evt) {
        if (node.preloadState === 'PAUSED') {
          node.preloadState = 'READY'
          if (always) {
            node.preloadAlways = true
          }
          setTimeout(load(node), 1)
        }
      })

      switch (on) {
        case 'mouseover':
        case 'touchstart':
          node.addEventListener('mouseout', function(evt) {
            if ((evt.target === node) && (node.preloadState === 'READY')) {
              node.preloadState = 'PAUSED'
            }
          })
          break
        default:
          break
      }

      node.preloadState = 'PAUSED'
    }

    event.target.querySelectorAll('[preload]').forEach(function(node) {
      init(node)
      node.querySelectorAll('a,[hx-get],[data-hx-get]').forEach(init)
    })
  }
})
