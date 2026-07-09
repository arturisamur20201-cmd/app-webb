import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'backlog.db')
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


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_site_name():
    return dict(site_name=app.config.get('SITE_NAME', 'Mi Backlog'))


def ensure_schema():
    with db.engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(games)")).fetchall()]
        if 'progress' not in columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN progress INTEGER DEFAULT 0"))
        if 'emoji' not in columns:
            conn.execute(text("ALTER TABLE games ADD COLUMN emoji TEXT"))


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
            'title': 'The Legend of Zelda: Breath of the Wild',
            'platform': 'Nintendo Switch',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Aventura abierta imprescindible',
        },
        {
            'title': 'Hollow Knight',
            'platform': 'PC',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Exploración y combate profundo',
        },
        {
            'title': 'Spider-Man: Miles Morales',
            'platform': 'PS5',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Acción urbana y vuelo libre',
        },
        {
            'title': 'Stardew Valley',
            'platform': 'PC',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'Simulación relajada y granja',
        },
        {
            'title': 'Final Fantasy VII Remake',
            'platform': 'PS4 Pro',
            'status': 'sin jugar',
            'progress': 0,
            'rating': None,
            'notes': 'RPG cinematográfico moderno',
        }
    ]
    for game_data in recommended:
        db.session.add(Game(user_id=user_id, **game_data))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
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
            db.session.flush()
            add_recommended_games_for_user(new_user.id)
            db.session.commit()
            flash('Cuenta creada con éxito. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            error = 'El usuario ya existe. Intenta con otro nombre.'
    return render_template('registro.html', error=error)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    games = Game.query.filter_by(user_id=current_user.id).all()
    total_games = len(games)
    return render_template('index.html', games=games, total_games=total_games)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_game():
    if request.method == 'POST':
        rating_value = request.form.get('rating')
        notes_value = request.form.get('notes')
        platform_value = request.form.get('platform')
        title_value = request.form.get('title')
        new_game = Game(
            title=title_value,
            platform=platform_value,
            status=request.form.get('status', 'sin jugar'),
            rating=int(rating_value) if rating_value else None,
            notes=notes_value.strip() if notes_value and notes_value.strip() else None,
            progress=int(request.form.get('progress') or 0),
            emoji=choose_game_emoji(title_value, platform_value),
            user_id=current_user.id
        )
        db.session.add(new_game)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_games.html', action='Añadir')

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
        game.emoji = choose_game_emoji(game.title, game.platform)
        db.session.commit()
        return redirect(url_for('index'))
        
    return render_template('edit_games.html', action='Editar', game=game, platforms=platforms, statuses=statuses)

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
    
    completed_this_year = 0
    for g in games:
        estados[g.status] = estados.get(g.status, 0) + 1
        plataformas[g.platform] = plataformas.get(g.platform, 0) + 1
        try:
            if g.status == 'Completado' and g.date_added and g.date_added.year == datetime.utcnow().year:
                completed_this_year += 1
        except Exception:
            pass

    most_played_platform = None
    if plataformas:
        most_played_platform = max(plataformas.items(), key=lambda x: x[1])

    return render_template('stats.html', 
                           estados_labels=list(estados.keys()), 
                           estados_data=list(estados.values()),
                           plat_labels=list(plataformas.keys()),
                           plat_data=list(plataformas.values()),
                           total_games=len(games),
                           completed_this_year=completed_this_year,
                           most_played_platform=most_played_platform)


@app.route('/profile')
@login_required
def profile():
    # Mostrar página de perfil del usuario
    games_count = Game.query.filter_by(user_id=current_user.id).count()
    return render_template('profile.html', user=current_user, games_count=games_count)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Página de configuración (placeholder)
    if request.method == 'POST':
        # Aquí podrías procesar cambios de perfil o preferencias
        flash('Cambios guardados.', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')

def seed_games():
    # Solo añadir si no hay juegos para el usuario
    if Game.query.first() is None:
        juegos_iniciales = [
            ("The Legend of Zelda: BOTW", "Nintendo Switch", "Completado", 100, 10, "Obra maestra"),
            ("Bloodborne", "PS4 Pro", "Jugando", 45, 9, "Muy difícil"),
            ("FIFA 18", "PS3", "Jugando", 20, 7, "Clásico"),
            ("Dead Cells", "Nintendo Switch", "En Backlog", 0, 8, "Rogue-like"),
            ("God of War Ragnarök", "PS5", "Completado", 100, 10, "Increíble historia"),
            ("Elden Ring", "PC", "Jugando", 60, 9, "Mundo abierto vasto"),
            ("The Last of Us Part II", "PS4 Pro", "Completado", 100, 10, "Impactante"),
            ("Hollow Knight", "Nintendo Switch", "En Backlog", 0, 9, "Retador"),
            ("Cyberpunk 2077", "PC", "En Backlog", 10, 8, "Mundo inmersivo"),
            ("Brawl Stars", "Móvil", "Jugando", 80, 7, "Adictivo")
        ]
        for titulo, plat, est, prog, rat, nota in juegos_iniciales:
            db.session.add(Game(
                title=titulo,
                platform=plat,
                status=est,
                progress=prog,
                rating=rat,
                notes=nota,
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
