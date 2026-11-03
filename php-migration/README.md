# JOY University Transportation System — PHP/MySQL migration

This directory is the isolated PHP migration track. The original Flask/SQLite application remains untouched while the PHP implementation is built and tested.

## Runtime
- PHP 8.2+
- MySQL 8+
- PHP extensions: pdo_mysql, json, mbstring, openssl
- Web server document root: `php-migration/public`
- Configure the database and session secret using environment variables; never commit production credentials.

## Setup
1. Create a MySQL database and user.
2. Import `database/schema.sql`.
3. Copy `.env.example` to your host's environment configuration (do not commit secrets).
4. Point the PHP host's document root to `public/`.
5. Set `APP_BASE_URL` and `APP_SESSION_SECURE=1` when served over HTTPS.

## Migration status
This is a staged migration, not a declaration that every requested module is already complete. The Flask application remains the live deployment until the PHP implementation has parity, integration tests, a persistent database, and a successful staging deployment. Do not switch the production domain before that gate passes.

## GPS requirements
Driver GPS updates must only be accepted from an authenticated driver with an active bus assignment and active trip. The browser must obtain coordinates using the Geolocation API; the server stores timestamped coordinates in MySQL. No simulated fallback is part of the PHP implementation.

## Hosting
The current Vercel deployment is configured for the existing Python application. PHP hosting and MySQL provisioning are required for this migration; the existing Vercel deployment will not automatically run this PHP application.
