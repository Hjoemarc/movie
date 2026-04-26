from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'my_super_secret_static_key_123')

# Setup Connection
ca = certifi.where()
uri = "mongodb+srv://joeanmarkhiolin_db_user:3vYbGdRiCncabJXs@cluster0.7vwb4kd.mongodb.net/"

try:
    client = MongoClient(uri, tlsCAFile=ca)
    db = client.school_project
    
    users = db.users
    raw_materials = db.raw_materials
    production = db.production
    finished_products = db.finished_products

except Exception as e:
    print(f"Connection failed: {e}")

# ==========================================
# PUBLIC ROUTE (LANDING PAGE)
# ==========================================
@app.route('/')
def landing_page():
    # Show index.html to everyone! No login check required.
    return render_template('index.html')

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If the user is already logged in, send them straight to the dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user = users.find_one({"username": request.form.get('username')})
        if user and user['password'] == request.form.get('password'):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['full_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user['username']
            session['role'] = user['role']
            # Redirect to the secure dashboard upon successful login
            return redirect(url_for('dashboard'))
        flash("Invalid credentials. Please try again.", "error")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    # Redirect back to the landing page when logging out
    return redirect(url_for('landing_page'))

# ==========================================
# SECURE ROUTES (DASHBOARD)
# ==========================================
@app.route('/dashboard', methods=['GET'])
def dashboard():
    # Block unauthenticated users
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    view = request.args.get('view', 'dashboard')
    data = {}
    
    # We will expand this logic later when building out the student/teacher specific data
    
    # Render the secure internal dashboard
    return render_template('dashboard.html', view=view, data=data)

if __name__ == '__main__':
    app.run(debug=True)