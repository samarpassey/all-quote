// Local stand-in for Google's reCAPTCHA v3 library script. Served from the
// same origin as the test fixture server (127.0.0.1) so the fixture never
// makes a real request to gstatic.com — a no-op is enough, since the point
// of recaptcha_v3_only.html is that a *loaded script* must never gate on
// its own, regardless of what the script does once it runs.
