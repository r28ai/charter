/* The "Copy page" button's feedback.

   Mintlify says what the button is doing in words: the label runs "Copy page" →
   "Copying..." → "Copied" → "Copy page". Fetching the Markdown takes about a
   second, so "Copying..." is on screen just long enough to register as a flicker
   in the middle of the header — the control changes width, says something you
   did not ask about, and changes back.

   So the cycle loses its middle state and keeps its end: "Copying..." never
   reaches the screen — the label stays "Copy page" while the fetch runs — and
   the two seconds Mintlify holds "Copied" read as "Copied", under a check
   circle that cross-fades in over the copy sheets. Nothing reflows either way,
   because the button is sized by an invisible copy of "Copy page" that is left
   alone: the longest of the three labels holds the column no matter which one
   is showing.

   The button is React's, and React rewrites the label on every state change, so
   this runs from a MutationObserver and re-asserts itself after each rewrite.
   Observer callbacks land before paint, so the theme's text is replaced in the
   same frame it is written and never reaches the screen. The two glyphs live in
   an injected span; custom.css hides the theme's own icon and drives the
   cross-fade off the data-copy-state this file stamps on the button. */
(function () {
  "use strict";

  var COPY_PATH =
    "M8.25 2c.14 0 .25.11.25.25V3H10v-.75C10 1.28 9.22.5 8.25.5h-5.5C1.78.5 1 1.28 1 2.25v7.5c0 .97.78 1.75 1.75 1.75H4.5V10H2.75a.25.25 0 0 1-.25-.25v-7.5c0-.14.11-.25.25-.25zm5 4c.14 0 .25.11.25.25v7.5q-.02.23-.25.25h-5.5a.25.25 0 0 1-.25-.25v-7.5c0-.14.11-.25.25-.25zm0 9.5c.97 0 1.75-.78 1.75-1.75v-7.5c0-.97-.78-1.75-1.75-1.75h-5.5C6.78 4.5 6 5.28 6 6.25v7.5c0 .97.78 1.75 1.75 1.75z";

  var CHECK_PATH =
    "M14.5 8a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0m-4.47-1.47.53-.53L11 4.94l-.53.53L6.5 9.44l-.97-.97L5 7.94 3.94 9l.53.53 1.5 1.5c.3.3.77.3 1.06 0z";

  var LABEL = "Copy page";
  var SVG_NS = "http://www.w3.org/2000/svg";

  function glyph(path, className) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", className);

    var d = document.createElementNS(SVG_NS, "path");
    d.setAttribute("d", path);
    d.setAttribute("fill", "currentColor");
    d.setAttribute("fill-rule", "evenodd");
    d.setAttribute("clip-rule", "evenodd");
    svg.appendChild(d);

    return svg;
  }

  /* The glyph pair, injected once per button. It goes where the theme's icon
     sits — first inside the button's flex row — so the gap to the label is the
     theme's own. */
  function icons(button) {
    var existing = button.querySelector(".copy-page-icon");
    if (existing) return existing;

    var row = button.querySelector("div") || button;
    var slot = document.createElement("span");
    slot.className = "copy-page-icon";
    slot.appendChild(glyph(COPY_PATH, "copy-page-glyph"));
    slot.appendChild(glyph(CHECK_PATH, "copy-page-glyph copy-page-glyph-done"));
    row.insertBefore(slot, row.firstChild);

    return slot;
  }

  /* Mintlify renders the label twice inside a grid cell — an invisible copy
     that holds the column at the width of whatever state is current, and the
     visible one you read. The two are driven apart here: the invisible one is
     pinned to "Copy page" so the width is the same in every state, and the
     visible one shows "Copied" or "Copy page" and never "Copying...".

     The state is read off the theme's text before anything is rewritten, and
     "Copied" is the one label passed through unchanged — so on the next pass,
     what we wrote reads back as the same state, and the button falls out of it
     only when React itself writes "Copy page" again. */
  function relabel(button) {
    var spans = button.querySelectorAll("span");
    var leaves = [];
    var state = null;
    var i;

    for (i = 0; i < spans.length; i++) {
      if (spans[i].children.length) continue;
      leaves.push(spans[i]);
      if (spans[i].textContent.trim() === "Copied") state = "copied";
    }

    for (i = 0; i < leaves.length; i++) {
      var sizer = leaves[i].className.indexOf("invisible") !== -1;
      var text = sizer || state !== "copied" ? LABEL : "Copied";
      if (leaves[i].textContent.trim() !== text) leaves[i].textContent = text;
    }

    return state;
  }

  function render() {
    var button = document.querySelector(
      "#page-context-menu > button:first-of-type"
    );
    if (!button) return;

    icons(button);
    var state = relabel(button);

    if (state === "copied") {
      button.setAttribute("data-copy-state", "copied");
    } else {
      button.removeAttribute("data-copy-state");
    }
  }

  /* Our own writes — the injected span, the rewritten label, the state
     attribute — are mutations too, so the observer is paused around them. */
  var observer = new MutationObserver(function () {
    observer.disconnect();
    try {
      render();
    } finally {
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
  });

  function start() {
    render();
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
