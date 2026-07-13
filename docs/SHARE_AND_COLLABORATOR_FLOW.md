# Share link and collaborator flow

## How it is implemented (current design)

### 1. No “sub user” or guest user

- We do **not** create a random uid or “sub user” when someone opens the share link.
- We do **not** add a “sub user id” (or similar) to the session document.
- Collaborators are identified only by the **share token**: whoever has the link has the same token.

### 2. Share token on the session

- Each **board (session)** can have a **share_token** (random string, e.g. `secrets.token_urlsafe(32)`).
- Stored on the session document: `session.share_token = <token>`.
- Owner gets the share link via **Share** → backend creates/returns `share_token` and `share_url` (e.g. `https://app/?token=xxx`).

### 3. Join when someone opens the link

- Frontend sees `?token=xxx` in the URL.
- Calls **GET /api/join?token=xxx** (no auth).
- Backend finds the session where `share_token == token`, returns `{ session_id, problem_summary, share_token }`.
- Frontend then:
  - Saves `session_id` in `localStorage` (`current_session_id`).
  - Saves the token in `localStorage` under `board_tokens[session_id] = token`.
  - Sets React state `sessionId`, `isInitialized`, and calls `loadCurrentState(session_id)`.

### 4. How the API is validated today

- For **current-node**, **history**, **upload-artifact**, etc., the backend needs **session_id** and **who is allowed**:
  - **session_id**: from query (`session_id`) or JSON body.
  - **Who is allowed**:  
    - Owner: JWT user and `session.owner_id == user.id`, or  
    - Legacy: session has no `owner_id`, or  
    - Collaborator: request sends **X-Board-Token** (or `access_token`) and `session.share_token == that token`.

So we **validate by token**, not by a “sub user id”. The token is the proof that the client is allowed to access that board.

### 5. Why “session_id is required” was happening

- The backend required **session_id** in the request first; only then did it check **X-Board-Token** for access.
- If the frontend ever sent a request **without** `session_id` in the URL/body (e.g. race, or request sent before `session_id` was in state/localStorage), the backend returned 400 **before** looking at the token.

### 6. Change made (token can supply session_id)

- In **get_engine_from_request()** we now do:
  - If **session_id** is missing in query/body but the request has **X-Board-Token** (or `access_token`):
    - Find the session where `share_token == that token`.
    - Use that session’s `_id` as **session_id** for the rest of the request.
- So when a collaborator opens the share link and the frontend sends **only** the board token (e.g. in the header), the backend can still resolve **session_id** and load the board. The client no longer has to send `session_id` in every call for this to work.

---

## Your proposed design (sub user id per collaborator)

You described:

- When someone clicks the share link, create a **random uid** (e.g. “sub user id”).
- Store that uid on the session (e.g. a list of “sub user ids” or a `collaborator_ids` field).
- When that user calls the API, validate that **sub user id** and then load the state.

Comparison:

| Aspect | Current design | Your proposed design |
|--------|----------------|----------------------|
| Identity of collaborator | Same token for everyone with the link | One uid per person (e.g. per browser/device) |
| Stored on session | `share_token` (one token per board) | e.g. `collaborator_ids: [uid1, uid2, ...]` |
| Validation | Token in header/query; match `session.share_token` | Sub user id in header/query; check it’s in `session.collaborator_ids` (or similar) |
| When uid is created | Not used | When they first open the share link (e.g. in /api/join) |

Your design makes sense if you want to:

- Track **who** (which collaborator) did what, or
- Revoke access for one person without changing the link for everyone, or
- Have a stable “guest” identity per user/session.

The current design is simpler: one share token per board; anyone with the link uses that same token and we don’t store per-collaborator ids.

---

## Summary

- **Current flow:** Share token on session → join by token → frontend stores `session_id` + token → API needs `session_id` + (JWT owner or same token). We do **not** create or store a “sub user id”.
- **Fix applied:** If the request has no `session_id` but has the board token (X-Board-Token), the backend now **resolves session_id from the token** and continues. So the share link should work even when the client doesn’t send `session_id` in the URL/body.

If you want to move to the “sub user id” design, the next step would be: in **GET /api/join**, create a new uid, add it to the session (e.g. `collaborator_ids` or a small “guest users” structure), return that uid to the client, and then have the API accept that uid (e.g. in a header) and resolve **session_id** and access from it instead of (or in addition to) the share token.
