---
urgency: ship-soon
component: backend
audience: people
---
Trumpet video takes are now checked for embouchure with MediaPipe's Face Landmarker, only while a note is sounding: puffed cheeks and a smile embouchure (mouth corners pulled back) are flagged like the posture problems. If the face can't be seen, or the face model can't run, those two checks are skipped and the posture checks carry on.
