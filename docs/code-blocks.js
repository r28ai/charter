/* Punctuation, which Shiki does not tokenize.

   Shiki hands back one span per token class, and its "everything else" class is
   very wide: identifiers, attribute access, dots, commas, brackets, colons and
   arrows all arrive in a single color. That one class is 2,579 of the site's
   spans — more than every other class combined — which is why an unstyled block
   reads as a wall of near-white in dark mode and near-black in light.

   Splitting it in two recovers the distinction the grammar threw away. Each of
   those spans is walked here and its text cut into runs of word characters and
   runs of everything else; the second kind is wrapped in `.tok-punct`, which
   custom.css sets to the dimmed member of the pair. `client.chat.completions`
   comes out as three names at full strength with two recessive dots between
   them, which is how it reads in an editor.

   Only that one class is touched. A span Shiki did color — a string, a keyword,
   a number — is left whole, punctuation and all, because the color it already
   has is the right answer for the whole token.

   The wrapping adds elements but no characters: textContent is identical
   before and after, so the copy button still copies exactly what is on screen.

   Mintlify re-renders code blocks on client-side navigation, which drops the
   wrapping, so this runs from a MutationObserver and redoes it. Our own writes
   are mutations too, so the observer is paused around them — the same shape
   copy-button.js uses. Spans are marked once processed, and a span that has
   already been split has element children, which is the other reason a second
   pass skips it. */
(function () {
  "use strict";

  /* The one Shiki class this file claims: github-light-default's plain
     foreground paired with dark-plus's. Both halves are needed — three other
     token classes share #d4d4d4 — and the light half is written two ways,
     because React normalizes `color:#1f2328` into `color: rgb(31, 35, 40)`
     when it writes the style back through the CSSOM at hydration. Which of the
     two is in the DOM depends on whether this pass beat hydration. */
  var PLAIN = /#d4d4d4/;
  var PLAIN_LIGHT = /#1f2328|rgb\(31,\s*35,\s*40\)/;

  var PUNCTUATION = /[^\w\s]+/g;

  function split(span) {
    var text = span.firstChild;
    if (!text || text.nodeType !== 3 || span.children.length) return;

    var source = text.nodeValue;
    if (!/[^\w\s]/.test(source)) return;

    var pieces = document.createDocumentFragment();
    var at = 0;
    var match;

    PUNCTUATION.lastIndex = 0;
    while ((match = PUNCTUATION.exec(source)) !== null) {
      if (match.index > at) {
        pieces.appendChild(
          document.createTextNode(source.slice(at, match.index))
        );
      }

      var mark = document.createElement("span");
      mark.className = "tok-punct";
      mark.textContent = match[0];
      pieces.appendChild(mark);

      at = match.index + match[0].length;
    }

    if (at < source.length) {
      pieces.appendChild(document.createTextNode(source.slice(at)));
    }

    span.replaceChild(pieces, text);
  }


/* Second pass: the filename on a tabbed block's header bar.

   Every code block on the site draws a 40px bar with the language's mark, a
   label and the copy button. For a block with a title Mintlify builds that bar
   and fills it with the filename; for one without, custom.css draws it and the
   label falls back to the language ("Python").

   Inside a <CodeGroup> neither happens. The title goes to the tab rather than a
   header, so the card underneath has no header to fill, and the bar custom.css
   draws for it has only the language to show — which, on a page where every
   other block is named, is the one bar saying nothing.

   The tab cannot carry the name either: a tab title is the tab's whole label,
   and "Hand written" is what belongs there. So the names ride on a wrapper
   around the group — <div className="named-tabs" data-files="a.py|b.py"> — and
   are handed to the cards in order here, as data-filename, which custom.css
   prefers over the language name. A group with no wrapper keeps the language
   name, which is what an untitled block shows anywhere else.

   This lives in the same file as the punctuation pass because it needs the same
   thing: a MutationObserver that redoes the work after Mintlify re-renders a
   code block on client-side navigation. */

  function name_tabs() {
    var wrappers = document.querySelectorAll(
      "#content-area .named-tabs[data-files]"
    );

    for (var i = 0; i < wrappers.length; i++) {
      var names = wrappers[i].getAttribute("data-files").split("|");
      var cards = wrappers[i].querySelectorAll(
        '[role="tabpanel"] [data-component-part="code-block-root"]'
      );

      /* Panels render in the order the fences were written, which is the order
         the names are given in. Fewer cards than names means the group is still
         rendering; the observer brings us back when the rest arrive. */
      for (var j = 0; j < cards.length && j < names.length; j++) {
        var name = names[j].trim();
        if (!name || cards[j].getAttribute("data-filename") === name) continue;
        cards[j].setAttribute("data-filename", name);
      }
    }
  }

  function render() {
    name_tabs();

    var spans = document.querySelectorAll(
      "#content-area .shiki span[style]:not([data-punct])"
    );

    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];
      var style = span.getAttribute("style").toLowerCase();
      if (!PLAIN.test(style) || !PLAIN_LIGHT.test(style)) continue;
      span.setAttribute("data-punct", "");
      split(span);
    }
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
