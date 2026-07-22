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

# Resolve database path early so app config can use it.
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

# Initialize Flask-Login manager (minimal setup)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.login_manager = login_manager

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = resolve_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize ORM and migrations
db = SQLAlchemy(app)
migrate = Migrate(app, db)


# Models (minimal fields needed by the app)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    platform = db.Column(db.String(120))
    status = db.Column(db.String(80))
    progress = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    hours = db.Column(db.Float, default=0.0)
    genre = db.Column(db.String(200), nullable=True)
    emoji = db.Column(db.String(10), nullable=True)
    steam_app_id = db.Column(db.String(50), nullable=True)
    steam_name = db.Column(db.String(250), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    achievements = db.relationship('Achievement', backref='game', lazy='dynamic')


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text)
    difficulty = db.Column(db.Integer, default=3)
    source = db.Column(db.String(50))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


# Flask-Login loader
@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None


def ensure_schema():
    """Create DB schema and a seeded user if missing."""
    db.create_all()
    try:
        if User.query.count() == 0:
            u = User(username='admin', password=generate_password_hash('admin'))
            db.session.add(u)
            db.session.commit()
    except Exception:
        db.session.rollback()

# DEFAULT_RECOMMENDED_GAMES is used by the recommendation helper below.
DEFAULT_RECOMMENDED_GAMES = []

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
    pool = DEFAULT_RECOMMENDED_GAMES or NINTENDO_FALLBACK_GAMES
    if not pool:
        return {
            'title': 'Recomendado',
            'platform': 'General',
            'steam_app_id': None,
            'note': 'No hay recomendaciones disponibles en este momento.',
            'image_url': '',
        }
    selected = random.choice(pool)
    image_url = resolve_steam_image(selected.get('steam_app_id'), selected.get('title'))
    rec = {
        'title': selected.get('title', 'Juego recomendado'),
        'platform': selected.get('platform', 'Desconocido'),
        'steam_app_id': selected.get('steam_app_id'),
        'note': selected.get('note', ''),
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


def compute_stats(games):
    """Compute aggregated stats from a list of Game objects and return a dict of values
    used by the stats view. Handles missing attributes safely.
    """
    estados = {}
    plataformas = {}
    genero_count = {}
    total_hours = 0.0
    completed_this_year = 0

    for g in games:
        status = (getattr(g, 'status', '') or '').strip()
        platform = (getattr(g, 'platform', '') or '').strip()
        estados[status] = estados.get(status, 0) + 1
        plataformas[platform] = plataformas.get(platform, 0) + 1

        try:
            date_added = getattr(g, 'date_added', None)
            if status == 'Completado' and date_added and date_added.year == datetime.utcnow().year:
                completed_this_year += 1
        except Exception:
            pass

        try:
            total_hours += float(getattr(g, 'hours', 0) or 0)
        except Exception:
            pass

        genre_val = getattr(g, 'genre', None)
        if genre_val:
            try:
                parts = [p.strip() for p in str(genre_val).split(',') if p.strip()]
                for p in parts:
                    genero_count[p] = genero_count.get(p, 0) + 1
            except Exception:
                pass

    abandoned_statuses = {'En Backlog', 'sin jugar'}
    abandoned = sum(1 for g in games if (getattr(g, 'status', '') or '').strip() in abandoned_statuses)
    completed = sum(1 for g in games if (getattr(g, 'status', '') or '').strip() == 'Completado')

    most_played_platform = None
    if plataformas:
        most_played_platform = max(plataformas.items(), key=lambda x: x[1])

    top_genres = sorted(genero_count.items(), key=lambda x: x[1], reverse=True)
    genre_labels = [g[0] for g in top_genres]
    genre_data = [g[1] for g in top_genres]

    # Top games by hours
    games_with_hours = []
    for g in games:
        try:
            h = float(getattr(g, 'hours', 0) or 0)
        except Exception:
            h = 0.0
        if h > 0:
            games_with_hours.append((getattr(g, 'title', 'Untitled'), h, getattr(g, 'id', None)))
    games_with_hours.sort(key=lambda x: x[1], reverse=True)
    top_hours = games_with_hours[:5]
    hours_labels = [g[0] for g in top_hours]
    hours_data = [g[1] for g in top_hours]

    return {
        'estados_labels': list(estados.keys()),
        'estados_data': list(estados.values()),
        'plat_labels': list(plataformas.keys()),
        'plat_data': list(plataformas.values()),
        'total_games': len(games),
        'completed_this_year': completed_this_year,
        'most_played_platform': most_played_platform,
        'abandoned_count': abandoned,
        'completed_count': completed,
        'total_hours': round(total_hours, 1),
        'genre_labels': genre_labels,
        'genre_data': genre_data,
        'hours_labels': hours_labels,
        'hours_data': hours_data,
    }


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
    stats_payload = compute_stats(games)
    return render_template('stats.html', **stats_payload)


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
