#Expense Tracker 
## Techniques used

### 1. Firebase

- Create a Firebase project (if you don't have one): https://console.firebase.google.com
- Enable **Authentication** → Email/Password (or whichever sign-in method you want) in the Firebase console. This is what your future frontend/mobile app will use to actually log users in.
- Go to Project Settings → Service Accounts → **Generate new private key**. This downloads a JSON file.
- Save it as `firebase-service-account.json` in the project root (same folder as this README). **Never commit this file** — it's already git-ignored below.

### 2. PostgreSQL

- Create a local (or hosted) Postgres database, e.g.:
  ```
  createdb expense_tracker
  ```

### 3. Environment variables

```bash
cp .env.example .env
```
Edit `.env`:
- `DATABASE_URL` → your Postgres connection string
- `FIREBASE_CREDENTIALS_PATH` → path to the service account JSON (default `./firebase-service-account.json` is fine if you followed step 1)

### 4. Install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run the first migration

```bash
alembic revision --autogenerate -m "create users table"
alembic upgrade head
```

### 6. Run the server

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## How auth actually works here (important — read this)

Firebase handles **login/signup on the client** (web or mobile app), not this backend.
The flow is:

1. Client app uses the Firebase client SDK to sign a user up / log them in. Firebase returns an **ID token** to the client.
2. Client sends that token in every request to this backend:
   ```
   Authorization: Bearer <firebase_id_token>
   ```
3. This backend verifies the token with Firebase Admin SDK (`app/core/firebase.py`) — it never sees a password, and never issues its own tokens.
4. Right after a user's very first login, the client should call `POST /users/sync` once. This is what creates the local `users` row in Postgres (tier thresholds, etc.) tied to the Firebase UID. Every other table's `user_id` foreign key will be this same Firebase UID (a string), not an auto-increment integer — this matters for every future migration.

There is no `/login` or `/signup` route in this backend, and there shouldn't be — that would mean you're reimplementing what Firebase already does.




