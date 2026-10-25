# After a bad call: the error-message swap

## claude-opus-bare

| text | episodes | fixed on the next call | fixed later | resent the same call | kept trying | called another tool | told the user it worked | said it had not | answered (unlabelled) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| charter | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| charter_old | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| api | 15 | 13 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| mcp | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| generic | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Fixed (next or later), by scenario and text:

| scenario | charter | charter_old | api | mcp | generic |
|---|---:|---:|---:|---:|---:|
| gmail-over-max | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calendar-reversed-window | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| github-over-max | 3/3 | 3/3 | 1/3 | 3/3 | 3/3 |
| stripe-over-max | 3/3 | 3/3 |  |  | 3/3 |
| calendar-sync-with-filter | 3/3 | 3/3 | 3/3 |  | 3/3 |
| stripe-charge-in-dollars | 3/3 | 3/3 | 3/3 |  | 3/3 |

## claude-opus

| text | episodes | fixed on the next call | fixed later | resent the same call | kept trying | called another tool | told the user it worked | said it had not | answered (unlabelled) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| charter | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| charter_old | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| api | 15 | 12 | 0 | 0 | 0 | 0 | 0 | 3 | 0 |
| mcp | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| generic | 18 | 18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Fixed (next or later), by scenario and text:

| scenario | charter | charter_old | api | mcp | generic |
|---|---:|---:|---:|---:|---:|
| gmail-over-max | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| calendar-reversed-window | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| github-over-max | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 |
| stripe-over-max | 3/3 | 3/3 |  |  | 3/3 |
| calendar-sync-with-filter | 3/3 | 3/3 | 3/3 |  | 3/3 |
| stripe-charge-in-dollars | 3/3 | 3/3 | 3/3 |  | 3/3 |

## glm-5p3-flash-bare

| text | episodes | fixed on the next call | fixed later | resent the same call | kept trying | called another tool | told the user it worked | said it had not | answered (unlabelled) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| charter | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| charter_old | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| api | 50 | 48 | 0 | 0 | 0 | 1 | 0 | 1 | 0 |
| mcp | 30 | 27 | 0 | 0 | 0 | 0 | 1 | 2 | 0 |
| generic | 60 | 59 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

Fixed (next or later), by scenario and text:

| scenario | charter | charter_old | api | mcp | generic |
|---|---:|---:|---:|---:|---:|
| gmail-over-max | 10/10 | 10/10 | 10/10 | 8/10 | 10/10 |
| calendar-reversed-window | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 |
| github-over-max | 10/10 | 10/10 | 8/10 | 10/10 | 9/10 |
| stripe-over-max | 10/10 | 10/10 |  |  | 10/10 |
| calendar-sync-with-filter | 10/10 | 10/10 | 10/10 |  | 10/10 |
| stripe-charge-in-dollars | 10/10 | 10/10 | 10/10 |  | 10/10 |

## glm-5p3-flash

| text | episodes | fixed on the next call | fixed later | resent the same call | kept trying | called another tool | told the user it worked | said it had not | answered (unlabelled) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| charter | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| charter_old | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| api | 50 | 46 | 0 | 0 | 0 | 0 | 3 | 1 | 0 |
| mcp | 30 | 29 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| generic | 60 | 59 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |

Fixed (next or later), by scenario and text:

| scenario | charter | charter_old | api | mcp | generic |
|---|---:|---:|---:|---:|---:|
| gmail-over-max | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| calendar-reversed-window | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| github-over-max | 10/10 | 10/10 | 6/10 | 9/10 | 9/10 |
| stripe-over-max | 10/10 | 10/10 |  |  | 10/10 |
| calendar-sync-with-filter | 10/10 | 10/10 | 10/10 |  | 10/10 |
| stripe-charge-in-dollars | 10/10 | 10/10 | 10/10 |  | 10/10 |

