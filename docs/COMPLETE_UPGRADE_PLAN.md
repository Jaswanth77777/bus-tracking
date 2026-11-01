# JOY University Transport Management — Complete Upgrade Plan

This document is the acceptance checklist for the full Admin, Student and Driver transportation platform. The work is developed on `complete-joy-transport-upgrade`; `main` and the production Vercel deployment are intentionally untouched until review and approval.

## Product and visual system
- College identity: use the official JOY University logo asset supplied by the college; do not redraw or substitute it.
- Palette: navy `#102A43`, royal blue `#2563EB`, sky `#38BDF8`, background `#F4F7FB`, white surfaces, dark-navy/slate text.
- Typography: Poppins or Inter; consistent accessible icon family, spacing, focus states, contrast, empty/loading/error/success states.
- Responsive desktop, tablet and mobile layouts; shared header, side navigation, cards, tables, forms, dialogs and alerts.
- Separate branded login and role-specific landing pages.

## Authentication and authorization
- Login by email or institutional ID; secure password hashing; password reset/invitation flow; profile editing; session expiry and logout.
- Enforce role-based authorization on every API, not only by hiding navigation.
- Student data is restricted to the signed-in student; drivers can access only their assigned bus and active trips; admin/transport roles receive explicit permissions.
- Audit important administrative and account actions. Configure stable session secret and secure cookies in Vercel environment variables.

## Admin portal
- Overview KPIs: students, drivers, buses, active trips, live/stale/offline GPS, unresolved complaints and emergency alerts.
- CRUD and deactivation: students, drivers, users, buses, routes and ordered stops.
- Student details: student ID, department, year, phone, email, account invitation, assigned bus/route/pickup stop and fee status.
- Driver details: driver ID, phone, licence, account status and assigned bus/route.
- Fleet assignments with conflict prevention and assignment history.
- Fleet live map; trip history; boarding/QR attendance; fees and payment records; complaints; announcements; emergency acknowledgement/resolution.
- CSV and printable exports; activity logs; transport contact and operating settings.

## Student portal
- Profile and account details; assigned bus/route/driver/pickup stop.
- Assigned bus live map based only on actual GPS; GPS freshness, speed and last update.
- Route and stop list; ETA only when computed from a real routing/traffic source or explicitly labelled as an estimate.
- Notifications, QR attendance history, fee ledger/receipts, complaint submission/status and emergency contacts.

## Driver portal
- Assigned bus, route and ordered stops; profile and trip history.
- Start/end trip controls; browser Geolocation permission and GPS sharing state.
- GPS updates accepted only from the authenticated assigned driver during an active trip; validate coordinate bounds, accuracy, timestamp and update rate.
- No generated location fallback. Missing/stale GPS is clearly shown as unavailable/offline.
- Secure student boarding QR scanner; emergency alert; maintenance/bus problem reporting.

## Live tracking
- Leaflet with OpenStreetMap tiles; real coordinates from driver devices; multiple bus markers; route and stop markers; bus details and GPS freshness.
- Polling or a managed realtime provider compatible with Vercel serverless functions. Do not depend on a persistent Flask-SocketIO worker on Vercel.
- Never fabricate moving markers, coordinates, speed, distance or ETA in production.

## QR attendance
- Short-lived, signed or random high-entropy boarding tokens; token validation on the server.
- Driver-side scan/verification tied to an active trip, assigned bus and student; one boarding per student/trip policy; duplicate prevention and immutable timestamps.
- Admin attendance review/export; student attendance history. A student must not be able to self-submit a verified boarding record.

## Fees and payments
- Fee schedules, amount, due date, paid/pending/overdue status, payment ledger and receipts.
- Payment completion is recorded only from a verified payment-gateway webhook/server-side confirmation. A client button cannot mark a fee paid.
- Gateway selection and merchant credentials are deployment configuration, never committed to Git.

## Complaints, notifications and emergencies
- Student complaints with status, admin response and resolution history.
- Targeted and role-wide announcements for delays, route changes, trip start/end and general transport messages.
- Emergency records include reporter, bus/trip and timestamps where available; admin acknowledge/resolve workflow and audit trail.

## Reports
- Student, driver, bus, route, assignment, trip, attendance, GPS activity, fee, complaint and emergency reports.
- CSV export and print-friendly views; PDF generation can be added once the final report layouts are approved.

## Deployment architecture
- Frontend: existing HTML/CSS/JavaScript app.
- API: existing Python Flask application on Vercel.
- Persistent database: Neon PostgreSQL; no production data in local SQLite or Vercel `/tmp`.
- Map: Leaflet/OpenStreetMap.
- GPS: HTTPS browser Geolocation on driver's phone.
- Live updates: serverless-compatible polling initially; managed realtime service only if configured.
- Secrets: `JOY_BUS_SECRET`, `DATABASE_URL`, cookie settings and any payment/realtime credentials in Vercel Environment Variables only.

## Acceptance and release gates
- Automated tests for login, role boundaries, CRUD, assignment conflicts, trip state, GPS authorization/freshness, QR replay/duplicates, fees/webhook verification and exports.
- Manual tests on desktop, Android and iOS browsers; test denied GPS permission, poor signal, offline state, stale updates and session expiry.
- Confirm PostgreSQL persistence across serverless cold starts.
- Verify all buttons/forms perform real actions and provide feedback; no placeholder controls.
- Deploy preview and verify it before any production promotion.

## Current branch status
The first safety pass disables production demo credentials and simulated GPS, requires an active trip for driver GPS updates, and prevents GPS sharing from admin accounts. This is not the complete feature set. PostgreSQL migration, the remaining modules, frontend redesign, test suite and end-to-end Vercel verification remain release blockers and must be completed before calling the system production-ready.
