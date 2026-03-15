Emergent Auth Testing Playbook

1. Login Button
const redirectUrl = window.location.origin + '/dashboard';
window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;

2. After Google Auth
User lands at {redirect_url}#session_id={session_id}

3. Backend Session Validation
GET https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data
Header: X-Session-ID: <session_id>
Response:
{"id":"string","email":"string","name":"string","picture":"string","session_token":"string"}

4. Backend session storage
Store session_token in database with 7-day expiry and set httpOnly cookie path=/ secure=True samesite=None.

5. Session verification
Use /api/auth/me with credentials included and validate server-side before showing protected routes.

Testing reminders:
- Detect session_id from URL hash before protected route logic runs
- Check cookies first, Authorization header second on backend
- Use timezone-aware expiry comparisons
- Exclude Mongo _id in all projections
