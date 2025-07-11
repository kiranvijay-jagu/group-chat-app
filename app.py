import os
from flask import *
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from deep_translator import GoogleTranslator
ADMIN_EMAIL = "kiranvijay1414@gmail.com"
ADMIN_PASSWORD = "vijay143"
app = Flask(__name__)
app.jinja_env.cache = {}

app.secret_key = 'your_secret_key'
DATABASE = 'users.db'

def initialize_database():
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS groups")
        cursor.execute("DROP TABLE IF EXISTS group_members")
        cursor.execute("DROP TABLE IF EXISTS messages")
        cursor.execute("DROP TABLE IF EXISTS translations")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                email TEXT UNIQUE, 
                password TEXT, 
                language TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                creator_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER, 
                user_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER,
                user_name TEXT,
                message TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                group_id INTEGER,
                original_message_id INTEGER,
                user_id INTEGER,
                translated_message TEXT,
                PRIMARY KEY (group_id, original_message_id, user_id)
            )
        """)
        db.commit()

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        language = request.form['language']

        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM users WHERE email=?", (email,))
            if cursor.fetchone():
                return "User already registered"
            cursor.execute(
                "INSERT INTO users (name, email, password, language) VALUES (?, ?, ?, ?)",
                (name, email, password, language)
            )
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            cursor.execute("SELECT id, password FROM users WHERE email=? AND name=?", (email, name))
            user = cursor.fetchone()

            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['user_name'] = name
                session['email'] = email
                return redirect('/dashboard')
            else:
                return "Invalid login"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    user_name = session['user_name']

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("""
            SELECT groups.id, groups.name FROM groups
            JOIN group_members ON groups.id = group_members.group_id
            WHERE group_members.user_id = ?
        """, (user_id,))
        groups = cursor.fetchall()

    return render_template('dashboard.html', groups=groups, username=user_name)

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        group_name = request.form['group_name']
        creator_id = session['user_id']
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO groups (name, creator_id) VALUES (?, ?)", (group_name, creator_id))
            group_id = cursor.lastrowid
            cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, creator_id))
        return redirect('/dashboard')

    return render_template('create_group.html')

@app.route('/group/<int:group_id>', methods=['GET', 'POST'])
def group_chat(group_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    user_name = session['user_name']
    message = None

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()

        # Verify user is a member of the group
        cursor.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id))
        if not cursor.fetchone():
            return redirect('/dashboard')

        # Handle message submission
        if request.method == 'POST' and 'message' in request.form:
            text = request.form['message']

            try:
                english_version = GoogleTranslator(source='auto', target='en').translate(text)
            except Exception:
                english_version = text

            # Save original message (as entered by user)
            cursor.execute("INSERT INTO messages (group_id, user_name, message) VALUES (?, ?, ?)",
                           (group_id, user_name, text))
            message_id = cursor.lastrowid

            # Translate English to each member's language and store
            cursor.execute("""
                SELECT users.id, users.language FROM users
                JOIN group_members ON users.id = group_members.user_id
                WHERE group_members.group_id = ?
            """, (group_id,))
            members = cursor.fetchall()

            for member_id, lang in members:
                try:
                    translated = GoogleTranslator(source='en', target=lang).translate(english_version)
                except Exception:
                    translated = english_version
                cursor.execute("""
                    INSERT OR REPLACE INTO translations (group_id, original_message_id, user_id, translated_message)
                    VALUES (?, ?, ?, ?)
                """, (group_id, message_id, member_id, translated))

            db.commit()
            return redirect(url_for('group_chat', group_id=group_id))

        # Get group name and admin info
        cursor.execute("SELECT name, creator_id FROM groups WHERE id=?", (group_id,))
        group = cursor.fetchone()
        group_name, creator_id = group[0], group[1]
        is_admin = user_id == creator_id

        # Fetch translated messages for this user
        cursor.execute("""
            SELECT m.user_name, t.translated_message
            FROM messages m
            JOIN translations t ON m.id = t.original_message_id
            WHERE m.group_id=? AND t.user_id=?
            ORDER BY m.id
        """, (group_id, user_id))
        messages = cursor.fetchall()

        # Fetch group members
        cursor.execute("""
            SELECT users.name, users.language FROM users
            JOIN group_members ON users.id = group_members.user_id
            WHERE group_members.group_id = ?
        """, (group_id,))
        members = cursor.fetchall()

    return render_template("chat.html", group_id=group_id, group_name=group_name,
                           messages=messages, username=user_name,
                           is_admin=is_admin, members=members, message=message)

@app.route('/add_member/<int:group_id>', methods=['POST'])
def add_member(group_id):
    if 'user_id' not in session:
        return redirect('/login')
    user_id = session['user_id']
    member_email = request.form['member_email']

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("SELECT creator_id FROM groups WHERE id=?", (group_id,))
        creator_id = cursor.fetchone()[0]
        if user_id != creator_id:
            message = "Only the group creator can add members"
        else:
            cursor.execute("SELECT id FROM users WHERE email=?", (member_email,))
            user = cursor.fetchone()
            if not user:
                message = "User is not registered"
            else:
                new_user_id = user[0]
                cursor.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=?", (group_id, new_user_id))
                if cursor.fetchone():
                    message = "User already in group"
                else:
                    cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, new_user_id))
                    message = "Added successfully"

        cursor.execute("SELECT name FROM groups WHERE id=?", (group_id,))
        group_name = cursor.fetchone()[0]
        cursor.execute("SELECT * FROM messages WHERE group_id=?", (group_id,))
        messages = cursor.fetchall()
        cursor.execute("""
            SELECT users.name, users.language FROM users
            JOIN group_members ON users.id = group_members.user_id
            WHERE group_members.group_id = ?
        """, (group_id,))
        members = cursor.fetchall()

    return render_template("chat.html", group_id=group_id, group_name=group_name, messages=messages,
                           message=message, is_admin=True, username=session['user_name'], members=members)

@app.route('/remove_member/<int:group_id>', methods=['POST'])
def remove_member(group_id):
    if 'user_id' not in session:
        return redirect('/login')
    user_id = session['user_id']
    member_email = request.form['member_email']

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("SELECT creator_id FROM groups WHERE id=?", (group_id,))
        creator_id = cursor.fetchone()[0]
        if user_id != creator_id:
            message = "Only the group creator can remove members"
        else:
            cursor.execute("SELECT id FROM users WHERE email=?", (member_email,))
            user = cursor.fetchone()
            if not user:
                message = "User not registered"
            else:
                remove_id = user[0]
                cursor.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=?", (group_id, remove_id))
                if not cursor.fetchone():
                    message = "User not in group"
                else:
                    cursor.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (group_id, remove_id))
                    message = "Removed successfully"

        cursor.execute("SELECT name FROM groups WHERE id=?", (group_id,))
        group_name = cursor.fetchone()[0]
        cursor.execute("SELECT * FROM messages WHERE group_id=?", (group_id,))
        messages = cursor.fetchall()
        cursor.execute("""
            SELECT users.name, users.language FROM users
            JOIN group_members ON users.id = group_members.user_id
            WHERE group_members.group_id = ?
        """, (group_id,))
        members = cursor.fetchall()

    return render_template("chat.html", group_id=group_id, group_name=group_name, messages=messages,
                           message=message, is_admin=True, username=session['user_name'], members=members)

@app.route('/exit_group/<int:group_id>', methods=['POST'])
def exit_group(group_id):
    if 'user_id' not in session:
        return redirect('/login')
    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("SELECT creator_id FROM groups WHERE id=?", (group_id,))
        creator_id = cursor.fetchone()[0]
        if user_id == creator_id:
            cursor.execute("SELECT user_id FROM group_members WHERE group_id=? AND user_id!=? LIMIT 1", (group_id, user_id))
            new_admin = cursor.fetchone()
            if new_admin:
                cursor.execute("UPDATE groups SET creator_id=? WHERE id=?", (new_admin[0], group_id))
            else:
                return render_template('home.html', message="No one left to assign ownership")
        cursor.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id))
    return redirect('/dashboard')
@app.route('/chat_area/<int:group_id>')
def chat_area(group_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    user_name = session['user_name']

    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()

        # Check if user is in the group
        cursor.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id))
        if not cursor.fetchone():
            return "Unauthorized", 403

        # Fetch translated messages for this user
        cursor.execute("""
            SELECT m.user_name, t.translated_message
            FROM messages m
            JOIN translations t ON m.id = t.original_message_id
            WHERE m.group_id=? AND t.user_id=?
            ORDER BY m.id
        """, (group_id, user_id))
        messages = cursor.fetchall()

    return render_template("chat_area.html", messages=messages, username=user_name)
@app.route('/chat_status/<int:group_id>')
def chat_status(group_id):
    if 'user_id' not in session:
        return jsonify({"ready": False})

    user_id = session['user_id']
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()

        # Get the most recent message ID in this group
        cursor.execute("SELECT MAX(id) FROM messages WHERE group_id=?", (group_id,))
        last_message_id = cursor.fetchone()[0]

        if not last_message_id:
            return jsonify({"ready": True})  # No messages yet

        # Check if a translation exists for the current user
        cursor.execute("""SELECT 1 FROM translations
                          WHERE group_id=? AND original_message_id=? AND user_id=?""",
                       (group_id, last_message_id, user_id))
        translated = cursor.fetchone() is not None

    return jsonify({"ready": translated})

#admin login
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password'].strip()

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect('/admin_dashboard')
        else:
            return render_template('admin_login.html', error="Invalid credentials")
    return render_template('admin_login.html')

#admin dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('is_admin'):
        return redirect('/admin_login')
    
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

        cursor.execute("SELECT * FROM groups")
        groups = cursor.fetchall()

        group_members = {}
        for group in groups:
            group_id = group[0]
            cursor.execute("""
                SELECT users.id, users.name, users.language 
                FROM users 
                JOIN group_members ON users.id = group_members.user_id 
                WHERE group_members.group_id=?
            """, (group_id,))
            group_members[group_id] = cursor.fetchall()

    return render_template('admin_dashboard.html', users=users, groups=groups, group_members=group_members)

#admin delete options

@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect('/admin_login')
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()

        # Get all message IDs sent by this user
        cursor.execute("SELECT id FROM messages WHERE user_name = (SELECT name FROM users WHERE id=?)", (user_id,))
        message_ids = [row[0] for row in cursor.fetchall()]

        # Delete translations related to this user's messages
        for msg_id in message_ids:
            cursor.execute("DELETE FROM translations WHERE original_message_id=?", (msg_id,))

        # Delete user's messages
        cursor.execute("DELETE FROM messages WHERE user_name = (SELECT name FROM users WHERE id=?)", (user_id,))

        # Delete translations received by this user
        cursor.execute("DELETE FROM translations WHERE user_id=?", (user_id,))

        # Remove from all group memberships
        cursor.execute("DELETE FROM group_members WHERE user_id=?", (user_id,))

        # Delete the user account
        cursor.execute("DELETE FROM users WHERE id=?", (user_id,))

    return redirect('/admin_dashboard')


@app.route('/admin/delete_group/<int:group_id>')
def delete_group(group_id):
    if not session.get('is_admin'):
        return redirect('/admin_login')
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()

        # Get all messages of this group
        cursor.execute("SELECT id FROM messages WHERE group_id=?", (group_id,))
        message_ids = [row[0] for row in cursor.fetchall()]

        # Delete translations of those messages
        for msg_id in message_ids:
            cursor.execute("DELETE FROM translations WHERE original_message_id=?", (msg_id,))

        # Delete messages
        cursor.execute("DELETE FROM messages WHERE group_id=?", (group_id,))

        # Delete group members
        cursor.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))

        # Delete group
        cursor.execute("DELETE FROM groups WHERE id=?", (group_id,))

    return redirect('/admin_dashboard')

@app.route('/admin/remove_member/<int:group_id>/<int:user_id>')
def admin_remove_member(group_id, user_id):
    if not session.get('is_admin'):
        return redirect('/admin_login')
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        cursor.execute("DELETE FROM group_members WHERE group_id=? AND user_id=?", (group_id, user_id))
        cursor.execute("DELETE FROM translations WHERE group_id=? AND user_id=?", (group_id, user_id))
    return redirect('/admin_dashboard')



#admin logout
@app.route('/admin_logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if os.environ.get('RENDER') else '127.0.0.1'
    app.run(debug=True, host=host, port=port, use_reloader=False)
