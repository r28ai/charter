/* Breadcrumbs in the page header, on the Packs tab only.

   Mintlify's eyebrow — the line above the H1 — names only the immediate parent
   group, so /packs/gmail/... reads "Gmail" and tells you nothing about where
   Gmail sits. There is no docs.json setting for this, so the trail is built here
   and written into the eyebrow the theme already renders.

   Everywhere else the eyebrow is suppressed. The Documentation and Reference
   tabs are shallow enough that the sidebar already shows you where you are, and
   a trail that only ever restates the group above the title is noise on every
   page. Packs is the one tab deep enough to need an address: a pack page sits
   under a pack group, under an auth-style group, under the tab.

   The sidebar is the source of truth: it carries the same tree docs.json
   declares, and it marks it up well enough to walk. Each page is an
   `li[id="/its/path"]`, each nested group an `li[data-title]`, and each
   top-level group a `div.sidebar-group-header`. Reading the trail off the DOM
   rather than re-declaring it in this file means the breadcrumb cannot drift
   from the navigation. */
(function () {
  "use strict";

  /* Pages that sit directly under a tab have no group above them, so the tab
     stands in as their one ancestor. On a tab's own landing page — /packs
     titled "Packs", /reference titled "Reference" — that ancestor is the page
     itself, and "Packs / Packs" is worse than no trail at all; those are
     deduplicated below and left with nothing, which is honest: the page is the
     root of its section, and a root has no path above it. */
  function activeTab() {
    var tab = document.querySelector(
      'header .nav-tabs a[class*="text-primary"], header .nav-tabs [aria-selected="true"]'
    );
    return tab ? tab.textContent.trim() : null;
  }

  function trailFor(path) {
    var nav = document.getElementById("navigation-items");
    if (!nav) return null;

    var page = nav.querySelector('li[id="' + path.replace(/"/g, '\\"') + '"]');
    if (!page) return null;

    var crumbs = [];
    var node = page.parentElement;
    while (node && node !== nav) {
      if (node.tagName === "LI" && node.hasAttribute("data-title")) {
        crumbs.unshift(node.getAttribute("data-title"));
      }
      var header = node.querySelector(":scope > .sidebar-group-header");
      if (header) crumbs.unshift(header.textContent.trim());
      node = node.parentElement;
    }

    if (!crumbs.length) {
      var tab = activeTab();
      if (tab) crumbs.push(tab);
    }

    var title = document.getElementById("page-title");
    var name = title
      ? title.textContent.trim()
      : page.getAttribute("data-title") || "";

    crumbs = crumbs.filter(Boolean).filter(function (crumb) {
      return crumb !== name;
    });
    crumbs.push(name);

    return crumbs;
  }

  /* The Packs tab, under any base path. `mint dev` serves the site at `/` and
     docs.r28.ai serves it under `/charter`, so this page is `/packs/gmail` in
     one and `/charter/packs/gmail` in the other; a check anchored to the start
     of the path passes locally and fails in production, taking the trail with
     it. Matching `packs` as a whole segment holds in both, and the sidebar
     lookup in trailFor needs no such care — it keys `li[id]` off the same
     `location.pathname` the theme wrote those ids from, prefix and all. */
  function isPacksPage(path) {
    return /(^|\/)packs(\/|$)/.test(path);
  }

  function render() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";

    var existing = document.querySelector("#header .eyebrow");

    /* Off the Packs tab there is no trail. The class is what custom.css shows an
       eyebrow by, so dropping it leaves the theme's own group name hidden rather
       than needing to be blanked and re-blanked on every re-render. */
    if (!isPacksPage(path)) {
      if (existing) existing.classList.remove("breadcrumb-trail");
      return;
    }

    if (existing && existing.getAttribute("data-breadcrumb-path") === path) {
      return;
    }

    /* Only ever fills the eyebrow the theme rendered; never makes one. An
       eyebrow inserted here would arrive at hydration, and the line plus the
       24px custom.css hangs under it would push the title and the whole page
       down 44px a second after it had painted — which is the one thing the
       reserved box over there exists to prevent, and it cannot reserve space
       for an element that is not in the served HTML. Mintlify renders the
       eyebrow on every page that sits inside a group, which on this tab is
       every page with a trail worth drawing; a page directly under the tab gets
       no eyebrow and no trail, and its title starts at the top of the header,
       where a root belongs. */
    var crumbs = trailFor(path);
    if (!crumbs || crumbs.length < 2) return;

    var eyebrow = existing;
    if (!eyebrow) return;

    eyebrow.textContent = "";
    crumbs.forEach(function (crumb, i) {
      if (i > 0) {
        var sep = document.createElement("span");
        sep.className = "breadcrumb-separator";
        sep.textContent = "/";
        eyebrow.appendChild(sep);
      }
      var span = document.createElement("span");
      span.className =
        i === crumbs.length - 1 ? "breadcrumb breadcrumb-current" : "breadcrumb";
      span.textContent = crumb;
      eyebrow.appendChild(span);
    });
    eyebrow.classList.add("breadcrumb-trail");
    eyebrow.setAttribute("data-breadcrumb-path", path);
  }

  /* The theme is a single-page app: it swaps the header on navigation without a
     reload, and it re-renders the eyebrow from its own state afterwards. So the
     trail is rebuilt whenever the DOM settles, and the path stamped on the
     eyebrow both marks our work as done and detects the theme overwriting it.
     The observer is paused around our own writes so it does not see them. */
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
