/* The setup prompt's copy button.

   Three things this does that the obvious version does not.

   It binds nothing. Mintlify is a single-page app, so a listener attached to
   the button on load is gone the moment the reader navigates away and back.
   Rebinding on route change means knowing when routes change; delegating from
   the document means not caring. One listener, attached once, survives every
   navigation because it never referred to the button in the first place.

   It announces the result. The confirmation lives in its own element with
   role="status", so a screen reader is told the copy happened. A label that
   silently swaps its own text — the usual pattern — is invisible to anyone not
   watching that pixel. The status element is also separate from the button so
   nothing reflows: the button keeps its width whatever the status says.

   And it survives failing. `navigator.clipboard` rejects on an insecure origin,
   under a restrictive permissions policy, or when the document is not focused,
   and the usual `catch {}` leaves the reader with no text, no error and no way
   forward. Here the string is written into the page instead, which is the one
   outcome that still lets them get on with it. */
(function () {
  "use strict";

  /* The confirmation is a class on <html> rather than state on the button:
     Mintlify re-renders the page with React, which drops an attribute this
     file writes onto a node React owns almost immediately. The root element
     is not part of that tree. */
  var COPIED_CLASS = "charter-prompt-copied";
  var CLEAR_AFTER = 2400;
  var timer = null;

  function statusFor(button) {
    var root = button.closest(".agent-setup");
    return root ? root.querySelector(".agent-setup-status") : null;
  }

  function say(button, message) {
    var status = statusFor(button);
    if (!status) return;
    /* Reasserting identical textContent is not a DOM change, so a second copy
       would announce nothing. Clearing first makes the node change either way. */
    status.textContent = "";
    status.textContent = message;
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      status.textContent = "";
      document.documentElement.classList.remove(COPIED_CLASS);
    }, CLEAR_AFTER);
  }

  /* The prompt is declared once, on the button. Both the clipboard write and
     the fallback read it from there, so neither can drift from the other. */
  function reveal(button) {
    var doc = button.ownerDocument;
    var fallback = doc.querySelector(".agent-setup-fallback");
    var slot = fallback && fallback.querySelector(".agent-setup-fallback-text");
    if (!fallback || !slot) return;
    slot.textContent = button.getAttribute("data-prompt") || "";
    fallback.hidden = false;
  }

  function copy(button) {
    var prompt = button.getAttribute("data-prompt");
    if (!prompt) return;

    var clipboard = navigator.clipboard;
    if (!clipboard || !clipboard.writeText) {
      reveal(button);
      say(button, "Copy the prompt below");
      return;
    }

    clipboard.writeText(prompt).then(
      function () {
        document.documentElement.classList.add(COPIED_CLASS);
        say(button, "Copied prompt");
      },
      function () {
        reveal(button);
        say(button, "Copy the prompt below");
      }
    );
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".agent-setup-btn");
    if (button) copy(button);
  });
})();
