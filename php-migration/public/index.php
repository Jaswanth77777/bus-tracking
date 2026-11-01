<?php
declare(strict_types=1);
require_once __DIR__ . '/../app/bootstrap.php';

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$path = rtrim($path, '/') ?: '/';

if ($path === '/api/health' && $method === 'GET') {
    try {
        db()->query('SELECT 1');
        json_response(['ok' => true, 'service' => 'JOY University Transportation Management', 'database' => 'connected']);
    } catch (Throwable $e) {
        json_response(['ok' => false, 'error' => 'Database unavailable'], 503);
    }
}

if ($path === '/api/csrf' && $method === 'GET') {
    json_response(['ok' => true, 'csrf' => $_SESSION['csrf']]);
}

if ($path === '/api/login' && $method === 'POST') {
    require_csrf();
    $input = request_json();
    $identity = strtolower(trim((string)($input['identity'] ?? '')));
    $password = (string)($input['password'] ?? '');
    if ($identity === '' || $password === '') json_response(['ok' => false, 'error' => 'Email and password are required'], 422);
    $stmt = db()->prepare('SELECT id,name,email,password_hash,role,phone FROM users WHERE LOWER(email)=? AND is_active=1 LIMIT 1');
    $stmt->execute([$identity]);
    $user = $stmt->fetch();
    if (!$user || !password_verify($password, $user['password_hash'])) {
        json_response(['ok' => false, 'error' => 'Invalid login details'], 401);
    }
    session_regenerate_id(true);
    $_SESSION['user_id'] = (int)$user['id'];
    unset($user['password_hash']);
    json_response(['ok' => true, 'user' => $user, 'csrf' => $_SESSION['csrf']]);
}

if ($path === '/api/logout' && $method === 'POST') {
    require_csrf();
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $params['path'], '', $params['secure'], $params['httponly']);
    }
    session_destroy();
    json_response(['ok' => true]);
}

if ($path === '/api/me' && $method === 'GET') {
    $user = current_user();
    json_response(['ok' => true, 'user' => $user, 'csrf' => $_SESSION['csrf']]);
}

if ($path === '/' || $path === '/login') {
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JOY University Transport</title><body style="font-family:Inter,Arial,sans-serif;background:#f2f7ff;color:#10264a;margin:0"><main style="max-width:460px;margin:8vh auto;background:white;padding:32px;border-radius:18px;box-shadow:0 12px 40px #10264a18"><h1>JOY University</h1><p>Transportation Management System</p><p>PHP/MySQL migration is being built in this branch. Sign-in and role dashboards will be enabled after the module migration and database setup are completed.</p><p>Configure the MySQL database and import <code>database/schema.sql</code> before using the API.</p></main></body></html>';
    exit;
}

json_response(['ok' => false, 'error' => 'Endpoint not implemented yet'], 404);
