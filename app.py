import os, sqlite3, time, math, secrets, re
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from flask_socketio import SocketIO
except Exception:
    SocketIO = None

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'joy_bus_tracker.db')
app = Flask(__name__)
app.secret_key = os.environ.get('JOY_BUS_SECRET') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE=os.environ.get('SESSION_COOKIE_SAMESITE','Lax'),
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE','0') == '1',
    MAX_CONTENT_LENGTH=1_000_000, JSON_SORT_KEYS=False
)
GPS_TIMEOUT_SECONDS = int(os.environ.get('GPS_TIMEOUT_SECONDS','90'))
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading') if SocketIO else None

CAMPUS = {'name':'JOY UNIVERSITY','lat':8.2436,'lon':77.6058,
'address':'Raja Nagar, Vadakangulam, Near Kanyakumari, Tirunelveli District, Tamil Nadu 627116','help':'8919209636'}

# DEMO route names requested for JOY-01 ... JOY-10.
# PATHS are 3D DEMO geometry, not official GPS coordinates.
ROUTES = {
'JOY-01':('Vencode via Colachel',['JOY UNIVERSITY','Vencode','Irenipuram','Nattalam','Karungal','Colachel']),
'JOY-02':('Pettai via Tirunelveli',['JOY UNIVERSITY','Nanguneri','Moontradaipu','Tirunelveli New Bus Stand','TVL Junction','Pettai']),
'JOY-03':('Kanyakumari',['JOY UNIVERSITY','Anjugramam','Kottaram','Vivekanadapuram','Kanyakumari']),
'JOY-04':('Chettikulam',['JOY UNIVERSITY','Avaraikulam','Koottapuli','Chettikulam']),
'JOY-05':('Nithiravilai via Kaliyakkavilai',['JOY UNIVERSITY','Parvathipuram','Marthandam','Kaliyakkavilai','Nithiravilai']),
'JOY-06':('Thengapattanam via Rajakkamangalam',['JOY UNIVERSITY','Rajakkamangalam','Asaripallam','Kottar','Thengapattanam']),
'JOY-07':('Kalakkad',['JOY UNIVERSITY','Kavalkinaru','Panagudi','Thirukurungudi','Kalakkad']),
'JOY-08':('Thisayanvilai',['JOY UNIVERSITY','Radhapuram','Kumbilampadu','Thisayanvilai']),
'JOY-09':('Thalayuthu via Tirunelveli',['JOY UNIVERSITY','Nanguneri','Moontradaipu','Palayamkottai','Thalayuthu']),
'JOY-10':('Ambasamudram',['JOY UNIVERSITY','Aralvaimozhi','Thovalai','Vellamadam','Ambasamudram'])}
PATHS = {
'JOY-01':[(0,0),(5,3),(10,6),(16,9),(23,12)],
'JOY-02':[(0,0),(4,-3),(9,-6),(15,-9),(23,-12)],
'JOY-03':[(0,0),(-4,3),(-9,6),(-15,9),(-22,12)],
'JOY-04':[(0,0),(-3,-4),(-7,-8),(-12,-12),(-18,-16)],
'JOY-05':[(0,0),(4,-5),(9,-10),(15,-15),(22,-20)],
'JOY-06':[(0,0),(5,4),(10,8),(16,12),(24,17)],
'JOY-07':[(0,0),(-5,-2),(-10,-5),(-16,-7),(-23,-10)],
'JOY-08':[(0,0),(3,5),(7,10),(12,15),(18,22)],
'JOY-09':[(0,0),(5,1),(10,2),(16,3),(23,4)],
'JOY-10':[(0,0),(-4,4),(-8,8),(-13,13),(-19,19)]}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('student','driver','admin','transport_manager','security')),uid TEXT UNIQUE,phone TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,student_no TEXT,department TEXT,year TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drivers(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,license_no TEXT,phone TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS routes(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stops(id INTEGER PRIMARY KEY AUTOINCREMENT,route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,name TEXT NOT NULL,stop_order INTEGER NOT NULL,lat REAL,lon REAL,active INTEGER DEFAULT 1,UNIQUE(route_id,stop_order));
CREATE TABLE IF NOT EXISTS buses(id INTEGER PRIMARY KEY AUTOINCREMENT,number TEXT UNIQUE NOT NULL,route_name TEXT NOT NULL,route_id INTEGER REFERENCES routes(id),driver_id INTEGER REFERENCES users(id),status TEXT DEFAULT 'RUNNING',capacity INTEGER DEFAULT 45,last_lat REAL,last_lon REAL,last_speed REAL DEFAULT 0,last_heading REAL DEFAULT 0,last_accuracy REAL,last_gps REAL,manual_until REAL DEFAULT 0,simulated INTEGER DEFAULT 1,enabled INTEGER DEFAULT 1,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS driver_bus_assignments(id INTEGER PRIMARY KEY AUTOINCREMENT,driver_id INTEGER NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,bus_id INTEGER NOT NULL REFERENCES buses(id) ON DELETE CASCADE,route_id INTEGER REFERENCES routes(id),starts_at TEXT NOT NULL,ends_at TEXT,active INTEGER DEFAULT 1,UNIQUE(driver_id,bus_id,starts_at));
CREATE TABLE IF NOT EXISTS trips(id INTEGER PRIMARY KEY AUTOINCREMENT,bus_id INTEGER NOT NULL REFERENCES buses(id),driver_id INTEGER NOT NULL REFERENCES users(id),route_id INTEGER REFERENCES routes(id),started_at TEXT NOT NULL,ended_at TEXT,status TEXT DEFAULT 'ACTIVE',start_lat REAL,start_lon REAL,end_lat REAL,end_lon REAL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gps_locations(id INTEGER PRIMARY KEY AUTOINCREMENT,bus_id INTEGER NOT NULL REFERENCES buses(id) ON DELETE CASCADE,driver_id INTEGER NOT NULL REFERENCES users(id),trip_id INTEGER REFERENCES trips(id),lat REAL NOT NULL,lon REAL NOT NULL,speed REAL DEFAULT 0,heading REAL DEFAULT 0,accuracy REAL,recorded_at TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS complaints(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),bus_id INTEGER REFERENCES buses(id),subject TEXT NOT NULL,message TEXT NOT NULL,status TEXT DEFAULT 'SUBMITTED',created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS maintenance_reports(id INTEGER PRIMARY KEY AUTOINCREMENT,bus_id INTEGER NOT NULL REFERENCES buses(id),driver_id INTEGER REFERENCES users(id),issue TEXT NOT NULL,status TEXT DEFAULT 'REPORTED',created_at TEXT NOT NULL,updated_at TEXT);
CREATE TABLE IF NOT EXISTS maintenance(id INTEGER PRIMARY KEY AUTOINCREMENT,bus_id INTEGER,issue TEXT,status TEXT DEFAULT 'GOOD',created_at TEXT);
CREATE TABLE IF NOT EXISTS emergency_alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),bus_id INTEGER REFERENCES buses(id),trip_id INTEGER REFERENCES trips(id),type TEXT DEFAULT 'EMERGENCY',message TEXT NOT NULL,status TEXT DEFAULT 'ACTIVE',created_at TEXT NOT NULL,acknowledged_at TEXT,resolved_at TEXT);
CREATE TABLE IF NOT EXISTS emergencies(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,bus_id INTEGER,message TEXT,status TEXT DEFAULT 'ACTIVE',created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id),title TEXT NOT NULL,message TEXT NOT NULL,role TEXT,kind TEXT DEFAULT 'INFO',bus_id INTEGER REFERENCES buses(id),created_at TEXT NOT NULL,read_at TEXT);
CREATE TABLE IF NOT EXISTS boarding_history(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id),bus_id INTEGER NOT NULL REFERENCES buses(id),stop_id INTEGER REFERENCES stops(id),stop_name TEXT,boarded_at TEXT NOT NULL,qr_token TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,bus_id INTEGER,stop_name TEXT,boarded_at TEXT,qr_token TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS favorites(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,bus_id INTEGER REFERENCES buses(id) ON DELETE CASCADE,route_id INTEGER REFERENCES routes(id) ON DELETE CASCADE,created_at TEXT NOT NULL,UNIQUE(user_id,bus_id,route_id));
CREATE INDEX IF NOT EXISTS idx_gps_bus_time ON gps_locations(bus_id,recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_gps_driver_time ON gps_locations(driver_id,recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_trips_bus_status ON trips(bus_id,status);
CREATE INDEX IF NOT EXISTS idx_assign_driver_active ON driver_bus_assignments(driver_id,active);
CREATE INDEX IF NOT EXISTS idx_notifications_user_time ON notifications(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_emergency_status ON emergency_alerts(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status,created_at DESC);
'''


def db():
    c=sqlite3.connect(DB,timeout=10); c.row_factory=sqlite3.Row; return c

def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

@app.after_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options','nosniff')
    response.headers.setdefault('X-Frame-Options','DENY')
    response.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
    response.headers.setdefault('Cache-Control','no-store' if request.path.startswith('/api/') else 'no-cache')
    return response

def csrf_token():
    if 'csrf_token' not in session: session['csrf_token'] = secrets.token_urlsafe(32)
    return session['csrf_token']

@app.context_processor
def inject_template_security(): return {'csrf_token': csrf_token()}

@app.before_request
def protect_mutations():
    if request.method in ('POST','PUT','PATCH','DELETE') and request.path not in ('/api/login','/api/logout','/api/register/student'):
        token = request.headers.get('X-CSRF-Token')
        if not token or not secrets.compare_digest(token, session.get('csrf_token','')):
            return jsonify(ok=False,error='CSRF validation failed'), 403

def audit_notification(title, message, role=None, user_id=None, kind='INFO', bus_id=None, c=None):
    own = c is None
    c = c or db()
    c.execute('INSERT INTO notifications(user_id,title,message,role,kind,bus_id,created_at) VALUES(?,?,?,?,?,?,?)',(user_id,title,message,role,kind,bus_id,now()))
    if own: c.commit(); c.close()

def validate_coordinates(lat, lon, speed=0, accuracy=None):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): return False, 'Invalid coordinates'
    if not (0 <= speed <= 180): return False, 'Invalid speed'
    if accuracy is not None and not (0 <= accuracy <= 5000): return False, 'Invalid GPS accuracy'
    return True, ''

def assigned_bus_for_driver(c, user_id):
    row=c.execute("SELECT b.* FROM buses b JOIN drivers d ON d.user_id=b.driver_id WHERE b.driver_id=? AND b.enabled=1 LIMIT 1",(user_id,)).fetchone()
    if row: return row
    row=c.execute("SELECT b.* FROM buses b JOIN driver_bus_assignments a ON a.bus_id=b.id JOIN drivers d ON d.id=a.driver_id WHERE d.user_id=? AND a.active=1 AND b.enabled=1 ORDER BY a.id DESC LIMIT 1",(user_id,)).fetchone()
    return row

def active_trip(c, bus_id, driver_id):
    return c.execute("SELECT * FROM trips WHERE bus_id=? AND driver_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(bus_id,driver_id)).fetchone()

def table_columns(c, table):
    return {row['name'] for row in c.execute(f'PRAGMA table_info({table})').fetchall()}

def ensure_column(c, table, column, definition):
    cols = table_columns(c, table)
    if column not in cols:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

def migrate_old_database(c):
    # CREATE TABLE IF NOT EXISTS does not upgrade an existing SQLite table.
    # Older project versions used a different buses schema, so add missing
    # columns instead of crashing with: "no column named route_name".
    if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='buses'").fetchone():
        ensure_column(c, 'buses', 'number', 'TEXT')
        ensure_column(c, 'buses', 'route_name', 'TEXT')
        ensure_column(c, 'buses', 'driver_id', 'INTEGER')
        ensure_column(c, 'buses', 'status', "TEXT DEFAULT 'RUNNING'")
        ensure_column(c, 'buses', 'capacity', 'INTEGER DEFAULT 45')
        ensure_column(c, 'buses', 'last_lat', 'REAL')
        ensure_column(c, 'buses', 'last_lon', 'REAL')
        ensure_column(c, 'buses', 'last_speed', 'REAL DEFAULT 0')
        ensure_column(c, 'buses', 'last_heading', 'REAL DEFAULT 0')
        ensure_column(c, 'buses', 'last_accuracy', 'REAL')
        ensure_column(c, 'buses', 'last_gps', 'REAL')
        ensure_column(c, 'buses', 'manual_until', 'REAL DEFAULT 0')
        ensure_column(c, 'buses', 'simulated', 'INTEGER DEFAULT 1')

        cols = table_columns(c, 'buses')
        # Preserve route names from common older column names when possible.
        if 'route' in cols:
            c.execute("UPDATE buses SET route_name=route WHERE (route_name IS NULL OR route_name='')")
        if 'name' in cols:
            c.execute("UPDATE buses SET route_name=name WHERE (route_name IS NULL OR route_name='')")

        # If an older version has bus_number instead of number, copy it.
        if 'bus_number' in cols:
            c.execute("UPDATE buses SET number=bus_number WHERE (number IS NULL OR number='')")

    # Older databases may not have these tables at all; SCHEMA above creates them.

def init_db():
    c=db(); c.execute('PRAGMA foreign_keys=ON'); c.executescript(SCHEMA)
    migrate_old_database(c)
    # Ensure columns used by legacy databases.
    for table, col, definition in [
        ('users','active','INTEGER DEFAULT 1'),('users','updated_at','TEXT'),('buses','route_id','INTEGER'),('buses','enabled','INTEGER DEFAULT 1'),('buses','created_at','TEXT'),('buses','updated_at','TEXT')]:
        ensure_column(c,table,col,definition)
    c.execute("UPDATE buses SET status='RUNNING' WHERE status IS NULL OR status=''")
    c.execute("UPDATE buses SET capacity=45 WHERE capacity IS NULL")
    c.execute("UPDATE buses SET simulated=1 WHERE simulated IS NULL")
    c.execute("UPDATE buses SET enabled=1 WHERE enabled IS NULL")
    for n,e,p,r,u in [('System Admin','admin@joyuniversity.edu','Admin@123','admin','ADM001'),('Demo Driver','driver@joyuniversity.edu','Driver@123','driver','DRV001'),('Demo Student','student@joyuniversity.edu','Student@123','student','JOY001')]:
        c.execute('INSERT OR IGNORE INTO users(name,email,password,role,uid,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(n,e,generate_password_hash(p),'%s'%r,u,1,now(),now()))
    # Synchronize driver/student profile tables.
    for r in c.execute("SELECT id FROM users WHERE role='driver'").fetchall(): c.execute('INSERT OR IGNORE INTO drivers(user_id,created_at) VALUES(?,?)',(r['id'],now()))
    for r in c.execute("SELECT id FROM users WHERE role='student'").fetchall(): c.execute('INSERT OR IGNORE INTO students(user_id,created_at) VALUES(?,?)',(r['id'],now()))
    # Seed routes and stops from the existing working route definitions.
    for number,(route_name,stop_names) in ROUTES.items():
        rr=c.execute('SELECT id FROM routes WHERE code=?',(number,)).fetchone()
        if not rr:
            c.execute('INSERT INTO routes(code,name,created_at) VALUES(?,?,?)',(number,route_name,now())); rr=c.execute('SELECT last_insert_rowid() id').fetchone()
        rid=rr['id']
        pts=PATHS[number]
        for i,stop in enumerate(stop_names):
            x,z=pts[min(i,len(pts)-1)]; lat=CAMPUS['lat']+z*.004; lon=CAMPUS['lon']+x*.004
            c.execute('INSERT OR IGNORE INTO stops(route_id,name,stop_order,lat,lon,created_at) VALUES(?,?,?,?,?,?)' if False else 'INSERT OR IGNORE INTO stops(route_id,name,stop_order,lat,lon) VALUES(?,?,?,?,?)',(rid,stop,i,lat,lon))
        c.execute('UPDATE buses SET route_id=? WHERE number=?',(rid,number))
        c.execute('INSERT OR IGNORE INTO buses(number,route_name,route_id,status,capacity,simulated,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(number,route_name,rid,'RUNNING',45,1,1,now(),now()))
    d=c.execute("SELECT id FROM users WHERE uid='DRV001'").fetchone(); b=c.execute("SELECT id,route_id FROM buses WHERE number='JOY-01'").fetchone()
    if d and b:
        c.execute('UPDATE buses SET driver_id=? WHERE id=?',(d['id'],b['id']))
        dr=c.execute('SELECT id FROM drivers WHERE user_id=?',(d['id'],)).fetchone()
        if dr: c.execute('INSERT OR IGNORE INTO driver_bus_assignments(driver_id,bus_id,route_id,starts_at,active) VALUES(?,?,?,?,1)',(dr['id'],b['id'],b['route_id'],now()))
    c.commit(); c.close()


def current_user():
    uid=session.get('user_id')
    if not uid:return None
    c=db(); r=c.execute('SELECT * FROM users WHERE id=? AND active=1',(uid,)).fetchone(); c.close();
    if not r:return None
    u=dict(r); u.pop('password',None); return u

def auth(roles=None):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            u=current_user()
            if not u:return jsonify(ok=False,error='Login required'),401
            if roles and u['role'] not in roles:return jsonify(ok=False,error='Access denied'),403
            return fn(*args,**kwargs)
        return wrapped
    return deco

def demo_state(number):
    pts=PATHS[number]; duration=70+(int(number[-2:])%4)*12; t=(time.time()%duration)/duration
    q=t*(len(pts)-1); i=min(len(pts)-2,int(q)); f=q-i
    x=pts[i][0]+(pts[i+1][0]-pts[i][0])*f; z=pts[i][1]+(pts[i+1][1]-pts[i][1])*f
    h=(math.degrees(math.atan2(pts[i+1][0]-pts[i][0],pts[i+1][1]-pts[i][1]))+360)%360
    return x,z,h,t

def bus_payload(row):
    b=dict(row); number=b['number']; route,stops=ROUTES[number]
    manual=bool(b['manual_until'] and b['manual_until']>time.time() and b['last_lat'] is not None)
    stale_live=bool(b['last_gps'] and (time.time()-b['last_gps'])>GPS_TIMEOUT_SECONDS) and not bool(b['simulated'])
    if stale_live: manual=False
    if manual:
        lat,lon=b['last_lat'],b['last_lon']; speed=b['last_speed'] or 0; heading=b['last_heading'] or 0; accuracy=b['last_accuracy']; progress=None; gps='LIVE GPS'
    else:
        x,z,heading,progress=demo_state(number); lat=CAMPUS['lat']+z*.004; lon=CAMPUS['lon']+x*.004; speed=28+(b['id']%5)*3; accuracy=None; gps='DEMO GPS'
    idx=min(len(stops)-1,int((progress or 0)*(len(stops)-1)))
    route_km=round(sum(math.hypot(PATHS[number][i+1][0]-PATHS[number][i][0],PATHS[number][i+1][1]-PATHS[number][i][1]) for i in range(len(PATHS[number])-1))*0.42,1)
    duration=70+(int(number[-2:])%4)*12
    return {'id':b['id'],'number':number,'route':route,'stops':stops,'driver':'Assigned Driver' if b['driver_id'] else 'Unassigned','lat':lat,'lon':lon,'speed':round(speed,1),'heading':round(heading,1),'next_stop':stops[idx],'destination':stops[-1],'eta_minutes':max(1,round((1-(progress or 0))*18)),'status':('OFFLINE' if stale_live else b['status']),'capacity':b['capacity'],'passengers':min(b['capacity'],8+(int(time.time()/10)+b['id'])%30),'live':manual,'gps_status':('OFFLINE' if stale_live else gps),'accuracy':accuracy,'last_update':datetime.fromtimestamp(b['last_gps']).strftime('%d %b %Y %I:%M:%S') if b['last_gps'] else 'Demo clock','progress':progress,'path':PATHS[number],'route_km':route_km,'demo_duration':duration,'server_time':time.time()}


@app.get('/api/csrf')
def api_csrf(): return jsonify(ok=True,token=csrf_token())

@app.get('/api/routes')
def routes_api():
    c=db(); rows=c.execute('SELECT r.*, (SELECT COUNT(*) FROM stops s WHERE s.route_id=r.id AND s.active=1) stop_count FROM routes r WHERE r.active=1 ORDER BY r.code').fetchall(); c.close(); return jsonify(ok=True,routes=[dict(r) for r in rows])

@app.get('/api/routes/<int:route_id>/stops')
def route_stops(route_id):
    c=db(); rows=c.execute('SELECT * FROM stops WHERE route_id=? AND active=1 ORDER BY stop_order',(route_id,)).fetchall(); c.close(); return jsonify(ok=True,stops=[dict(r) for r in rows])

@app.get('/api/driver/me')
@auth(['driver'])
def driver_me():
    u=current_user(); c=db(); b=assigned_bus_for_driver(c,u['id']);
    if not b: c.close(); return jsonify(ok=True,driver=u,bus=None,trip=None)
    t=active_trip(c,b['id'],u['id']); route=c.execute('SELECT * FROM routes WHERE id=?',(b['route_id'],)).fetchone(); stops=c.execute('SELECT * FROM stops WHERE route_id=? AND active=1 ORDER BY stop_order',(b['route_id'],)).fetchall(); c.close()
    return jsonify(ok=True,driver=u,bus=bus_payload(b),trip=dict(t) if t else None,route=dict(route) if route else None,stops=[dict(x) for x in stops])

@app.post('/api/driver/trips/start')
@auth(['driver'])
def driver_start_trip():
    u=current_user(); c=db(); b=assigned_bus_for_driver(c,u['id'])
    if not b: c.close(); return jsonify(ok=False,error='No active bus assignment'),400
    if active_trip(c,b['id'],u['id']): c.close(); return jsonify(ok=False,error='Trip already active'),400
    t=now(); c.execute("INSERT INTO trips(bus_id,driver_id,route_id,started_at,status,created_at) VALUES(?,?,?,?,?,?)",(b['id'],u['id'],b['route_id'],t,'ACTIVE',t)); trip_id=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
    c.execute("UPDATE buses SET status='RUNNING',updated_at=? WHERE id=?",(t,b['id'])); audit_notification('Trip started',f"{b['number']} trip started",'admin',kind='TRIP_STARTED',bus_id=b['id'],c=c); c.commit(); c.close(); emit_event('trip_started',{'bus_id':b['id'],'trip_id':trip_id}); return jsonify(ok=True,trip_id=trip_id)

@app.post('/api/driver/trips/end')
@auth(['driver'])
def driver_end_trip():
    u=current_user(); c=db(); b=assigned_bus_for_driver(c,u['id'])
    if not b: c.close(); return jsonify(ok=False,error='No assigned bus'),400
    t=active_trip(c,b['id'],u['id'])
    if not t: c.close(); return jsonify(ok=False,error='No active trip'),400
    end=now(); c.execute("UPDATE trips SET ended_at=?,status='ENDED',end_lat=?,end_lon=? WHERE id=?",(end,b['last_lat'],b['last_lon'],t['id'])); c.execute("UPDATE buses SET status='STOPPED',updated_at=? WHERE id=?",(end,b['id'])); audit_notification('Trip ended',f"{b['number']} trip ended",'admin',kind='TRIP_ENDED',bus_id=b['id'],c=c); c.commit(); c.close(); emit_event('trip_ended',{'bus_id':b['id'],'trip_id':t['id']}); return jsonify(ok=True)

@app.get('/api/trips')
@auth()
def trips_api():
    u=current_user(); c=db();
    if u['role']=='driver': rows=c.execute('SELECT t.*,b.number bus_number,r.name route_name FROM trips t JOIN buses b ON b.id=t.bus_id LEFT JOIN routes r ON r.id=t.route_id WHERE t.driver_id=? ORDER BY t.id DESC LIMIT 100',(u['id'],)).fetchall()
    elif u['role']=='student': rows=c.execute("SELECT t.*,b.number bus_number,r.name route_name FROM trips t JOIN buses b ON b.id=t.bus_id LEFT JOIN routes r ON r.id=t.route_id WHERE t.status='ACTIVE' ORDER BY t.id DESC LIMIT 100").fetchall()
    else: rows=c.execute('SELECT t.*,b.number bus_number,r.name route_name,u.name driver_name FROM trips t JOIN buses b ON b.id=t.bus_id LEFT JOIN routes r ON r.id=t.route_id JOIN users u ON u.id=t.driver_id ORDER BY t.id DESC LIMIT 100').fetchall()
    c.close(); return jsonify(ok=True,trips=[dict(r) for r in rows])

def emit_event(event,payload):
    if socketio:
        try: socketio.emit(event,payload)
        except Exception: pass

@app.get('/api/health')
def health():
    return jsonify(ok=True,service='JOY University Bus Tracking',time=time.time(),
                   realtime='gps+polling',fleet_size=len(ROUTES))

@app.get('/api/me')
def api_me(): return jsonify(ok=True,user=current_user(),campus=CAMPUS)

@app.post('/api/login')
def login():
    d=request.get_json() or {}; identity=d.get('identity','').strip().lower(); password=d.get('password',''); c=db(); r=c.execute('SELECT * FROM users WHERE lower(email)=? OR lower(uid)=?',(identity,identity)).fetchone(); c.close()
    if not r or not r['active'] or not check_password_hash(r['password'],password):return jsonify(ok=False,error='Invalid login details'),401
    session.clear(); session['user_id']=r['id']; csrf_token(); u=dict(r); u.pop('password',None); return jsonify(ok=True,user=u)

@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

@app.post('/api/register/student')
def register_student():
    d=request.get_json() or {}; name=d.get('name','').strip(); email=d.get('email','').strip().lower(); password=d.get('password','')
    if not name or '@' not in email or len(password)<8:return jsonify(ok=False,error='Name, email and 8+ character password required'),400
    c=db()
    try:
        n=c.execute("SELECT COUNT(*) n FROM users WHERE role='student'").fetchone()['n']+1; uid=f"JOY-ST-{datetime.now().year}-{n:04d}"
        c.execute('INSERT INTO users(name,email,password,role,uid,created_at) VALUES(?,?,?,?,?,?)',(name,email,generate_password_hash(password),'student',uid,now())); c.commit()
    except sqlite3.IntegrityError:c.close(); return jsonify(ok=False,error='Email already registered'),400
    c.close(); return jsonify(ok=True,uid=uid)

@app.get('/api/buses')
def buses():
    c=db(); u=current_user()
    if u and u['role']=='driver':
        b=assigned_bus_for_driver(c,u['id']); rows=[b] if b else []
    else:
        rows=c.execute('SELECT * FROM buses WHERE enabled=1 ORDER BY id').fetchall()
    c.close(); return jsonify(ok=True,buses=[bus_payload(r) for r in rows],server_time=time.time())

@app.get('/api/buses/<int:bus_id>')
def bus_detail(bus_id):
    c=db(); r=c.execute('SELECT * FROM buses WHERE id=?',(bus_id,)).fetchone(); u=current_user()
    if u and u['role']=='driver':
        b=assigned_bus_for_driver(c,u['id']);
        if not b or b['id']!=bus_id:c.close();return jsonify(ok=False,error='Access denied'),403
    c.close()
    if not r:return jsonify(ok=False,error='Bus not found'),404
    return jsonify(ok=True,bus=bus_payload(r))

@app.post('/api/gps')
@auth(['driver','admin'])
def gps():
    d=request.get_json() or {}
    try:
        lat=float(d['lat']); lon=float(d['lon']); speed=max(0,float(d.get('speed',0))); heading=float(d.get('heading',0) or 0); accuracy=float(d.get('accuracy')) if d.get('accuracy') is not None else None
    except (KeyError,TypeError,ValueError): return jsonify(ok=False,error='Invalid GPS payload'),400
    ok,msg=validate_coordinates(lat,lon,speed,accuracy)
    if not ok:return jsonify(ok=False,error=msg),400
    u=current_user(); c=db()
    if u['role']=='driver':
        r=assigned_bus_for_driver(c,u['id']); bid=r['id'] if r else None
        if not bid:c.close();return jsonify(ok=False,error='No bus assigned to this driver'),400
    else:
        try: bid=int(d.get('bus_id'))
        except (TypeError,ValueError): c.close();return jsonify(ok=False,error='Admin bus_id required'),400
        r=c.execute('SELECT * FROM buses WHERE id=? AND enabled=1',(bid,)).fetchone()
        if not r:c.close();return jsonify(ok=False,error='Bus not found'),404
    trip=active_trip(c,bid,u['id']) if u['role']=='driver' else c.execute("SELECT * FROM trips WHERE bus_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(bid,)).fetchone()
    t=time.time(); stamp=now()
    c.execute("UPDATE buses SET last_lat=?,last_lon=?,last_speed=?,last_heading=?,last_accuracy=?,last_gps=?,manual_until=?,simulated=0,status='RUNNING',updated_at=? WHERE id=?",(lat,lon,speed,heading,accuracy,t,t+GPS_TIMEOUT_SECONDS*2,stamp,bid))
    c.execute('INSERT INTO gps_locations(bus_id,driver_id,trip_id,lat,lon,speed,heading,accuracy,recorded_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(bid,u['id'],trip['id'] if trip else None,lat,lon,speed,heading,accuracy,stamp,stamp))
    c.commit(); c.close(); payload={'bus_id':bid,'lat':lat,'lon':lon,'speed':speed,'heading':heading,'accuracy':accuracy,'last_update':stamp,'status':'RUNNING','live':True}
    emit_event('bus_update',payload); return jsonify(ok=True,**payload)

@app.post('/api/gps/stop')
@auth(['driver'])
def gps_stop():
    u=current_user(); c=db(); b=assigned_bus_for_driver(c,u['id'])
    if b:c.execute("UPDATE buses SET manual_until=0,simulated=1,status='STOPPED',updated_at=? WHERE id=?",(now(),b['id']))
    c.commit(); c.close(); return jsonify(ok=True)

@app.post('/api/emergency')
@auth()
def emergency():
    d=request.get_json() or {}; u=current_user(); c=db(); bid=d.get('bus_id')
    if u['role']=='driver':
        b=assigned_bus_for_driver(c,u['id']); bid=b['id'] if b else None
    try: bid=int(bid) if bid is not None else None
    except: bid=None
    if bid is not None and not c.execute('SELECT id FROM buses WHERE id=?',(bid,)).fetchone(): c.close();return jsonify(ok=False,error='Bus not found'),404
    message=str(d.get('message','Emergency reported')).strip() or 'Emergency reported'; typ=str(d.get('type','EMERGENCY')).upper()
    trip=None
    if bid: trip=c.execute("SELECT id FROM trips WHERE bus_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(bid,)).fetchone()
    stamp=now(); c.execute('INSERT INTO emergency_alerts(user_id,bus_id,trip_id,type,message,created_at) VALUES(?,?,?,?,?,?)',(u['id'],bid,trip['id'] if trip else None,typ,message,stamp)); eid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
    c.execute('INSERT INTO emergencies(user_id,bus_id,message,created_at) VALUES(?,?,?,?)',(u['id'],bid,message,stamp)); audit_notification('EMERGENCY',message,'admin',kind='EMERGENCY',bus_id=bid,c=c); c.commit(); c.close(); emit_event('emergency',{'id':eid,'bus_id':bid,'message':message,'status':'ACTIVE'}); return jsonify(ok=True,id=eid)

@app.post('/api/complaints')
@auth()
def complaint():
    d=request.get_json() or {}; c=db(); c.execute('INSERT INTO complaints(user_id,bus_id,subject,message,created_at) VALUES(?,?,?,?,?)',(current_user()['id'],d.get('bus_id'),d.get('subject','Bus complaint'),d.get('message',''),now())); c.commit(); c.close(); return jsonify(ok=True)

@app.post('/api/attendance')
@auth(['student'])
def attendance():
    d=request.get_json() or {}; token=secrets.token_urlsafe(18); c=db()
    try:
        bid=int(d.get('bus_id')); stop=str(d.get('stop_name','JOY UNIVERSITY')).strip() or 'JOY UNIVERSITY'
    except (TypeError,ValueError):
        c.close(); return jsonify(ok=False,error='Valid bus is required'),400
    if not c.execute('SELECT id FROM buses WHERE id=?',(bid,)).fetchone():
        c.close(); return jsonify(ok=False,error='Bus not found'),404
    try:
        stamp=now(); c.execute('INSERT INTO attendance(user_id,bus_id,stop_name,boarded_at,qr_token) VALUES(?,?,?,?,?)',
                  (current_user()['id'],bid,stop,stamp,token)); c.execute('INSERT INTO boarding_history(user_id,bus_id,stop_name,boarded_at,qr_token) VALUES(?,?,?,?,?)',(current_user()['id'],bid,stop,stamp,token)); c.commit()
    except sqlite3.IntegrityError:
        c.close(); return jsonify(ok=False,error='Attendance already recorded'),400
    c.close(); return jsonify(ok=True,token=token,boarded_at=now())

@app.get('/api/notifications')
@auth()
def notifications():
    u=current_user(); c=db(); rows=c.execute("SELECT * FROM notifications WHERE (role IS NULL OR role='' OR role=?) AND (user_id IS NULL OR user_id=?) ORDER BY id DESC LIMIT 50",(u['role'],u['id'])).fetchall(); c.close(); return jsonify(ok=True,items=[dict(r) for r in rows])

@app.get('/api/complaints')
@auth()
def complaints():
    u=current_user(); c=db()
    if u['role'] in ('admin','transport_manager','security'):
        rows=c.execute('SELECT c.*,u.name user_name,b.number bus_number FROM complaints c LEFT JOIN users u ON u.id=c.user_id LEFT JOIN buses b ON b.id=c.bus_id ORDER BY c.id DESC LIMIT 100').fetchall()
    else:
        rows=c.execute('SELECT c.*,b.number bus_number FROM complaints c LEFT JOIN buses b ON b.id=c.bus_id WHERE c.user_id=? ORDER BY c.id DESC LIMIT 30',(u['id'],)).fetchall()
    c.close(); return jsonify(ok=True,items=[dict(r) for r in rows])

@app.patch('/api/complaints/<int:complaint_id>')
@auth(['admin','transport_manager','security'])
def complaint_update(complaint_id):
    d=request.get_json() or {}; status=str(d.get('status','')).upper().strip()
    if status not in ('SUBMITTED','IN_PROGRESS','RESOLVED','REJECTED'):
        return jsonify(ok=False,error='Invalid complaint status'),400
    c=db(); r=c.execute('SELECT * FROM complaints WHERE id=?',(complaint_id,)).fetchone()
    if not r: c.close(); return jsonify(ok=False,error='Complaint not found'),404
    c.execute('UPDATE complaints SET status=? WHERE id=?',(status,complaint_id))
    c.execute('INSERT INTO notifications(title,message,role,created_at) VALUES(?,?,?,?)',
              ('Complaint update',f'Complaint #{complaint_id} is now {status}.','student',now()))
    c.commit(); c.close(); return jsonify(ok=True)

@app.get('/api/attendance')
@auth()
def attendance_list():
    u=current_user(); c=db()
    if u['role'] in ('admin','transport_manager','security'):
        rows=c.execute('SELECT a.*,u.name user_name,u.uid,b.number bus_number FROM attendance a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN buses b ON b.id=a.bus_id ORDER BY a.id DESC LIMIT 100').fetchall()
    else:
        rows=c.execute('SELECT a.*,b.number bus_number FROM attendance a LEFT JOIN buses b ON b.id=a.bus_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 30',(u['id'],)).fetchall()
    c.close(); return jsonify(ok=True,items=[dict(r) for r in rows])

@app.get('/api/maintenance')
@auth(['admin','transport_manager','security','driver'])
def maintenance_list():
    u=current_user(); c=db()
    if u['role']=='driver':
        rows=c.execute('SELECT m.*,b.number bus_number FROM maintenance m LEFT JOIN buses b ON b.id=m.bus_id WHERE b.driver_id=? ORDER BY m.id DESC LIMIT 30',(u['id'],)).fetchall()
    else:
        rows=c.execute('SELECT m.*,b.number bus_number FROM maintenance m LEFT JOIN buses b ON b.id=m.bus_id ORDER BY m.id DESC LIMIT 100').fetchall()
    c.close(); return jsonify(ok=True,items=[dict(r) for r in rows])

@app.post('/api/maintenance')
@auth(['admin','transport_manager','driver'])
def maintenance_create():
    d=request.get_json() or {}; issue=str(d.get('issue','')).strip(); status=str(d.get('status','REPORTED')).upper().strip()
    if not issue:return jsonify(ok=False,error='Issue is required'),400
    if status not in ('GOOD','REPORTED','IN_PROGRESS','OUT_OF_SERVICE','RESOLVED'):return jsonify(ok=False,error='Invalid maintenance status'),400
    c=db(); bid=d.get('bus_id')
    if current_user()['role']=='driver':
        r=c.execute('SELECT id FROM buses WHERE driver_id=? LIMIT 1',(current_user()['id'],)).fetchone()
        bid=r['id'] if r else None
    try: bid=int(bid)
    except (TypeError,ValueError): c.close(); return jsonify(ok=False,error='Bus is required'),400
    if not c.execute('SELECT id FROM buses WHERE id=?',(bid,)).fetchone():c.close();return jsonify(ok=False,error='Bus not found'),404
    c.execute('INSERT INTO maintenance(bus_id,issue,status,created_at) VALUES(?,?,?,?)',(bid,issue,status,now()))
    c.execute('INSERT INTO notifications(title,message,role,created_at) VALUES(?,?,?,?)',('Maintenance report',f'Bus #{bid}: {issue}','admin',now()))
    c.commit(); c.close(); return jsonify(ok=True)

@app.patch('/api/emergencies/<int:emergency_id>')
@auth(['admin','transport_manager','security'])
def emergency_update(emergency_id):
    d=request.get_json() or {}; status=str(d.get('status','')).upper().strip()
    if status not in ('ACTIVE','ACKNOWLEDGED','RESOLVED'):return jsonify(ok=False,error='Invalid emergency status'),400
    c=db(); r=c.execute('SELECT * FROM emergencies WHERE id=?',(emergency_id,)).fetchone()
    if not r:c.close();return jsonify(ok=False,error='Emergency not found'),404
    c.execute('UPDATE emergencies SET status=? WHERE id=?',(status,emergency_id)); er=c.execute('SELECT bus_id FROM emergencies WHERE id=?',(emergency_id,)).fetchone(); ea=c.execute('SELECT id FROM emergency_alerts WHERE bus_id=? ORDER BY id DESC LIMIT 1',(er['bus_id'],)).fetchone() if er and er['bus_id'] else None
    if ea:
        c.execute("UPDATE emergency_alerts SET status=?,acknowledged_at=CASE WHEN ?=\'ACKNOWLEDGED\' THEN ? ELSE acknowledged_at END,resolved_at=CASE WHEN ?=\'RESOLVED\' THEN ? ELSE resolved_at END WHERE id=?",(status,status,now(),status,now(),ea['id']))
    c.execute('INSERT INTO notifications(title,message,role,created_at) VALUES(?,?,?,?)',('Emergency update',f'Emergency #{emergency_id} is now {status}.','admin',now()))
    c.commit();c.close();return jsonify(ok=True)

@app.post('/api/driver/problem')
@auth(['driver'])
def driver_problem():
    d=request.get_json() or {}; issue=str(d.get('issue') or '').strip(); kind=str(d.get('type') or 'BREAKDOWN').upper()
    allowed={'BREAKDOWN','ACCIDENT','DELAY','TRAFFIC','EMERGENCY'}
    if kind not in allowed or not issue:return jsonify(ok=False,error='Problem type and description are required'),400
    u=current_user(); c=db(); b=assigned_bus_for_driver(c,u['id'])
    if not b:c.close();return jsonify(ok=False,error='No assigned bus'),400
    stamp=now(); c.execute('INSERT INTO maintenance_reports(bus_id,driver_id,issue,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',(b['id'],u['id'],f'[{kind}] {issue}','REPORTED',stamp,stamp)); c.execute('INSERT INTO maintenance(bus_id,issue,status,created_at) VALUES(?,?,?,?)',(b['id'],f'[{kind}] {issue}','REPORTED',stamp))
    audit_notification(kind.title(),f'{b["number"]}: {issue}','admin',kind=kind,bus_id=b['id'],c=c); c.commit(); c.close();
    if kind=='EMERGENCY': emit_event('emergency',{'bus_id':b['id'],'message':issue})
    return jsonify(ok=True)

@app.get('/api/favorites')
@auth(['student'])
def favorites_get():
    c=db(); rows=c.execute('SELECT f.*,b.number bus_number,r.code route_code,r.name route_name FROM favorites f LEFT JOIN buses b ON b.id=f.bus_id LEFT JOIN routes r ON r.id=f.route_id WHERE f.user_id=? ORDER BY f.id DESC',(current_user()['id'],)).fetchall(); c.close(); return jsonify(ok=True,items=[dict(x) for x in rows])

@app.post('/api/favorites')
@auth(['student'])
def favorites_add():
    d=request.get_json() or {}; bid=d.get('bus_id'); rid=d.get('route_id')
    if not bid and not rid:return jsonify(ok=False,error='bus_id or route_id required'),400
    c=db();
    try:c.execute('INSERT INTO favorites(user_id,bus_id,route_id,created_at) VALUES(?,?,?,?)',(current_user()['id'],int(bid) if bid else None,int(rid) if rid else None,now())); c.commit()
    except sqlite3.IntegrityError: c.rollback()
    c.close(); return jsonify(ok=True)

@app.delete('/api/favorites/<int:favorite_id>')
@auth(['student'])
def favorites_delete(favorite_id):
    c=db(); c.execute('DELETE FROM favorites WHERE id=? AND user_id=?',(favorite_id,current_user()['id'])); c.commit(); c.close(); return jsonify(ok=True)

@app.get('/api/gps/history/<int:bus_id>')
@auth(['admin','driver','student'])
def gps_history(bus_id):
    u=current_user(); c=db()
    if u['role']=='driver':
        b=assigned_bus_for_driver(c,u['id']);
        if not b or b['id']!=bus_id:c.close();return jsonify(ok=False,error='Access denied'),403
    rows=c.execute('SELECT lat,lon,speed,heading,accuracy,recorded_at FROM gps_locations WHERE bus_id=? ORDER BY id DESC LIMIT 200',(bus_id,)).fetchall(); c.close(); return jsonify(ok=True,locations=[dict(x) for x in rows])

@app.post('/api/admin/users')
@auth(['admin'])
def admin_user_create():
    d=request.get_json() or {}; name=str(d.get('name','')).strip(); email=str(d.get('email','')).strip().lower(); password=str(d.get('password','')); role=str(d.get('role','student')).lower(); phone=str(d.get('phone','')).strip()
    if not name or '@' not in email or len(password)<8 or role not in ('student','driver','admin','transport_manager','security'): return jsonify(ok=False,error='Valid name, email, password and role required'),400
    c=db();
    try:
        n=c.execute('SELECT COUNT(*) n FROM users WHERE role=?',(role,)).fetchone()['n']+1; prefix={'student':'JOY-ST','driver':'DRV','admin':'ADM','transport_manager':'TM','security':'SEC'}[role]; uid=f'{prefix}-{datetime.now().year}-{n:04d}'
        c.execute('INSERT INTO users(name,email,password,role,uid,phone,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(name,email,generate_password_hash(password),role,uid,phone,1,now(),now())); uid_id=c.execute('SELECT last_insert_rowid() id').fetchone()['id']
        if role=='driver': c.execute('INSERT INTO drivers(user_id,phone,created_at) VALUES(?,?,?)',(uid_id,phone,now()))
        if role=='student': c.execute('INSERT INTO students(user_id,created_at) VALUES(?,?)',(uid_id,now()))
        c.commit()
    except sqlite3.IntegrityError: c.rollback();c.close();return jsonify(ok=False,error='Email already exists'),400
    c.close();return jsonify(ok=True,uid=uid)

@app.post('/api/admin/buses')
@auth(['admin'])
def admin_bus_create():
    d=request.get_json() or {}; number=str(d.get('number','')).strip().upper(); route_id=d.get('route_id');
    try: cap=max(1,min(200,int(d.get('capacity',45))))
    except: return jsonify(ok=False,error='Invalid capacity'),400
    if not number or not route_id:return jsonify(ok=False,error='Bus number and route are required'),400
    c=db(); r=c.execute('SELECT * FROM routes WHERE id=?',(int(route_id),)).fetchone()
    if not r:c.close();return jsonify(ok=False,error='Route not found'),404
    try:c.execute('INSERT INTO buses(number,route_name,route_id,status,capacity,simulated,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(number,r['name'],r['id'],'STOPPED',cap,1,1,now(),now()));c.commit()
    except sqlite3.IntegrityError:c.rollback();c.close();return jsonify(ok=False,error='Bus number already exists'),400
    c.close();return jsonify(ok=True)

@app.post('/api/admin/routes')
@auth(['admin'])
def admin_route_create():
    d=request.get_json() or {}; code=str(d.get('code','')).strip().upper(); name=str(d.get('name','')).strip()
    if not code or not name:return jsonify(ok=False,error='Route code and name are required'),400
    c=db();
    try:c.execute('INSERT INTO routes(code,name,created_at) VALUES(?,?,?)',(code,name,now()));c.commit()
    except sqlite3.IntegrityError:c.rollback();c.close();return jsonify(ok=False,error='Route code already exists'),400
    c.close();return jsonify(ok=True)

@app.post('/api/admin/stops')
@auth(['admin'])
def admin_stop_create():
    d=request.get_json() or {}; name=str(d.get('name','')).strip()
    try: rid=int(d['route_id']); order=int(d.get('stop_order',0)); lat=float(d.get('lat',CAMPUS['lat'])); lon=float(d.get('lon',CAMPUS['lon']))
    except (KeyError,TypeError,ValueError):return jsonify(ok=False,error='Valid route, stop order and coordinates required'),400
    if not name:return jsonify(ok=False,error='Stop name required'),400
    c=db();
    try:c.execute('INSERT INTO stops(route_id,name,stop_order,lat,lon) VALUES(?,?,?,?,?)',(rid,name,order,lat,lon));c.commit()
    except sqlite3.IntegrityError:c.rollback();c.close();return jsonify(ok=False,error='Stop order already exists for this route'),400
    c.close();return jsonify(ok=True)

@app.get('/api/admin/overview')
@auth(['admin','transport_manager','security'])
def admin_overview():
    c=db(); cutoff=time.time()-GPS_TIMEOUT_SECONDS
    active=c.execute("SELECT COUNT(*) n FROM buses WHERE enabled=1 AND status='RUNNING'").fetchone()['n']; live=c.execute('SELECT COUNT(*) n FROM buses WHERE enabled=1 AND last_gps IS NOT NULL AND last_gps>=?',(cutoff,)).fetchone()['n']; drivers=c.execute("SELECT COUNT(*) n FROM users WHERE role='driver' AND active=1").fetchone()['n']; trips=c.execute("SELECT COUNT(*) n FROM trips WHERE status='ACTIVE'").fetchone()['n']; emergencies=c.execute("SELECT COUNT(*) n FROM emergency_alerts WHERE status!='RESOLVED'").fetchone()['n']; complaints=c.execute("SELECT COUNT(*) n FROM complaints WHERE status NOT IN ('RESOLVED','REJECTED')").fetchone()['n']; maintenance=c.execute("SELECT COUNT(*) n FROM maintenance_reports WHERE status NOT IN ('RESOLVED','GOOD')").fetchone()['n']; c.close(); return jsonify(ok=True,active_buses=active,live_buses=live,drivers=drivers,active_trips=trips,emergency_alerts=emergencies,complaints=complaints,maintenance=maintenance,gps_timeout=GPS_TIMEOUT_SECONDS)

@app.post('/api/admin/assignments')
@auth(['admin'])
def admin_assign():
    d=request.get_json() or {}
    try: driver_id=int(d['driver_id']); bus_id=int(d['bus_id']); route_id=int(d['route_id']) if d.get('route_id') else None
    except (KeyError,TypeError,ValueError): return jsonify(ok=False,error='driver_id, bus_id and route_id are required'),400
    c=db(); du=c.execute('SELECT id FROM drivers WHERE id=?',(driver_id,)).fetchone(); b=c.execute('SELECT id FROM buses WHERE id=?',(bus_id,)).fetchone()
    if not du or not b:c.close();return jsonify(ok=False,error='Driver or bus not found'),404
    c.execute('UPDATE driver_bus_assignments SET active=0,ends_at=? WHERE (bus_id=? OR driver_id=?) AND active=1',(now(),bus_id,driver_id)); c.execute('UPDATE buses SET driver_id=NULL WHERE driver_id=(SELECT user_id FROM drivers WHERE id=?) AND id<>?',(driver_id,bus_id)); c.execute('INSERT INTO driver_bus_assignments(driver_id,bus_id,route_id,starts_at,active) VALUES(?,?,?,?,1)',(driver_id,bus_id,route_id,now())); user=c.execute('SELECT user_id FROM drivers WHERE id=?',(driver_id,)).fetchone(); c.execute('UPDATE buses SET driver_id=?,route_id=COALESCE(?,route_id),updated_at=? WHERE id=?',(user['user_id'],route_id,now(),bus_id)); c.commit(); c.close(); return jsonify(ok=True)

@app.patch('/api/admin/users/<int:user_id>')
@auth(['admin'])
def admin_user_update(user_id):
    d=request.get_json() or {}; active=1 if bool(d.get('active',True)) else 0
    c=db(); r=c.execute('SELECT id FROM users WHERE id=?',(user_id,)).fetchone()
    if not r:c.close();return jsonify(ok=False,error='User not found'),404
    c.execute('UPDATE users SET active=?,updated_at=? WHERE id=?',(active,now(),user_id)); c.commit(); c.close(); return jsonify(ok=True)

@app.patch('/api/admin/buses/<int:bus_id>')
@auth(['admin'])
def admin_bus_update(bus_id):
    d=request.get_json() or {}; c=db(); r=c.execute('SELECT * FROM buses WHERE id=?',(bus_id,)).fetchone()
    if not r:c.close();return jsonify(ok=False,error='Bus not found'),404
    if 'enabled' in d:c.execute('UPDATE buses SET enabled=?,updated_at=? WHERE id=?',(1 if d['enabled'] else 0,now(),bus_id))
    if 'capacity' in d:
        try:cap=max(1,min(200,int(d['capacity'])))
        except: c.close();return jsonify(ok=False,error='Invalid capacity'),400
        c.execute('UPDATE buses SET capacity=?,updated_at=? WHERE id=?',(cap,now(),bus_id))
    c.commit();c.close();return jsonify(ok=True)

@app.get('/api/admin/system')
@auth(['admin'])
def admin_system():
    c=db()
    users=c.execute("SELECT role,COUNT(*) n FROM users GROUP BY role").fetchall()
    buses=c.execute("SELECT status,COUNT(*) n FROM buses GROUP BY status").fetchall()
    active_trips=c.execute("SELECT COUNT(*) n FROM trips WHERE status='ACTIVE'").fetchone()['n']
    pending=c.execute("SELECT COUNT(*) n FROM complaints WHERE status!='RESOLVED'").fetchone()['n']
    emergencies=c.execute("SELECT COUNT(*) n FROM emergency_alerts WHERE status!='RESOLVED'").fetchone()['n']
    c.close()
    return jsonify(ok=True,users=[dict(x) for x in users],buses=[dict(x) for x in buses],active_trips=active_trips,pending_complaints=pending,open_emergencies=emergencies,server_time=now())

@app.get('/api/admin')
@auth(['admin','transport_manager','security'])
def admin_data():
    c=db()
    fleet=[bus_payload(r) for r in c.execute('SELECT * FROM buses ORDER BY id').fetchall()]
    users=[dict(r) for r in c.execute('SELECT id,name,email,role,uid,phone FROM users ORDER BY id').fetchall()]
    emergencies=[dict(r) for r in c.execute('SELECT e.*,u.name user_name,b.number bus_number FROM emergencies e LEFT JOIN users u ON u.id=e.user_id LEFT JOIN buses b ON b.id=e.bus_id ORDER BY e.id DESC LIMIT 50').fetchall()]
    complaints=[dict(r) for r in c.execute('SELECT c.*,u.name user_name,b.number bus_number FROM complaints c LEFT JOIN users u ON u.id=c.user_id LEFT JOIN buses b ON b.id=c.bus_id ORDER BY c.id DESC LIMIT 50').fetchall()]
    maintenance=[dict(r) for r in c.execute('SELECT m.*,b.number bus_number FROM maintenance m LEFT JOIN buses b ON b.id=m.bus_id ORDER BY m.id DESC LIMIT 50').fetchall()]
    attendance=[dict(r) for r in c.execute('SELECT a.*,u.name user_name,u.uid,b.number bus_number FROM attendance a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN buses b ON b.id=a.bus_id ORDER BY a.id DESC LIMIT 50').fetchall()]
    routes=[dict(r) for r in c.execute('SELECT * FROM routes ORDER BY code').fetchall()]; stops=[dict(r) for r in c.execute('SELECT s.*,r.code route_code FROM stops s JOIN routes r ON r.id=s.route_id ORDER BY r.code,s.stop_order').fetchall()]; drivers=[dict(r) for r in c.execute('SELECT d.*,u.name,u.email,u.uid,u.active FROM drivers d JOIN users u ON u.id=d.user_id ORDER BY d.id').fetchall()]; assignments=[dict(r) for r in c.execute('SELECT a.*,u.name driver_name,b.number bus_number,r.name route_name FROM driver_bus_assignments a JOIN drivers d ON d.id=a.driver_id JOIN users u ON u.id=d.user_id JOIN buses b ON b.id=a.bus_id LEFT JOIN routes r ON r.id=a.route_id WHERE a.active=1 ORDER BY a.id DESC').fetchall()]; c.close(); return jsonify(ok=True,fleet=fleet,users=users,drivers=drivers,assignments=assignments,routes=routes,stops=stops,emergencies=emergencies,complaints=complaints,maintenance=maintenance,attendance=attendance)

# Initialize on import as well as when run directly, so WSGI/Gunicorn deployments are ready.
init_db()

PAGE = ''



@app.get('/')
def home(): return render_template('index.html')

if __name__=='__main__':
    init_db()
    print('='*60)
    print('JOY UNIVERSITY BUS TRACKING - LIVE ROAD MAP + SMOOTH BUS MOVEMENT')
    print('Open: http://127.0.0.1:5000')
    print('Student: student@joyuniversity.edu / Student@123')
    print('Driver:  driver@joyuniversity.edu / Driver@123')
    print('Admin:   admin@joyuniversity.edu / Admin@123')
    print('='*60)
    if socketio: socketio.run(app,host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=False,allow_unsafe_werkzeug=True)
    else: app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=False)
