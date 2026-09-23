#!/usr/bin/env bash
# Regenerate the social preview cards. Run after any number in them changes.
#
# GitHub renders card.html at Settings -> Social preview; X and Slack use the same
# 1280x640 at 2:1. The tagline and wordmark must stay legible at ~420px wide,
# which is the size the card is actually seen at in a feed. The code block is
# texture at that size, not reading matter, and that is deliberate.
#
# banner.html is the X profile header at 1500x500. It carries no wordmark: the
# avatar and display name sit directly beneath it, so the banner spends its space
# on the mechanism instead. banner-3row.html is the same picture cut to three
# paired rows, which is what buys the type size the right pane needs at the ~600px
# it is actually seen at. Both render; pick one in the X settings. See the comment
# at the top of each file for the avatar safe area and what it may claim.
#
# banner-safe.html is the one measured against the real crop. The iOS app shows
# only x 125..1277, y 25..481 of the 1500x500, with the status bar over the top
# of that, so the other two lose their pane headers under the clock. Render it
# with class="debug" on <body> to see the crop and the safe box drawn.
set -euo pipefail
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT="../../docs/images"
"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --screenshot="$OUT/charter-social.png" --window-size=1280,640 "file://$PWD/card.html"
echo "wrote $OUT/charter-social.png"
"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=4000 \
  --screenshot="$OUT/charter-banner.png" --window-size=1500,500 "file://$PWD/banner.html"
echo "wrote $OUT/charter-banner.png"
"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=4000 \
  --screenshot="$OUT/charter-banner-3row.png" --window-size=1500,500 "file://$PWD/banner-3row.html"
echo "wrote $OUT/charter-banner-3row.png"
"$CHROME" --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --virtual-time-budget=4000 \
  --screenshot="$OUT/charter-banner-safe.png" --window-size=1500,500 "file://$PWD/banner-safe.html"
echo "wrote $OUT/charter-banner-safe.png"
