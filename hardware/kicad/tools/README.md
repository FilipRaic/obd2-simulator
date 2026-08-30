# Router

`route_board.ps1` hands the board to **Freerouting**, an external autorouter, and
imports the result back. The jar is not in this repository: it is 58 MB of
third-party build output, which has no business in the history of a project this
size.

## Getting it

Download a release jar from the project and drop it here as
`freerouting.jar`:

    https://github.com/freerouting/freerouting/releases

The file the board was routed with is not a tagged release but a build of
**2026-05-13**, revision `20f1a72e`, built with Adoptium 25. Any release from
that period or later behaves the same for this board. The routing chain calls it
head-on, so only the file name matters:

    java -jar tools/freerouting.jar -de board.dsn -do result.ses -mp 300

A Java runtime of 21 or newer is required. `route_board.ps1` looks for `java` on
PATH and falls back to the JetBrains runtime bundled with CLion.

## Why the result is not deterministic

The router is randomised, so two runs on the same input give different track
counts and a different number of vias. `route_board.ps1` therefore runs it up to
ten times and keeps the best attempt, judged by unrouted nets first and via
count second. That is also why any number quoted about the layout - 738 segments,
60 vias - belongs to one specific run and is re-measured from the board file
rather than carried over from an earlier text.
