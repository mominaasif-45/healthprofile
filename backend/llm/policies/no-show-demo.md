# The no-show estimate demo

*Fictional policy for the HealthProfile demo. Synthetic example content, not real clinic rules and not medical advice.*

The dashboard includes an educational no-show estimate. It was trained only on invented appointments made by a
script, not on any real person or clinic.

**What it can do:** given the facts of a fictional appointment (such as how far ahead it was booked, whether a
reminder was sent and earlier missed visits), it estimates the chance that the appointment would be missed.

**What it cannot do:** it cannot predict what a real person will do, it is not a diagnosis, and it must not be used
to treat anyone differently.

The demo uses a decision line of 22%. An estimate above the line suggests an extra reminder, not a certain no-show.
On the invented test appointments, this line caught 95 of 187 no-shows (50.8%), and 227 of its 322 flags (about 7
in 10) were appointments that were kept.
