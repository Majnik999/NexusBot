import os
import requests
from flask import Flask, render_template, request, session, redirect, url_for
from settings import ADMIN_IDS, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET
from functools import wraps

# Discord OAuth2 settings
DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_API_URL = "https://discord.com/api/users/@me"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('discord_login'))
        return f(*args, **kwargs)
    return decorated_function

def create_app(bot_instance):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.urandom(24)
    app.bot = bot_instance

    @app.route('/')
    @login_required
    def main():
        return render_template('index.html', server_count=len(app.bot.guilds))

    @app.route('/login')
    def login():
        return redirect(url_for('discord_login'))

    @app.route('/discord/login')
    def discord_login():
        return redirect(f"{DISCORD_AUTH_URL}?response_type=code&client_id={DISCORD_CLIENT_ID}&scope=identify&redirect_uri={url_for('discord_callback', _external=True)}")

    @app.route('/discord/callback')
    def discord_callback():
        code = request.args.get('code')
        data = {
            'client_id': DISCORD_CLIENT_ID,
            'client_secret': DISCORD_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': url_for('discord_callback', _external=True),
            'scope': 'identify'
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post(DISCORD_TOKEN_URL, data=data, headers=headers)
        token_info = response.json()

        if 'access_token' not in token_info:
            return "Error: Could not retrieve access token.", 400

        access_token = token_info['access_token']
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        user_response = requests.get(DISCORD_API_URL, headers=headers)
        user_info = user_response.json()

        if 'id' not in user_info:
            return "Error: Could not retrieve user info.", 400

        discord_id = int(user_info['id'])
        if discord_id in ADMIN_IDS:
            session['discord_id'] = discord_id
            session['admin_logged_in'] = True
            return redirect(url_for('hello_world'))
        else:
            return "You are not an authorized administrator.", 403
    @app.route('/logout')
    def logout():
        session.pop('discord_id', None)
        session.pop('admin_logged_in', None)
        return redirect(url_for('hello_world'))

    return app