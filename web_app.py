from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
# Secret key is required for sessions and flashing messages
app.secret_key = os.urandom(24) 

# Setup Connection
ca = certifi.where()
uri = "mongodb+srv://joeanmarkhiolin_db_user:3vYbGdRiCncabJXs@cluster0.7vwb4kd.mongodb.net/"

try:
    client = MongoClient(uri, tlsCAFile=ca)
    db = client.bottled_water_db
    
    # Collections
    users = db.users
    raw_materials = db.raw_materials
    production = db.production
    finished_products = db.finished_products
    suppliers = db.suppliers
    reports = db.reports
    
    # Auto-initialize Admin account and Finished Product tracker if they don't exist
    if not users.find_one({"username": "admin"}):
        users.insert_one({"username": "admin", "password": generate_password_hash("admin123"), "role": "Admin"})
    if not finished_products.find_one({"product_name": "Bottled Water"}):
        finished_products.insert_one({"product_name": "Bottled Water", "quantity": 0, "date_updated": datetime.now()})

except Exception as e:
    print(f"Connection failed: {e}")

# READ: Main Router
@app.route('/', methods=['GET'])
def index():
    # If not logged in, force the login view
    if 'user_id' not in session:
        return render_template('index.html', view='login')

    # Determine which page to show (default is dashboard)
    view = request.args.get('view', 'dashboard')
    data = {}

    # Fetch data based on the active view
    if view == 'dashboard':
        data['total_raw'] = raw_materials.count_documents({})
        fp = finished_products.find_one({"product_name": "Bottled Water"})
        data['total_finished'] = fp['quantity'] if fp else 0
        data['low_stock'] = len(list(raw_materials.find({"$expr": {"$lte": ["$quantity", "$reorder_level"]}})))
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_prod = list(production.find({"date": {"$regex": f"^{today}"}}))
        data['today_prod'] = sum(item['quantity_produced'] for item in today_prod)
        data['total_suppliers'] = suppliers.count_documents({})

    elif view == 'inventory':
        data['materials'] = list(raw_materials.find())

    elif view == 'production':
        data['history'] = list(production.find().sort("_id", -1).limit(20))

    return render_template('index.html', view=view, data=data)

# AUTHENTICATION
@app.route('/login', methods=['POST'])
def login():
    user = users.find_one({"username": request.form.get('username')})
    if user and check_password_hash(user['password'], request.form.get('password')):
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['role'] = user['role']
    else:
        flash("Invalid credentials. Try admin / admin123", "danger")
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# CREATE: Add Material
@app.route('/add_material', methods=['POST'])
def add_material():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    raw_materials.insert_one({
        "name": request.form.get('name'),
        "quantity": int(request.form.get('quantity')),
        "unit": request.form.get('unit'),
        "reorder_level": int(request.form.get('reorder_level')),
        "date_added": datetime.now().strftime("%Y-%m-%d")
    })
    flash("Material added successfully!", "success")
    return redirect(url_for('index', view='inventory'))

# ACTION: Run Production
@app.route('/produce', methods=['POST'])
def produce():
    if 'user_id' not in session: return redirect(url_for('index'))
    
    qty = int(request.form.get('quantity'))
    
    labels = raw_materials.find_one({"name": "Labels"})
    caps = raw_materials.find_one({"name": "Caps"})
    bottles = raw_materials.find_one({"name": "Bottles"})
    
    # Check if materials exist and are sufficient
    if not labels or labels['quantity'] < qty:
        flash("Insufficient Labels in inventory!", "danger")
    elif not caps or caps['quantity'] < qty:
        flash("Insufficient Caps in inventory!", "danger")
    elif not bottles or bottles['quantity'] < qty:
        flash("Insufficient Bottles in inventory!", "danger")
    else:
        # Deduct Raw Materials
        raw_materials.update_one({"name": "Labels"}, {"$inc": {"quantity": -qty}})
        raw_materials.update_one({"name": "Caps"}, {"$inc": {"quantity": -qty}})
        raw_materials.update_one({"name": "Bottles"}, {"$inc": {"quantity": -qty}})
        
        # Add Finished Products
        finished_products.update_one(
            {"product_name": "Bottled Water"},
            {"$inc": {"quantity": qty}, "$set": {"date_updated": datetime.now()}}
        )
        
        # Save History
        production.insert_one({
            "quantity_produced": qty,
            "produced_by": session['username'],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash(f"Successfully produced {qty} bottles of water!", "success")
        
    return redirect(url_for('index', view='production'))

# DELETE: Remove Material
@app.route('/delete_material/<id>', methods=['POST'])
def delete_material(id):
    if 'user_id' in session:
        raw_materials.delete_one({"_id": ObjectId(id)})
        flash("Material deleted.", "warning")
    return redirect(url_for('index', view='inventory'))

if __name__ == '__main__':
    app.run(debug=True)