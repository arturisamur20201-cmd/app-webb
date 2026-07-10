import json
import os
from datetime import datetime
import random
from urllib import error as urllib_error, parse as urllib_parse, request as urllib_request

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from markupsafe import Markup
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from flask_migrate import Migrate

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'clave_secreta_backlog_dev'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SITE_NAME'] = 'To-Play List'


basedir = os.path.abspath(os.path.dirname(__file__))

def resolve_database_uri():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    primary_db = os.path.join(basedir, 'backlog_v2.db')
    legacy_db = os.path.join(basedir, 'backlog.db')
    if os.path.exists(primary_db):
        return 'sqlite:///' + primary_db
    if os.path.exists(legacy_db):
        return 'sqlite:///' + legacy_db
    return 'sqlite:///' + primary_db

app.config['SQLALCHEMY_DATABASE_URI'] = resolve_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, inicia sesión para acceder.'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Game(db.Model):
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default='sin jugar')
    rating = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    progress = db.Column(db.Integer, default=0)
    emoji = db.Column(db.String(4), nullable=True)
    steam_app_id = db.Column(db.String(50), nullable=True)
    steam_name = db.Column(db.String(200), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)

class Achievement(db.Model):
    __tablename__ = 'achievements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.Integer, default=3)
    unlocked = db.Column(db.Boolean, default=False)
    source = db.Column(db.String(50), default='manual')
    steam_api_name = db.Column(db.String(150), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey('games.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game = db.relationship('Game', backref=db.backref('achievements', cascade='all, delete-orphan'))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_site_name():
    return dict(site_name=app.config.get('SITE_NAME', 'Mi Backlog'))


def ensure_schema():
    with db.engine.connect() as conn:
        games_columns = [row[1] for row in conn.execute(text("PRAGMA table_info(games)")).fetchall()]
        if 'progress' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN progress INTEGER DEFAULT 0"))
        if 'emoji' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN emoji TEXT"))
        if 'steam_app_id' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN steam_app_id TEXT"))
        if 'steam_name' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN steam_name TEXT"))
        if 'image_url' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN image_url TEXT"))
        # Optional analytics columns
        if 'hours' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN hours REAL DEFAULT 0"))
        if 'genre' not in games_columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN genre TEXT"))

DEFAULT_RECOMMENDED_GAMES = [
    {
        'title': 'Hades II',
        'platform': 'PC',
        'steam_app_id': '1145350',
        'note': 'La secuela del rey de los roguelites, ahora controlando a Melinoë con nueva magia.',
    },
    {
        'title': 'Dead Cells',
        'platform': 'PC / PS4',
        'steam_app_id': '588650',
        'note': 'Un metroidvania roguelite frenético con un combate absurdamente pulido.',
    },
    {
        'title': 'The Binding of Isaac: Rebirth',
        'platform': 'PC / PS4',
        'steam_app_id': '250900',
        'note': 'El clásico indiscutible de la generación procedimental y las sinergias locas.',
    },
    {
        'title': 'Enter the Gungeon',
        'platform': 'PC / PS4',
        'steam_app_id': '311690',
        'note': 'Un bullet hell roguelike adictivo lleno de armas absurdas y referencias pop.',
    },
    {
        'title': 'Slay the Spire',
        'platform': 'PC / PS4',
        'steam_app_id': '646570',
        'note': 'El roguelike de construcción de mazos definitivo. Adictivo a más no poder.',
    },
    {
        'title': 'Risk of Rain 2',
        'platform': 'PC / PS4',
        'steam_app_id': '632360',
        'note': 'Un roguelike en 3D caótico donde la dificultad sube con el reloj.',
    },
    {
        'title': 'Vampire Survivors',
        'platform': 'PC',
        'steam_app_id': '1794680',
        'note': 'El juego de "bullet heaven" que puso de moda sobrevivir a hordas con ataques automáticos.',
    },
    {
        'title': 'Marvel\'s Spider-Man 2',
        'platform': 'PS5 / PC',
        'steam_app_id': '2940250',
        'note': 'La espectacular continuación de la historia de Peter y Miles con el traje de simbiote.',
    },
    {
        'title': 'God of War Ragnarök',
        'platform': 'PS4 / PC',
        'steam_app_id': '2322010',
        'note': 'El épico cierre de la saga nórdica de Kratos y Atreus con un combate brutal.',
    },
    {
        'title': 'Elden Ring',
        'platform': 'PC / PS4',
        'steam_app_id': '1245620',
        'note': 'La obra maestra de FromSoftware que redefine lo que debe ser un mundo abierto.',
    },
    {
        'title': 'Cyberpunk 2077',
        'platform': 'PC',
        'steam_app_id': '1091500',
        'note': 'Un RPG de acción brutal en Night City que brilla con Lossless Scaling o FSR.',
    },
    {
        'title': 'Red Dead Redemption 2',
        'platform': 'PC / PS4',
        'steam_app_id': '1174180',
        'note': 'Uno de los mundos abiertos más inmersivos y detallados jamás creados.',
    },
    {
        'title': 'Grand Theft Auto V',
        'platform': 'PC / PS4',
        'steam_app_id': '271590',
        'note': 'El titán de Rockstar que nunca muere. Campaña increíble y un online eterno.',
    },
    {
        'title': 'Ghost of Tsushima DIRECTOR\'S CUT',
        'platform': 'PS4 / PC',
        'steam_app_id': '2215430',
        'note': 'Combates de samuráis perfectos y un apartado artístico que te deja loco.',
    },
    {
        'title': 'Horizon Forbidden West',
        'platform': 'PS4 / PC',
        'steam_app_id': '2420110',
        'note': 'Aloy explora el Oeste Prohibido enfrentando nuevas y colosales máquinas mecánicas.',
    },
    {
        'title': 'The Witcher 3: Wild Hunt',
        'platform': 'PC / PS4',
        'steam_app_id': '292030',
        'note': 'Una de las mejores narrativas en los videojuegos de rol de la historia.',
    },
    {
        'title': 'Hitman World of Assassination',
        'platform': 'PC / PS4',
        'steam_app_id': '1659040',
        'note': 'El simulador de asesinatos definitivo con mapas gigantescos que son puzles interactivos.',
    },
    {
        'title': 'Metal Gear Solid V: The Phantom Pain',
        'platform': 'PC / PS4',
        'steam_app_id': '287700',
        'note': 'Jugabilidad de sigilo perfecta en mundo abierto cortesía de Hideo Kojima.',
    },
    {
        'title': 'Dishonored 2',
        'platform': 'PC / PS4',
        'steam_app_id': '403640',
        'note': 'Infiltración en primera persona con un diseño de niveles brillante y super creativo.',
    },
    {
        'title': 'EA Sports FC 24',
        'platform': 'PC / PS4',
        'steam_app_id': '2195250',
        'note': 'La evolución de FIFA con Ultimate Team y el modo carrera para armar tu plantilla ideal.',
    },
    {
        'title': 'Forza Horizon 5',
        'platform': 'PC',
        'steam_app_id': '1551360',
        'note': 'El rey de los arcades de conducción en un mapa brutal inspirado en México.',
    },
    {
        'title': 'Assetto Corsa Competizione',
        'platform': 'PC / PS4',
        'steam_app_id': '805550',
        'note': 'Simulador de carreras serio enfocado en la categoría GT con físicas brutales.',
    },
    {
        'title': 'Rocket League',
        'platform': 'PC / PS4',
        'steam_app_id': '252950',
        'note': 'Fútbol con carros propulsados por cohetes. Rápido, competitivo y gratis.',
    },
    {
        'title': 'Hollow Knight',
        'platform': 'PC / PS4',
        'steam_app_id': '367520',
        'note': 'El pico más alto de los metroidvania independientes. Arte, música y reto top.',
    },
    {
        'title': 'Celeste',
        'platform': 'PC / PS4',
        'steam_app_id': '504230',
        'note': 'Un plataformas de precisión ultra pulido con una hermosa historia sobre superación.',
    },
    {
        'title': 'Outer Wilds',
        'platform': 'PC / PS4',
        'steam_app_id': '753640',
        'note': 'Una aventura de misterio espacial basada en la curiosidad y bucles temporales.',
    },
    {
        'title': 'Stardew Valley',
        'platform': 'PC / PS4',
        'steam_app_id': '413150',
        'note': 'El simulador de granja e interacción social definitivo. Paz mental hecha juego.',
    },
    {
        'title': 'Terraria',
        'platform': 'PC / PS4',
        'steam_app_id': '105600',
        'note': 'Aventura sandbox en 2D con un sistema de progresión y jefes brutal.',
    },
    {
        'title': 'Shovel Knight: Treasure Trove',
        'platform': 'PC / PS4',
        'steam_app_id': '250760',
        'note': 'Una carta de amor a los juegos clásicos de 8 bits con mecánicas modernas.',
    },
    {
        'title': 'Cuphead',
        'platform': 'PC / PS4',
        'steam_app_id': '268910',
        'note': 'Un juego de jefes frenético con un estilo de animación de los años 30 dibujado a mano.',
    },
    {
        'title': 'Katana ZERO',
        'platform': 'PC',
        'steam_app_id': '460950',
        'note': 'Acción neo-noir en 2D donde mueres de un golpe y manipulas el tiempo.',
    },
    {
        'title': 'Hotline Miami',
        'platform': 'PC / PS4',
        'steam_app_id': '219150',
        'note': 'Acción cenital salvaje con una banda sonora synthwave espectacular.',
    },
    {
        'title': 'Ori and the Will of the Wisps',
        'platform': 'PC',
        'steam_app_id': '1057090',
        'note': 'Un metroidvania visualmente precioso con una fluidez de movimiento increíble.',
    },
    {
        'title': 'Disco Elysium - The Final Cut',
        'platform': 'PC / PS4',
        'steam_app_id': '632470',
        'note': 'Un RPG detectivesco donde tus habilidades definen la salud mental de tu personaje.',
    },
    {
        'title': 'Subnautica',
        'platform': 'PC / PS4',
        'steam_app_id': '264710',
        'note': 'Supervivencia y exploración en un océano alienígena hermoso... y terrorífico.',
    },
    {
        'title': 'It Takes Two',
        'platform': 'PC / PS4',
        'steam_app_id': '1426210',
        'note': 'El mejor juego cooperativo exclusivo para dos personas. Pura creatividad.',
    },
    {
        'title': 'Helldivers 2',
        'platform': 'PC / PS5',
        'steam_app_id': '553850',
        'note': 'Acción cooperativa caótica repartiendo democracia intergaláctica con amigos.',
    },
    {
        'title': 'Lethal Company',
        'platform': 'PC',
        'steam_app_id': '1966720',
        'note': 'Terror cooperativo lo-fi que genera situaciones absurdamente cómicas con chat de voz de proximidad.',
    },
    {
        'title': 'Monster Hunter: World',
        'platform': 'PC / PS4',
        'steam_app_id': '582010',
        'note': 'Cazar monstruos gigantescos con armas colosales, solo o con panas.',
    },
    {
        'title': 'Overcooked! All You Can Eat',
        'platform': 'PC / PS4',
        'steam_app_id': '1243830',
        'note': 'El simulador de cocina que pone a prueba tus amistades y tu manejo del caos.',
    },
    {
        'title': 'Resident Evil 4 (Remake)',
        'platform': 'PC / PS4',
        'steam_app_id': '2050650',
        'note': 'Una reimaginarización perfecta del clásico de acción y survival horror.',
    },
    {
        'title': 'Resident Evil 7: Biohazard',
        'platform': 'PC / PS4',
        'steam_app_id': '418370',
        'note': 'El regreso al terror puro en primera persona dentro de una casa pantanosa y tétrica.',
    },
    {
        'title': 'Outlast',
        'platform': 'PC / PS4',
        'steam_app_id': '238320',
        'note': 'Terror psicológico puro en un manicomio donde tu única defensa es correr y grabar.',
    },
    {
        'title': 'Dead Space (Remake)',
        'platform': 'PC',
        'steam_app_id': '1693980',
        'note': 'Terror de ciencia ficción claustrofóbico con un desmembramiento táctico impecable.',
    },
    {
        'title': 'Alan Wake 2',
        'platform': 'PC',
        'steam_app_id': '0',
        'note': 'Survival horror psicológico con una narrativa densa y gráficos fotorrealistas.',
    },
    {
        'title': 'Sekiro: Shadows Die Twice',
        'platform': 'PC / PS4',
        'steam_app_id': '814380',
        'note': 'El mejor sistema de parries y combate de katanas del mundo de los videojuegos.',
    },
    {
        'title': 'Dark Souls III',
        'platform': 'PC / PS4',
        'steam_app_id': '374320',
        'note': 'El cierre perfecto de la trilogía original de FromSoftware. Jefes memorables.',
    },
    {
        'title': 'Lies of P',
        'platform': 'PC / PS4',
        'steam_app_id': '1627720',
        'note': 'Un espectacular soulslike inspirado en Pinocho con una ambientación victoriana genial.',
    },
    {
        'title': 'Devil May Cry 5',
        'platform': 'PC / PS4',
        'steam_app_id': '601150',
        'note': 'Acción hack and slash pura con combos infinitos llenos de estilo.',
    },
    {
        'title': 'Monster Hunter Wilds',
        'platform': 'PC',
        'steam_app_id': '2246340',
        'note': 'La nueva frontera de la caza de monstruos con ecosistemas vivos masivos.',
    },
]

NINTENDO_FALLBACK_GAMES = [
    {'title': 'The Legend of Zelda: Breath of the Wild', 'platform': 'Nintendo Switch'},
    {'title': 'Super Mario Odyssey', 'platform': 'Nintendo Switch'},
    {'title': 'Mario Kart 8 Deluxe', 'platform': 'Nintendo Switch'},
    {'title': 'Animal Crossing: New Horizons', 'platform': 'Nintendo Switch'},
    {'title': 'Splatoon 2', 'platform': 'Nintendo Switch'},
    {'title': 'Metroid Dread', 'platform': 'Nintendo Switch'},
    {'title': 'Luigi\'s Mansion 3', 'platform': 'Nintendo Switch'},
    {'title': 'Super Smash Bros. Ultimate', 'platform': 'Nintendo Switch'},
    {'title': 'The Legend of Zelda: Skyward Sword', 'platform': 'Wii'},
    {'title': 'Super Mario Galaxy', 'platform': 'Wii'},
    {'title': 'Mario Kart Wii', 'platform': 'Wii'},
    {'title': 'Donkey Kong Country Returns', 'platform': 'Wii'},
    {'title': 'Metroid Prime 3: Corruption', 'platform': 'Wii'},
    {'title': 'The Legend of Zelda: Phantom Hourglass', 'platform': 'Nintendo DS'},
    {'title': 'Pokémon Diamond', 'platform': 'Nintendo DS'},
    {'title': 'Pokémon Pearl', 'platform': 'Nintendo DS'},
    {'title': 'Pokémon Black', 'platform': 'Nintendo DS'},
    {'title': 'Pokémon White', 'platform': 'Nintendo DS'},
    {'title': 'Mario Kart DS', 'platform': 'Nintendo DS'},
    {'title': 'New Super Mario Bros.', 'platform': 'Nintendo DS'},
    {'title': 'Kirby: Canvas Curse', 'platform': 'Nintendo DS'},
    {'title': 'Yoshi\'s Island DS', 'platform': 'Nintendo DS'},
]


def resolve_steam_image(appid, title=None):
    if not appid:
        return ''
    details = fetch_steam_app_details(appid)
    image_url = details.get('header_image') or details.get('background') or ''
    if image_url:
        return image_url
    if title:
        search_results = search_steam_games(title, limit=1)
        if search_results:
            fallback_appid = search_results[0].get('appid')
            if fallback_appid:
                details = fetch_steam_app_details(fallback_appid)
                image_url = details.get('header_image') or details.get('background') or ''
                if image_url:
                    return image_url
    return f'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg'


def get_session_recommendation():
    rec = session.get('recommended_game')
    if rec:
        return rec
    selected = random.choice(DEFAULT_RECOMMENDED_GAMES)
    image_url = resolve_steam_image(selected.get('steam_app_id'), selected.get('title'))
    rec = {
        'title': selected['title'],
        'platform': selected['platform'],
        'steam_app_id': selected['steam_app_id'],
        'note': selected['note'],
        'image_url': image_url,
    }
    session['recommended_game'] = rec
    return rec


def reset_session_recommendation():
    session.pop('recommended_game', None)


def build_steam_suggestion_payload(payload):
    items = payload.get('items', []) if isinstance(payload, dict) else []
    suggestions = []
    for item in items:
        if not isinstance(item, dict):
            continue
        appid = item.get('id')
        name = (item.get('name') or '').strip()
        if not appid or not name:
            continue
        suggestions.append({
            'appid': int(appid),
            'name': name,
            'price': item.get('price') or '',
            'image': item.get('tiny_image') or '',
            'platform': 'PC',
            'source': 'steam',
        })
    return suggestions[:6]


def get_rawg_api_key():
    return os.environ.get('RAWG_API_KEY') or os.environ.get('RAWG_KEY')


def build_rawg_suggestion_payload(payload):
    results = payload.get('results', []) if isinstance(payload, dict) else []
    suggestions = []
    for item in results:
        if not isinstance(item, dict):
            continue
        appid = item.get('id')
        name = (item.get('name') or '').strip()
        if not appid or not name:
            continue
        platforms = []
        for p in item.get('platforms', []) or []:
            if not isinstance(p, dict):
                continue
            platform_name = (p.get('platform', {}) or {}).get('name')
            if platform_name:
                platforms.append(platform_name)
        suggestions.append({
            'appid': int(appid),
            'name': name,
            'price': '',
            'image': item.get('background_image') or '',
            'platform': ' / '.join(platforms[:3]),
            'source': 'rawg',
        })
    return suggestions[:6]


def merge_game_suggestions(steam_results, rawg_results, local_results=None, limit=6):
    merged = []
    seen = set()
    for item in (steam_results or []) + (rawg_results or []) + (local_results or []):
        name = (item.get('name') or '').strip().lower()
        if not name or name in seen:
            continue
        merged.append(item)
        seen.add(name)
        if len(merged) >= limit:
            break
    return merged


def search_local_nintendo_games(query, limit=6):
    term = (query or '').strip().lower()
    if len(term) < 2:
        return []
    suggestions = []
    for item in NINTENDO_FALLBACK_GAMES:
        if term in item['title'].lower():
            suggestions.append({
                'appid': None,
                'name': item['title'],
                'price': '',
                'image': '',
                'platform': item['platform'],
                'source': 'local',
            })
            if len(suggestions) >= limit:
                break
    return suggestions


def build_achievement_payloads(schema_payload, player_payload):
    achievements = []
    schema_items = []
    if isinstance(schema_payload, dict):
        schema_items = schema_payload.get('game', {}).get('availableGameStats', {}).get('achievements', [])
    player_items = []
    if isinstance(player_payload, dict):
        player_items = player_payload.get('playerstats', {}).get('achievements', [])

    player_lookup = {entry.get('apiname'): entry for entry in player_items if isinstance(entry, dict) and entry.get('apiname')}

    for item in schema_items:
        if not isinstance(item, dict):
            continue
        api_name = (item.get('name') or '').strip()
        display_name = item.get('displayName') or api_name
        description = item.get('description') or ''
        player_entry = player_lookup.get(api_name, {})
        achievements.append({
            'name': api_name,
            'display_name': display_name,
            'description': description,
            'unlocked': bool(player_entry.get('achieved')),
        })
    return achievements


def search_rawg_games(query, limit=6):
    api_key = get_rawg_api_key()
    term = (query or '').strip()
    if not api_key or len(term) < 2:
        return []
    encoded_term = urllib_parse.quote(term)
    url = f'https://api.rawg.io/api/games?search={encoded_term}&page_size={limit}&key={urllib_parse.quote(api_key)}'
    req = urllib_request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            payload = json.load(response)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError):
        return []
    return build_rawg_suggestion_payload(payload)


def search_steam_games(query, limit=6):
    term = (query or '').strip()
    if len(term) < 2:
        return []
    encoded_term = urllib_parse.quote(term)
    url = f'https://store.steampowered.com/api/storesearch/?term={encoded_term}&l=spanish&cc=es&limit={limit}'
    req = urllib_request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            payload = json.load(response)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError):
        return []
    return build_steam_suggestion_payload(payload)


def fetch_steam_app_details(appid):
    if not appid:
        return {}
    url = f'https://store.steampowered.com/api/appdetails?appids={appid}&l=spanish&cc=es&filters=basic,achievements'
    req = urllib_request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib_request.urlopen(req, timeout=8) as response:
            payload = json.load(response)
    except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, ValueError):
        return {}
    data = payload.get(str(appid), {})
    if not data.get('success'):
        return {}
    return data.get('data', {})


def import_steam_achievements_for_game(game):
    if not game.steam_app_id:
        return []

    data = fetch_steam_app_details(game.steam_app_id)
    achievements_data = data.get('achievements') or {}
    achievements_list = []
    total = 0
    if isinstance(achievements_data, dict):
        achievements_list = achievements_data.get('achievements') or achievements_data.get('highlighted') or []
        total = achievements_data.get('total') or 0

    existing_names = {
        entry.steam_api_name for entry in Achievement.query.filter_by(game_id=game.id, user_id=game.user_id).all() if entry.steam_api_name
    }

    created = []
    if isinstance(achievements_list, list) and achievements_list:
        for item in achievements_list:
            if not isinstance(item, dict):
                continue
            name = (item.get('displayName') or item.get('localized_name') or item.get('name') or '').strip()
            api_name = (item.get('name') or item.get('displayName') or item.get('localized_name') or '').strip()
            description = item.get('description') or item.get('localized_name') or item.get('displayName') or 'Logro importado automáticamente desde Steam.'
            if not name or api_name in existing_names:
                continue
            achievement = Achievement(
                title=name,
                description=description,
                difficulty=3,
                unlocked=False,
                source='steam',
                steam_api_name=api_name,
                game_id=game.id,
                user_id=game.user_id,
            )
            db.session.add(achievement)
            created.append(achievement)
    elif total and total > 0:
        for index in range(1, total + 1):
            placeholder_name = f'Logro {index}'
            if placeholder_name in existing_names:
                continue
            achievement = Achievement(
                title=placeholder_name,
                description='Logro detectado gracias a los datos de Steam.',
                difficulty=3,
                unlocked=False,
                source='steam',
                steam_api_name=f'placeholder_{index}',
                game_id=game.id,
                user_id=game.user_id,
            )
            db.session.add(achievement)
            created.append(achievement)

    return created


def choose_game_emoji(title, platform):
    platform_emojis = {
        'PS3': '🎮',
        'PS4 Pro': '🕹️',
        'PS5': '🕹️',
        'Nintendo Switch': '🟢',
        'PC': '💻',
        'Móvil': '📱',
    }
    if platform in platform_emojis:
        return platform_emojis[platform]
    title_lower = (title or '').lower()
    if 'zelda' in title_lower or 'mario' in title_lower or 'pokemon' in title_lower:
        return '🪄'
    if 'war' in title_lower or 'doom' in title_lower or 'halo' in title_lower or 'call' in title_lower:
        return '⚔️'
    if 'star' in title_lower or 'space' in title_lower or 'rocket' in title_lower:
        return '🚀'
    return '🎮'

def add_recommended_games_for_user(user_id):
    recommended = [
        {
            'title': 'Hades',
            'platform': 'PC',
            'steam_app_id': '310950',
            'steam_name': 'Hades',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Órale con este roguelite de acción y narrativa.',
        },
        {
            'title': 'Stardew Valley',
            'platform': 'PC',
            'steam_app_id': '413150',
            'steam_name': 'Stardew Valley',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Un simulador de granja relajante con muchas metas.',
        },
        {
            'title': 'Hollow Knight',
            'platform': 'PC',
            'steam_app_id': '367520',
            'steam_name': 'Hollow Knight',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Explora una metrópolis subterránea y desbloquea logros.',
        },
        {
            'title': 'Celeste',
            'platform': 'PC',
            'steam_app_id': '103100',
            'steam_name': 'Celeste',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Plataformas precisas y una historia emotiva.',
        },
        {
            'title': 'Terraria',
            'platform': 'PC',
            'steam_app_id': '105600',
            'steam_name': 'Terraria',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Aventura de construcción y exploración con muchos logros.',
        }
    ]
    existing_titles = {game.title.lower() for game in Game.query.filter_by(user_id=user_id).all()}
    for game_data in recommended:
        if game_data['title'].lower() in existing_titles:
            continue
        game = Game(user_id=user_id, **game_data)
        db.session.add(game)
        db.session.flush()
        if not game.emoji:
            game.emoji = choose_game_emoji(game.title, game.platform)
        if game.steam_app_id:
            details = fetch_steam_app_details(game.steam_app_id)
            game.image_url = details.get('header_image') or details.get('background') or game.image_url
            if details and not game.steam_name:
                game.steam_name = details.get('name')
            import_steam_achievements_for_game(game)
        existing_titles.add(game_data['title'].lower())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            reset_session_recommendation()
            get_session_recommendation()
            return redirect(url_for('index'))
        flash('Usuario o contraseña incorrectos.')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    error = None
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'))
        new_user = User(username=request.form.get('username'), password=hashed_pw)
        try:
            db.session.add(new_user)
            db.session.commit()
            reset_session_recommendation()
            get_session_recommendation()
            flash('Cuenta creada con éxito. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            error = 'El usuario ya existe. Intenta con otro nombre.'
    return render_template('registro.html', error=error)

@app.route('/logout')
@login_required
def logout():
    reset_session_recommendation()
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    games = Game.query.filter_by(user_id=current_user.id).all()
    recommended_game = get_session_recommendation()
    total_games = len(games)
    return render_template('index.html', games=games, total_games=total_games, recommended_game=recommended_game)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_game():
    if request.method == 'POST':
        rating_value = request.form.get('rating')
        notes_value = request.form.get('notes')
        platform_value = request.form.get('platform')
        title_value = request.form.get('title')
        steam_app_id_value = request.form.get('steam_app_id') or None
        steam_name_value = request.form.get('steam_name') or None
        suggestion_source_value = request.form.get('suggestion_source') or None
        image_url_value = request.form.get('image_url') or None

        new_game = Game(
            title=title_value,
            platform=platform_value,
            status=request.form.get('status', 'sin jugar'),
            rating=int(rating_value) if rating_value else None,
            notes=notes_value.strip() if notes_value and notes_value.strip() else None,
            progress=int(request.form.get('progress') or 0),
            emoji=choose_game_emoji(title_value, platform_value),
            steam_app_id=steam_app_id_value,
            steam_name=steam_name_value,
            image_url=image_url_value,
            user_id=current_user.id
        )
        db.session.add(new_game)
        db.session.flush()

        if not new_game.steam_app_id and suggestion_source_value != 'rawg':
            suggestions = search_steam_games(title_value)
            if suggestions:
                new_game.steam_app_id = str(suggestions[0]['appid'])
                new_game.steam_name = suggestions[0]['name']

        if new_game.steam_app_id:
            game_details = fetch_steam_app_details(new_game.steam_app_id)
            new_game.image_url = game_details.get('header_image') or game_details.get('background') or new_game.image_url
            if game_details and not new_game.steam_name:
                new_game.steam_name = game_details.get('name')
            import_steam_achievements_for_game(new_game)
        db.session.commit()
        flash('Juego añadido correctamente. Ahora puedes revisar sus logros.', 'success')
        return redirect(url_for('achievements', game_id=new_game.id))
    return render_template('add_games.html', action='Añadir')

@app.route('/api/steam/suggestions')
@app.route('/api/game/suggestions')
@login_required
def game_suggestions():
    query = request.args.get('query', '').strip()
    steam_results = search_steam_games(query)
    rawg_results = search_rawg_games(query)
    local_results = search_local_nintendo_games(query)
    return jsonify(merge_game_suggestions(steam_results, rawg_results, local_results))

@app.route('/edit/<int:game_id>', methods=['GET', 'POST'])
@login_required
def edit_game(game_id):
    game = Game.query.get_or_404(game_id)
    if game.user_id != current_user.id:
        return "Acceso denegado", 403
        
    platforms = ['PS3', 'PS4 Pro', 'PS5', 'Nintendo Switch', 'PC', 'Móvil']
    statuses = ['sin jugar', 'Jugando', 'Completado']

    if request.method == 'POST':
        game.title = request.form.get('title')
        game.platform = request.form.get('platform')
        game.status = request.form.get('status')
        rating_value = request.form.get('rating')
        game.rating = int(rating_value) if rating_value else None
        notes_value = request.form.get('notes')
        game.notes = notes_value.strip() if notes_value and notes_value.strip() else None
        game.progress = int(request.form.get('progress') or 0)
        # optional analytics fields
        try:
            game.hours = float(request.form.get('hours') or 0)
        except Exception:
            game.hours = 0
        game.genre = request.form.get('genre') or None
        game.emoji = choose_game_emoji(game.title, game.platform)
        db.session.commit()
        return redirect(url_for('index'))
        
    return render_template('edit_games.html', action='Editar', game=game, platforms=platforms, statuses=statuses)

@app.route('/games/<int:game_id>/achievements', methods=['GET', 'POST'])
@login_required
def achievements(game_id):
    game = Game.query.get_or_404(game_id)
    if game.user_id != current_user.id:
        return 'Acceso denegado', 403

    if request.method == 'POST':
        if request.form.get('retry_import'):
            imported = import_steam_achievements_for_game(game)
            if imported:
                db.session.commit()
                flash('Importación de logros reintentada correctamente.', 'success')
            else:
                flash('No se encontraron logros automáticos en Steam para este juego.', 'warning')
            return redirect(url_for('achievements', game_id=game.id))

        title = request.form.get('title', '').strip()
        if title:
            new_achievement = Achievement(
                title=title,
                description=request.form.get('description', '').strip() or None,
                difficulty=int(request.form.get('difficulty') or 3),
                source='manual',
                game_id=game.id,
                user_id=current_user.id,
            )
            db.session.add(new_achievement)
            db.session.commit()
            flash('Logro añadido.', 'success')
        return redirect(url_for('achievements', game_id=game.id))

    if not game.achievements and game.steam_app_id:
        imported = import_steam_achievements_for_game(game)
        if imported:
            db.session.commit()

    return render_template('achievements.html', game=game, achievements=game.achievements)


@app.route('/api/steam/suggestions')
@login_required
def steam_suggestions():
    query = request.args.get('query', '').strip()
    return jsonify(search_steam_games(query))


@app.route('/delete/<int:game_id>', methods=['POST'])
@login_required
def delete_game(game_id):
    game = Game.query.get_or_404(game_id)
    if game.user_id == current_user.id:
        db.session.delete(game)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/stats')
@login_required
def stats():
    games = Game.query.filter_by(user_id=current_user.id).all()

    # Procesar datos para los gráficos
    estados = {}
    plataformas = {}
    genero_count = {}
    total_hours = 0.0

    completed_this_year = 0
    for g in games:
        estados[g.status] = estados.get(g.status, 0) + 1
        plataformas[g.platform] = plataformas.get(g.platform, 0) + 1
        try:
            if g.status == 'Completado' and g.date_added and g.date_added.year == datetime.utcnow().year:
                completed_this_year += 1
        except Exception:
            pass

        # Horas jugadas (si existe)
        try:
            total_hours += float(g.hours or 0)
        except Exception:
            pass

        # Género (puede ser cadena o lista separada por comas)
        if g.genre:
            parts = [p.strip() for p in g.genre.split(',') if p.strip()]
            for p in parts:
                genero_count[p] = genero_count.get(p, 0) + 1

    # Abandoned vs Completed
    abandoned_statuses = {'En Backlog', 'sin jugar'}
    abandoned = sum(1 for g in games if (g.status or '').strip() in abandoned_statuses)
    completed = sum(1 for g in games if (g.status or '').strip() == 'Completado')

    most_played_platform = None
    if plataformas:
        most_played_platform = max(plataformas.items(), key=lambda x: x[1])

    # Top genres
    top_genres = sorted(genero_count.items(), key=lambda x: x[1], reverse=True)
    genre_labels = [g[0] for g in top_genres]
    genre_data = [g[1] for g in top_genres]

    # Top games by hours
    games_with_hours = [(g.title, float(g.hours or 0), g.id) for g in games if (g.hours or 0) > 0]
    games_with_hours.sort(key=lambda x: x[1], reverse=True)
    top_hours = games_with_hours[:5]
    hours_labels = [g[0] for g in top_hours]
    hours_data = [g[1] for g in top_hours]

    return render_template('stats.html', 
                           estados_labels=list(estados.keys()), 
                           estados_data=list(estados.values()),
                           plat_labels=list(plataformas.keys()),
                           plat_data=list(plataformas.values()),
                           total_games=len(games),
                           completed_this_year=completed_this_year,
                           most_played_platform=most_played_platform,
                           abandoned_count=abandoned,
                           completed_count=completed,
                           total_hours=round(total_hours,1),
                           genre_labels=genre_labels,
                           genre_data=genre_data,
                           hours_labels=hours_labels,
                           hours_data=hours_data)


@app.route('/suggest')
@login_required
def suggest():
    # Select a game from user's backlog using simple weighted heuristics
    candidates = Game.query.filter(Game.user_id == current_user.id).filter(Game.status != 'Completado').all()
    if not candidates:
        flash('No hay juegos pendientes para sugerir.', 'warning')
        return redirect(url_for('index'))

    weights = []
    for g in candidates:
        w = 1.0
        status = (g.status or '').strip()
        if status == 'Jugando':
            w *= 1.6
        elif status.lower() == 'sin jugar' or status.lower() == 'en backlog':
            w *= 1.2

        try:
            prog = float(g.progress or 0) / 100.0
            w *= (1.0 - prog + 0.1)
        except Exception:
            pass

        try:
            rating = float(g.rating) if g.rating is not None else 5.0
            w *= (1.0 + (rating - 5.0) / 10.0)
        except Exception:
            pass

        weights.append(max(w, 0.01))

    chosen = random.choices(candidates, weights=weights, k=1)[0]
    flash(Markup(f'Sugerencia: <a href="{url_for("achievements", game_id=chosen.id)}">{chosen.title}</a> — ¡dale play!'), 'info')
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    # Mostrar página de perfil del usuario
    games_count = Game.query.filter_by(user_id=current_user.id).count()
    return render_template('profile.html', user=current_user, games_count=games_count)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        flash('Ajustes guardados.', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')

def seed_games():
    # Solo añadir si no hay juegos para el usuario
    if Game.query.first() is None:
        juegos_iniciales = [
            ("The Legend of Zelda: BOTW", "Nintendo Switch", "Completado", 100, 10, "Obra maestra", 120, 'Action-Adventure'),
            ("Bloodborne", "PS4 Pro", "Jugando", 45, 9, "Muy difícil", 80, 'Action-RPG'),
            ("FIFA 18", "PS3", "Jugando", 20, 7, "Clásico", 40, 'Sports'),
            ("Dead Cells", "Nintendo Switch", "En Backlog", 0, 8, "Rogue-like", 15, 'Roguelike,Metroidvania'),
            ("God of War Ragnarök", "PS5", "Completado", 100, 10, "Increíble historia", 50, 'Action-Adventure'),
            ("Elden Ring", "PC", "Jugando", 60, 9, "Mundo abierto vasto", 200, 'Action-RPG,Open World'),
            ("The Last of Us Part II", "PS4 Pro", "Completado", 100, 10, "Impactante", 90, 'Action-Adventure'),
            ("Hollow Knight", "Nintendo Switch", "En Backlog", 0, 9, "Retador", 35, 'Metroidvania,Platformer'),
            ("Cyberpunk 2077", "PC", "En Backlog", 10, 8, "Mundo inmersivo", 60, 'RPG,Open World'),
            ("Brawl Stars", "Móvil", "Jugando", 80, 7, "Adictivo", 250, 'Multiplayer')
        ]
        for titulo, plat, est, prog, rat, nota, hrs, gen in juegos_iniciales:
            db.session.add(Game(
                title=titulo,
                platform=plat,
                status=est,
                progress=prog,
                rating=rat,
                notes=nota,
                hours=hrs,
                genre=gen,
                emoji=choose_game_emoji(titulo, plat),
                user_id=1
            ))
        db.session.commit()
        

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_games() # <--- Llama aquí para cargar los 10 juegos
    app.run(debug=True, port=5000)
