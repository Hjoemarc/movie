import os
import re
import binascii
import certifi
from datetime import datetime
from bson.objectid import ObjectId
from flask import Flask, request, session, redirect, url_for, render_template, make_response, flash
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==========================================
# MONGODB SETUP
# ==========================================
ca = certifi.where()
uri = "mongodb+srv://joeanmarkhiolin_db_user:3vYbGdRiCncabJXs@cluster0.7vwb4kd.mongodb.net/"

try:
    client = MongoClient(uri, tlsCAFile=ca)
    
    # Assuming you are storing this in a DB called 'geotrack_db' based on the HTML branding. 
    # Change to 'client.bottled_water_db' if it belongs in the existing app DB.
    db = client.geotrack_db
    
    # Collections mapping to your old SQL tables
    users_col = db.users
    students_col = db.students
    devices_col = db.student_devices
    audit_col = db.audit_logs
    login_settings_col = db.login_customization
    student_settings_col = db.student_settings

except Exception as e:
    print(f"Connection failed: {e}")

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def detect_device_info(user_agent):
    """Device fingerprinting logic translated to Python."""
    device = {
        'brand': 'Unknown', 'model': 'Unknown',
        'type': 'desktop', 'os': 'Unknown',
        'friendly_name': 'Unregistered Device'
    }
    ua_lower = user_agent.lower()
    
    if 'mobi' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
        device['type'] = 'mobile'
    if 'ipad' in ua_lower or 'tablet' in ua_lower:
        device['type'] = 'tablet'
        
    if 'iphone' in ua_lower:
        device['os'], device['brand'], device['model'] = 'iOS', 'Apple', 'iPhone'
    elif 'ipad' in ua_lower:
        device['os'], device['brand'], device['model'] = 'iOS', 'Apple', 'iPad'
    elif 'android' in ua_lower:
        device['os'], device['brand'] = 'Android', 'Android Device'
        match = re.search(r'; ([^;)]+)\) applewebkit', ua_lower)
        if match: device['model'] = match.group(1).split('build/')[0].strip().title()
    elif 'windows' in ua_lower:
        device['os'], device['brand'] = 'Windows', 'PC'
    elif 'mac' in ua_lower:
        device['os'], device['brand'], device['model'] = 'macOS', 'Apple', 'Mac'
        
    friendly_parts = []
    if device['brand'] not in ['Unknown', 'PC']: friendly_parts.append(device['brand'])
    if device['model'] not in ['Unknown', 'Phone', 'Tablet']: friendly_parts.append(device['model'])
    if not friendly_parts:
        friendly_parts.append('Smartphone' if device['type'] == 'mobile' else 'Tablet' if device['type'] == 'tablet' else 'Computer')
    if device['os'] != 'Unknown': friendly_parts.append(f"({device['os']})")
        
    device['friendly_name'] = " ".join(friendly_parts) if friendly_parts else user_agent[:50] + "..."
    return device

def log_audit(user_id_str, action, details, request_obj):
    """Logs security events to MongoDB."""
    audit_col.insert_one({
        "user_id": user_id_str,
        "action": action,
        "details": details,
        "ip_address": request_obj.remote_addr or 'UNKNOWN',
        "user_agent": request_obj.headers.get('User-Agent', 'UNKNOWN'),
        "timestamp": datetime.now()
    })

# ==========================================
# LOGIN ROUTE
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    # 1. Check existing session
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin': return redirect(url_for('admin_dashboard'))
        elif role == 'teacher': return redirect(url_for('teacher_dashboard'))
        else: return redirect(url_for('student_dashboard'))

    error_msg = None
    enable_student_registration = True
    login_settings = {}

    # Fetch settings from MongoDB
    for setting in login_settings_col.find({"is_active": 1}):
        login_settings[setting.get('setting_key')] = setting.get('setting_value')

    reg_setting = student_settings_col.find_one({"setting_key": "enable_student_registration"})
    if reg_setting:
        enable_student_registration = bool(int(reg_setting.get('setting_value', 1)))

    # 2. Handle POST Request
    if request.method == 'POST':
        email_or_user = request.form.get('username')
        password = request.form.get('password')

        # Find user by username OR email using $or operator
        user = users_col.find_one({"$or": [{"username": email_or_user}, {"email": email_or_user}]})

        if user:
            if password == user.get('password'):
                user_id_str = str(user['_id']) # Convert ObjectId to string for sessions/relations
                
                if user.get('status') == 'pending':
                    error_msg = "Your account is pending approval. Please contact the administrator."
                    log_audit(user_id_str, 'login_failed', 'Account pending approval.', request)
                elif user.get('status') == 'deactivated':
                    error_msg = "Your account has been deactivated. Please check with your administrator."
                    log_audit(user_id_str, 'login_failed', 'Account deactivated.', request)
                else:
                    allow_login = True
                    student_pk = None
                    new_token = None

                    # --- DEVICE LOCK LOGIC (STUDENTS ONLY) ---
                    if user.get('role') == 'student':
                        student = students_col.find_one({"user_id": user_id_str})
                        
                        if student:
                            student_pk = str(student['_id'])
                            
                            # Get the most recent device for this student
                            device_cursor = devices_col.find({"student_id": student_pk}).sort("_id", -1).limit(1)
                            device_list = list(device_cursor)
                            device_row = device_list[0] if device_list else None
                            
                            browser_cookie = request.cookies.get('geo_device_token', '')
                            user_agent = request.headers.get('User-Agent', 'Unknown Browser')
                            current_device = detect_device_info(user_agent)

                            if device_row:
                                registered_token = device_row.get('device_identifier')

                                if browser_cookie != registered_token:
                                    # Smart Fingerprint Fallback
                                    db_os_raw = device_row.get('operating_system', '')
                                    curr_os_raw = current_device['os']
                                    db_os_base = re.sub(r'[^a-zA-Z]+', '', db_os_raw)
                                    curr_os_base = re.sub(r'[^a-zA-Z]+', '', curr_os_raw)
                                    
                                    if (device_row.get('device_type') == current_device['type'] and 
                                        device_row.get('device_brand') == current_device['brand'] and 
                                        db_os_base == curr_os_base):
                                        
                                        new_token = binascii.hexlify(os.urandom(32)).decode()
                                        devices_col.update_one(
                                            {"_id": device_row['_id']},
                                            {"$set": {"device_identifier": new_token, "last_used": datetime.now()}}
                                        )
                                        log_audit(user_id_str, 'cookie_restored', 'Cookie missing but fingerprint matched. Token regenerated.', request)
                                    else:
                                        allow_login = False
                                        error_msg = "Access Denied: You are attempting to login from an unauthorized device."
                                        log_audit(user_id_str, 'login_failed', 'Unauthorized device attempt. Original token mismatch.', request)
                                else:
                                    devices_col.update_one({"_id": device_row['_id']}, {"$set": {"last_used": datetime.now()}})
                            else:
                                # New Device Registration
                                new_token = binascii.hexlify(os.urandom(32)).decode()
                                devices_col.insert_one({
                                    "student_id": student_pk,
                                    "device_identifier": new_token,
                                    "device_name": current_device['friendly_name'],
                                    "device_brand": current_device['brand'],
                                    "device_model": current_device['model'],
                                    "device_type": current_device['type'],
                                    "operating_system": current_device['os'],
                                    "last_used": datetime.now()
                                })
                                log_audit(user_id_str, 'device_registered', f"New device registered: {current_device['friendly_name']}", request)
                        else:
                            allow_login = False
                            error_msg = "Student record not found. Contact admin."
                            log_audit(user_id_str, 'login_failed', 'Student record not found for student role.', request)

                    # --- FINAL LOGIN EXECUTION ---
                    if allow_login:
                        session.clear()
                        session['user_id'] = user_id_str
                        session['username'] = user.get('username')
                        session['full_name'] = user.get('full_name')
                        session['role'] = user.get('role')
                        session['profile_pic'] = user.get('profile_pic')

                        if user.get('role') == 'student' and student_pk:
                            new_session_id = request.cookies.get('session', os.urandom(16).hex())
                            students_col.update_one(
                                {"_id": ObjectId(student_pk)},
                                {"$set": {"active_session_id": new_session_id}}
                            )
                            
                        log_audit(user_id_str, 'login_success', 'User logged in successfully.', request)

                        if user.get('role') == 'admin': resp = make_response(redirect(url_for('admin_dashboard')))
                        elif user.get('role') == 'teacher': resp = make_response(redirect(url_for('teacher_dashboard')))
                        else: resp = make_response(redirect(url_for('student_dashboard')))

                        # Set Cookies
                        if request.form.get('remember_me') == 'on':
                            resp.set_cookie('geo_login_user', user.get('username', ''), max_age=86400*30, httponly=True)
                        else:
                            resp.set_cookie('geo_login_user', '', expires=0)

                        if new_token:
                            resp.set_cookie('geo_device_token', new_token, max_age=86400*365, httponly=True)

                        return resp
            else:
                error_msg = "Incorrect password."
                log_audit(str(user.get('_id', '')), 'login_failed', 'Incorrect password attempt.', request)
        else:
            error_msg = "User not found."
            log_audit(None, 'login_failed', f'User not found. Attempted username: {email_or_user}', request)
            
    if error_msg:
        flash(error_msg, 'error')
        
    return render_template('login.html', login_settings=login_settings, enable_student_registration=enable_student_registration)