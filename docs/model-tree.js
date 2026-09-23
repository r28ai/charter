/* The copy button on a model tree.

   The tree is the one thing on an objects page a reader is likely to want out
   of the page rather than in it: pasted into a prompt, a note, an issue. Every
   code block on the site has a copy button and the tree, which is the same kind
   of object, had none.

   What it copies is what is on the screen, indentation and all, including the
   "above" note on a model whose subtree is drawn at its first appearance. A
   plain-text tree that quietly dropped that note would claim those nodes are
   leaves.

   The theme is a single-page app: it swaps the article on navigation without a
   reload, so the button is attached whenever the DOM settles, and `data-copy`
   on the box marks a tree already done. The observer is paused around our own
   writes so it does not see them. */
(function () {
  "use strict";

  var COPY_PATH =
    "M8.25 2c.14 0 .25.11.25.25V3H10v-.75C10 1.28 9.22.5 8.25.5h-5.5C1.78.5 1 1.28 1 2.25v7.5c0 .97.78 1.75 1.75 1.75H4.5V10H2.75a.25.25 0 0 1-.25-.25v-7.5c0-.14.11-.25.25-.25zm5 4c.14 0 .25.11.25.25v7.5q-.02.23-.25.25h-5.5a.25.25 0 0 1-.25-.25v-7.5c0-.14.11-.25.25-.25zm0 9.5c.97 0 1.75-.78 1.75-1.75v-7.5c0-.97-.78-1.75-1.75-1.75h-5.5C6.78 4.5 6 5.28 6 6.25v7.5c0 .97.78 1.75 1.75 1.75z";

  /* A drawn check, not a filled disc with a check cut out of it. At 14px the
     disc is what the eye resolves and the check inside it is lost, so the
     confirmation read as a dot. */
  var CHECK_PATH = "M2.75 8.5 6.25 12l7-8";

  var SVG_NS = "http://www.w3.org/2000/svg";

  function glyph(path, stroked) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("aria-hidden", "true");
    var d = document.createElementNS(SVG_NS, "path");
    d.setAttribute("d", path);
    if (stroked) {
      d.setAttribute("fill", "none");
      d.setAttribute("stroke", "currentColor");
      d.setAttribute("stroke-width", "1.75");
      d.setAttribute("stroke-linecap", "round");
      d.setAttribute("stroke-linejoin", "round");
    } else {
      d.setAttribute("fill", "currentColor");
    }
    svg.appendChild(d);
    return svg;
  }

  /* The tree as indented text. Depth is read off the nesting rather than
     counted while walking, so the text cannot drift from the connectors. */
  function textOf(scroll) {
    var lines = [];
    var nodes = scroll.querySelectorAll(".tree-node");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var depth = 0;
      var up = node.parentElement;
      while (up && up !== scroll) {
        if (up.classList.contains("tree-children")) depth++;
        up = up.parentElement;
      }
      var name = node.querySelector("a");
      if (!name) continue;
      var note = node.querySelector(".tree-note");
      var line = new Array(depth + 1).join("  ") + name.textContent;
      if (note) line += "  (" + note.textContent + ")";
      lines.push(line);
    }
    return lines.join("\n") + "\n";
  }

  /* The async clipboard needs a secure context and a permission that can be
     refused, and when it is refused the promise rejects and a button with no
     fallback has simply done nothing. `execCommand` is deprecated and works
     everywhere, which is the trade a copy button should take. */
  function legacyCopy(text) {
    var field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.top = "-1000px";
    field.style.opacity = "0";
    document.body.appendChild(field);
    var ok = false;
    try {
      field.select();
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(field);
    return ok;
  }

  function attach(tree) {
    if (tree.getAttribute("data-copy") !== null) return;
    var scroll = tree.querySelector(".model-tree-scroll");
    if (!scroll) return;
    tree.setAttribute("data-copy", "idle");

    var button = document.createElement("button");
    button.type = "button";
    button.className = "model-tree-copy";
    button.setAttribute("aria-label", "Copy model tree");
    button.appendChild(glyph(COPY_PATH));
    button.appendChild(glyph(CHECK_PATH, true));

    var timer = null;
    button.addEventListener("click", function () {
      var text = textOf(scroll);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {
          if (legacyCopy(text)) done();
        });
        return;
      }
      if (legacyCopy(text)) done();
    });

    function done() {
      tree.setAttribute("data-copy", "copied");
      button.setAttribute("aria-label", "Copied");
      clearTimeout(timer);
      timer = setTimeout(function () {
        tree.setAttribute("data-copy", "idle");
        button.setAttribute("aria-label", "Copy model tree");
      }, 2000);
    }

    tree.appendChild(button);
  }

  function render() {
    var trees = document.querySelectorAll(".model-tree");
    for (var i = 0; i < trees.length; i++) attach(trees[i]);
  }

  var observer = new MutationObserver(function () {
    observer.disconnect();
    try {
      render();
    } finally {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  });

  function start() {
    render();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
