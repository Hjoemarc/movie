from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
import certifi
from bson.objectid import ObjectId
from datetime import datetime
import os

app = Flask(__name__)
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
    
    # Auto-initialize Admin account and Finished Product tracker
    if not users.find_one({"username": "admin"}):
        users.insert_one({
            "first_name": "System",
            "last_name": "Admin",
            "username": "admin", 
            "password": "admin123", 
            "role": "Admin"
        })
        
    if not finished_products.find_one({"product_name": "Bottled Water"}):
        finished_products.insert_one({"product_name": "Bottled Water", "quantity": 0, "date_updated": datetime.now()})

except Exception as e:
    print(f"Connection failed: {e}")

# READ: Main Router
@app.route('/', methods=['GET'])
def index():
    if 'user_id' not in session:
        return render_template('index.html', view='login')

    view = request.args.get('view', 'dashboard')
    data = {}

    if view == 'dashboard':
        data['total_raw'] = raw_materials.count_documents({})
        fp = finished_products.find_one({"product_name": "Bottled Water"})
        data['total_finished'] = fp['quantity'] if fp else 0
        data['low_stock'] = len(list(raw_materials.find({"$expr": {"$lte": ["$quantity", "$reorder_level"]}})))
        
        today = datetime.now().strftime("%Y-%m-%d")
        today_prod = list(production.find({"date": {"$regex": f"^{today}"}}))
        data['today_prod'] = sum(item['quantity_produced'] for item in today_prod)

    elif view == 'inventory':
        data['materials'] = list(raw_materials.find())

    elif view == 'production':
        data['history'] = list(production.find().sort("_id", -1).limit(20))

    return render_template('index.html', view=view, data=data)

# AUTHENTICATION: Login
@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    user = users.find_one({"username": username})
    
    if user and user['password'] == password:
        session['user_id'] = str(user['_id'])
        session['username'] = user['username']
        session['full_name'] = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user['username']
        session['role'] = user['role']
    else:
        flash("Invalid credentials. Please try again.", "error")
    return redirect(url_for('index'))

# AUTHENTICATION: Register
@app.route('/register', methods=['POST'])
def register():
    # Gather basic details
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    # Gather new detailed fields
    employee_id = request.form.get('employee_id')
    gender = request.form.get('gender')
    email = request.form.get('email')
    phone = request.form.get('phone')
    
    if users.find_one({"username": username}):
        flash("Username already exists! Please choose another.", "error")
    else:
        users.insert_one({
            "first_name": first_name,
            "last_name": last_name,
            "employee_id": employee_id,
            "gender": gender,
            "email": email,
            "phone": phone,
            "username": username, 
            "password": password, 
            "role": role,
            "date_created": datetime.now()
        })
        flash("Account created successfully! You can now log in.", "success")
        
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
    
    if not labels or labels['quantity'] < qty:
        flash("Insufficient Labels in inventory!", "error")
    elif not caps or caps['quantity'] < qty:
        flash("Insufficient Caps in inventory!", "error")
    elif not bottles or bottles['quantity'] < qty:
        flash("Insufficient Bottles in inventory!", "error")
    else:
        raw_materials.update_one({"name": "Labels"}, {"$inc": {"quantity": -qty}})
        raw_materials.update_one({"name": "Caps"}, {"$inc": {"quantity": -qty}})
        raw_materials.update_one({"name": "Bottles"}, {"$inc": {"quantity": -qty}})
        
        finished_products.update_one(
            {"product_name": "Bottled Water"},
            {"$inc": {"quantity": qty}, "$set": {"date_updated": datetime.now()}}
        )
        
        production.insert_one({
            "quantity_produced": qty,
            "produced_by": session['full_name'],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        flash(f"Successfully produced {qty} bottles of water!", "success")
        
    return redirect(url_for('index', view='production'))

# DELETE: Remove Material
@app.route('/delete_material/<id>', methods=['POST'])
def delete_material(id):
    if 'user_id' in session:
        raw_materials.delete_one({"_id": ObjectId(id)})
        flash("Material deleted.", "success")
    return redirect(url_for('index', view='inventory'))

if __name__ == '__main__':
    app.run(debug=True)