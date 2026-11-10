# Privacy and data handling

*Fictional policy for the HealthProfile demo. Synthetic example content, not real clinic rules and not medical advice.*

The HealthProfile demo uses synthetic data only. Do not enter real names, real phone numbers or real health details.

* Members sign in with a password. The sign-in tokens are kept in HttpOnly browser cookies, which page scripts
  cannot read.
* Admin accounts are created by the system owner, never by public sign-up.
* Changes to a profile are recorded in an audit log. The log stores which fields changed, never the values.
* The FAQ assistant never receives profile data. Questions that contain email addresses, phone or ID numbers,
  dates written in digits (such as a date of birth) or the member's own name are refused before they reach the
  assistant.
* Questions and answers in the FAQ assistant are not stored.
* The assistant runs on a local model on the demo computer, so questions are not sent to an outside service.
