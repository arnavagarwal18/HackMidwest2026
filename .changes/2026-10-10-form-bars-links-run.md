---
urgency: ride-along
component: backend
audience: internal
---
Adds form.run, which tracks a video take, puts each posture flag on score bars, links it to the note diagnosis for those bars and saves the result as take.form, plus form.get_flags and form.get_flag; its failures are recorded on the take and never raised.
