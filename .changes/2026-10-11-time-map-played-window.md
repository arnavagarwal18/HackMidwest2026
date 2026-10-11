---
urgency: ship-soon
component: backend/diagnosis
audience: people
---
Note checking now follows a take that speeds up or slows down, so a sped-up phrase is reported as rushing on exactly its bars and no longer causes false missed notes, and bars you did not play at the start or end are left out instead of counted as missed (with a "You played bars a-b of c-d" note). Rushing and dragging are now measured against your own tempo, not the goal tempo.

Deviation from the LLD-3 r4 time map (lead-approved): an anchor is also dropped when its played onset is more than 0.5 beat from the line fitted through its neighbouring anchors (up to 3 each side, two rounds), so a repeated note paired with the wrong copy cannot bend the map.
