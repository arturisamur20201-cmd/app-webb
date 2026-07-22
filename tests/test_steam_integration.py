import unittest
from unittest.mock import patch

from main import (
    Achievement,
    Game,
    User,
    app,
    build_achievement_payloads,
    build_steam_suggestion_payload,
    build_rawg_suggestion_payload,
    merge_game_suggestions,
    search_local_nintendo_games,
    db,
    ensure_schema,
    generate_password_hash,
    import_steam_achievements_for_game,
)


class SteamIntegrationTests(unittest.TestCase):
    def test_build_steam_suggestion_payload_filters_invalid_items(self):
        payload = {
            "items": [
                {"id": 123, "name": "Hades", "tiny_image": "img", "price": "$"},
                {"id": 456, "name": ""},
                {"name": "No id"},
            ]
        }
        result = build_steam_suggestion_payload(payload)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Hades")
        self.assertEqual(result[0]["appid"], 123)

    def test_build_rawg_suggestion_payload_filters_invalid_items(self):
        payload = {
            "results": [
                {"id": 777, "name": "Zelda", "background_image": "img", "platforms": [{"platform": {"name": "Nintendo Switch"}}]},
                {"id": None, "name": "No id"},
                {"id": 888, "name": ""},
            ]
        }
        result = build_rawg_suggestion_payload(payload)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Zelda")
        self.assertEqual(result[0]["platform"], "Nintendo Switch")

    def test_merge_game_suggestions_deduplicates_by_name(self):
        steam = [
            {"appid": 1, "name": "Hades", "source": "steam"},
            {"appid": 2, "name": "Mario", "source": "steam"},
        ]
        rawg = [
            {"appid": 3, "name": "Mario", "source": "rawg"},
            {"appid": 4, "name": "Zelda", "source": "rawg"},
        ]
        result = merge_game_suggestions(steam, rawg)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["name"], "Hades")
        self.assertEqual(result[1]["name"], "Mario")
        self.assertEqual(result[2]["name"], "Zelda")

    def test_build_steam_suggestion_payload_uses_default_image(self):
        payload = {
            "items": [
                {"id": 123, "name": "Hades", "price": "$"},
            ]
        }
        result = build_steam_suggestion_payload(payload)
        self.assertEqual(result[0]["image"], '/static/img/logo.svg')

    def test_build_rawg_suggestion_payload_uses_default_image(self):
        payload = {
            "results": [
                {"id": 777, "name": "Zelda", "platforms": [{"platform": {"name": "Nintendo Switch"}}]},
            ]
        }
        result = build_rawg_suggestion_payload(payload)
        self.assertEqual(result[0]["image"], '/static/img/logo.svg')

    def test_search_local_nintendo_games_uses_default_image(self):
        result = search_local_nintendo_games('Zelda')
        self.assertTrue(result)
        self.assertEqual(result[0]["image"], '/static/img/logo.svg')

    def test_build_achievement_payloads_uses_schema_and_player_state(self):
        schema_payload = {
            "game": {
                "gameName": "Hades",
                "availableGameStats": {
                    "achievements": [
                        {"name": "ACH_1", "displayName": "First Escape", "description": "Escape the underworld"},
                        {"name": "ACH_2", "displayName": "Full Clear", "description": "Beat the game"},
                    ]
                },
            }
        }
        player_payload = {
            "playerstats": {
                "achievements": [
                    {"apiname": "ACH_1", "achieved": 1},
                ]
            }
        }
        result = build_achievement_payloads(schema_payload, player_payload)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]["unlocked"])
        self.assertFalse(result[1]["unlocked"])

    def test_import_steam_achievements_uses_highlighted_data(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        with app.app_context():
            db.drop_all()
            db.create_all()
            ensure_schema()
            user = User(username='tester2', password=generate_password_hash('secret'))
            db.session.add(user)
            db.session.commit()
            game = Game(
                title='Ark',
                platform='PC',
                status='sin jugar',
                user_id=user.id,
                steam_app_id='12345',
                steam_name='Ark'
            )
            db.session.add(game)
            db.session.commit()

            with patch('main.fetch_steam_app_details') as mock_fetch:
                mock_fetch.return_value = {
                    'achievements': {
                        'total': 2,
                        'highlighted': [
                            {'name': 'ACH_1', 'localized_name': 'Primer logro'},
                            {'name': 'ACH_2', 'localized_name': 'Segundo logro'},
                        ]
                    }
                }
                created = import_steam_achievements_for_game(game)
                self.assertEqual(len(created), 2)
                self.assertEqual(Achievement.query.filter_by(game_id=game.id).count(), 2)
                titles = [a.title for a in created]
                self.assertIn('Primer logro', titles)
                self.assertIn('Segundo logro', titles)

    def test_add_game_redirects_to_achievements_page(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        with app.app_context():
            db.drop_all()
            db.create_all()
            ensure_schema()
            user = User(username='tester', password=generate_password_hash('secret'))
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(user_id)
            session['_fresh'] = True

        response = client.post('/add', data={
            'title': 'Hades',
            'platform': 'PC',
            'status': 'Jugando',
            'progress': '10',
            'rating': '8',
            'notes': 'Muy bueno',
            'steam_app_id': '',
            'steam_name': '',
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/games/', response.headers['Location'])
        self.assertIn('/achievements', response.headers['Location'])


if __name__ == "__main__":
    unittest.main()
