# JOY University Bus Tracking — Production Upgrade

This upgrade preserves the existing road map, smooth demo bus movement, bus selection, student services, authentication, driver GPS, complaints, maintenance, emergency alerts and admin monitoring, while adding the requested production-style transport features.

## Main features

- Student / Driver / Admin role-based login
- Secure password hashing with Werkzeug
- CSRF protection for state-changing browser requests
- Dedicated Driver Dashboard
- Driver sees only the assigned bus/trip
- Start Trip / End Trip
- Mobile browser GPS with permission handling
- Server-side GPS validation and GPS history
- Live / Offline / Demo GPS status
- Configurable offline timeout (`GPS_TIMEOUT_SECONDS`)
- Smooth selected-bus-only demo movement on the Leaflet road map
- Click bus marker or bus list to select and move that bus
- Auto-follow selected bus
- Routes and stops stored in SQLite
- Driver → Bus → Route assignments
- Admin fleet/driver/route/stop management controls
- Complaints, maintenance reports, emergency alerts and notifications
- Boarding history and student favorites
- Optional Socket.IO real-time events with polling fallback
- No campus photo or 3D campus view

## Demo accounts

- Admin: `admin@joyuniversity.edu` / `Admin@123`
- Driver: `driver@joyuniversity.edu` / `Driver@123`
- Student: `student@joyuniversity.edu` / `Student@123`

Change all demo passwords before production use.

## Local setup

1. Install Python 3.11+.
2. Create a virtual environment:

   Windows:
   `py -m venv .venv`
   `.venv\\Scripts\\activate`

   Linux/macOS:
   `python3 -m venv .venv`
   `source .venv/bin/activate`

3. Install packages:
   `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set a strong `JOY_BUS_SECRET`.
5. Start the application:
   `python app.py`
6. Open `http://127.0.0.1:5000`.

The SQLite database (`joy_bus_tracker.db`) is initialized automatically on first run. Existing older databases are migrated with missing columns/tables preserved where possible.

## Driver phone GPS

- Open the deployed HTTPS URL on the driver's phone.
- Log in as Driver.
- Open Driver Dashboard.
- Allow browser location permission.
- Start Trip, then Start Live GPS.
- Keep the page open while driving.
- The server validates latitude, longitude, speed and accuracy before storing the update.

Browsers normally require HTTPS for production geolocation. `localhost` is allowed for local development.

## Real-time behavior

If Flask-SocketIO is available, GPS/trip/emergency events are emitted to connected clients. The existing browser polling loop remains enabled as a reliable fallback, so a WebSocket connection is not required for map updates.

## Vercel deployment

This repository is Vercel-ready as a Flask application. Vercel now supports Flask directly, so no `/api` wrapper is required. The repository includes `vercel.json` and pins the Python runtime to 3.12.

1. Push/keep the repository on GitHub.
2. In Vercel, import `Jaswanth77777/bus-tracking` and keep the project root at the repository root.
3. Add these Environment Variables in Vercel:
   - `JOY_BUS_SECRET` — a long random secret (required for stable sessions).
   - `SESSION_COOKIE_SECURE=1`
   - `SESSION_COOKIE_SAMESITE=Lax`
   - `GPS_TIMEOUT_SECONDS=90` (optional).
4. Deploy. Vercel will install `requirements.txt` and serve `app.py` as the Flask application.

### Important: SQLite on Vercel

Vercel deployments use an immutable filesystem. When `VERCEL=1`, this app therefore uses `/tmp/joy_bus_tracker.db` so the application can start and operate as a demo. **SQLite data in `/tmp` is not durable and can disappear when the serverless instance is recycled; it is not suitable for production fleet data.** For persistent users, buses, GPS history, complaints and attendance, migrate the database to PostgreSQL or another managed database and set the application to use that database.

The driver's browser GPS also requires the deployed site to use HTTPS, which Vercel provides automatically.

## Production / Gunicorn

For a simple WSGI deployment:

`gunicorn -c gunicorn.conf.py app:app`

For Socket.IO deployments, use a Socket.IO-capable process configuration provided by your hosting platform and reverse proxy WebSocket upgrade requests. Keep HTTPS enabled and set `SESSION_COOKIE_SECURE=1`.

## HTTPS / reverse proxy

Use Nginx, Caddy, Apache, or a managed cloud HTTPS proxy in front of the app. Forward WebSocket upgrade headers when using Socket.IO. Do not expose Flask's development server directly to the public internet.

## Database

SQLite is suitable for a small deployment/demo. For a larger production fleet, move the same models to PostgreSQL and keep the API contract unchanged. Back up the database regularly.

## Important production checklist

- Replace all demo passwords.
- Set a long random `JOY_BUS_SECRET`.
- Use HTTPS.
- Set `SESSION_COOKIE_SECURE=1`.
- Restrict the reverse proxy and firewall.
- Run database backups.
- Use PostgreSQL for a large fleet/high-write GPS workload.
- Configure an appropriate GPS timeout for your operating area.
