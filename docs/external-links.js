/* External links open in a new tab.

   The setup guides are read beside a console: open Google Cloud, click
   through four screens, come back for step five. A link that replaces the
   guide with the console makes the reader find their place again after every
   step, and the back button returns them to the top of a long page.

   So any link to another host gets a new tab, decided at click time rather
   than stamped on at load. Mintlify renders pages client-side and swaps them
   without a reload, so a pass over the DOM on load would miss every page after
   the first; one delegated listener sees every click on every page. It runs in
   the capture phase, before the browser follows the link, which is the only
   point at which setting `target` still changes where it opens.

   A modified click (cmd, ctrl, shift, middle button) is left alone: the reader
   has already said where they want it. */
(function () {
  "use strict";

  document.addEventListener(
    "click",
    function (event) {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      var link = event.target.closest && event.target.closest("a[href]");
      if (!link || link.target) return;

      var url;
      try {
        url = new URL(link.href, window.location.href);
      } catch (error) {
        return;
      }
      if (url.protocol !== "http:" && url.protocol !== "https:") return;
      if (url.host === window.location.host) return;

      link.target = "_blank";
      link.rel = "noopener noreferrer";
    },
    true
  );
})();
