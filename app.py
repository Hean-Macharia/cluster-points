from flask import Flask, render_template, request, jsonify, send_from_directory, session, send_file, redirect, Response
from datetime import datetime, timedelta
import math
import json
import os
import re
import uuid
import requests
import base64
import random
import io
from functools import wraps 
from pymongo import MongoClient
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile
import time
import logging
import traceback
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# MongoDB Configuration
db = None  # Initialize db variable
try:
    mongo_client = MongoClient(os.getenv('MONGODB_URI'), serverSelectionTimeoutMS=5000)
    mongo_client.server_info()  # Test connection
    db = mongo_client[os.getenv('DATABASE_NAME', 'kcse_calculator')]
    print("✅ MongoDB connected successfully!")
    users_collection = db['users']
    payments_collection = db['payments']
    results_collection = db['results']
    pdfs_collection = db['pdfs']
    
    # Create indexes for better performance
    users_collection.create_index('kcse_index')
    users_collection.create_index('email')
    payments_collection.create_index('mpesa_request_id')
    payments_collection.create_index('user_id')
    results_collection.create_index('user_id')
    
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    # Create dummy collections for testing
    class DummyCollection:
        def find_one(self, *args, **kwargs):
            return None
        def insert_one(self, *args, **kwargs):
            class DummyResult:
                inserted_id = str(uuid.uuid4())
            return DummyResult()
        def update_one(self, *args, **kwargs):
            return None
        def update_many(self, *args, **kwargs):
            return None
        def find(self, *args, **kwargs):
            return []
        def delete_one(self, *args, **kwargs):
            return None
        def delete_many(self, *args, **kwargs):
            return None
        def count_documents(self, *args, **kwargs):
            return 0
        def create_index(self, *args, **kwargs):
            return None
    
    db = None
    users_collection = payments_collection = results_collection = pdfs_collection = DummyCollection()

# Background thread for retrying unmatched callbacks
def process_unmatched_callbacks():
    """Background thread to retry processing unmatched callbacks"""
    while True:
        try:
            time.sleep(60)  # Check every minute
            
            # Check if db is not None
            if db is not None:
                # Check if unmatched_callbacks collection exists
                try:
                    unmatched = db.unmatched_callbacks.find({
                        'status': 'unmatched',
                        'received_at': {'$gt': datetime.now() - timedelta(hours=24)}
                    })
                    
                    for callback in unmatched:
                        print(f"🔄 Retrying unmatched callback: {callback.get('callback_id')}")
                        
                        # Try to find payment again
                        checkout_id = callback.get('checkout_request_id')
                        payment = None
                        
                        if checkout_id:
                            payment = payments_collection.find_one({
                                'mpesa_request_id': checkout_id
                            })
                        
                        if payment:
                            # Found payment - process it
                            result_code = callback.get('result_code', 0)
                            result_desc = callback.get('result_desc', 'Success')
                            
                            if result_code == 0:
                                payments_collection.update_one(
                                    {'_id': payment['_id']},
                                    {'$set': {
                                        'status': 'completed',
                                        'mpesa_receipt': 'RETRY_' + str(int(time.time())),
                                        'result_desc': result_desc,
                                        'callback_received_at': datetime.now()
                                    }}
                                )
                                
                                users_collection.update_one(
                                    {'user_id': payment['user_id']},
                                    {'$set': {
                                        'payment_status': 'completed',
                                        'payment_date': datetime.now()
                                    }}
                                )
                                
                                print(f"✅ Successfully processed unmatched callback for {payment['user_id']}")
                                
                                # Mark as processed
                                db.unmatched_callbacks.update_one(
                                    {'_id': callback['_id']},
                                    {'$set': {
                                        'status': 'processed',
                                        'processed_at': datetime.now()
                                    }}
                                )
                except Exception as e:
                    print(f"Error processing unmatched callbacks: {e}")
                        
        except Exception as e:
            print(f"Error in callback retry thread: {e}")

# Start background thread if MongoDB is connected
if db is not None:
    retry_thread = threading.Thread(target=process_unmatched_callbacks, daemon=True)
    retry_thread.start()
    print("✅ Callback retry thread started")

# M-Pesa Configuration
MPESA_CONFIG = {
    'consumer_key': os.getenv('MPESA_CONSUMER_KEY'),
    'consumer_secret': os.getenv('MPESA_CONSUMER_SECRET'),
    'business_shortcode': os.getenv('MPESA_BUSINESS_SHORTCODE'),
    'passkey': os.getenv('MPESA_PASSKEY'),
    'callback_url': os.getenv('MPESA_CALLBACK_URL'),
    'environment': os.getenv('MPESA_ENVIRONMENT', 'production')
}

# Payment settings
PAYMENT_AMOUNT = int(os.getenv('PAYMENT_AMOUNT', 100))
PAYMENT_PURPOSE = os.getenv('PAYMENT_PURPOSE', 'KCSE Cluster Points Calculation')

# Grade to points mapping (Kenya KCSE)
GRADE_POINTS = {
    'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8,
    'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3,
    'D-': 2, 'E': 1
}

# Subject groups mapping - COMPLETE KCSE coverage
SUBJECT_GROUPS = {
    'Group I': ['english', 'kiswahili', 'mathematics'],
    'Group II': ['biology', 'physics', 'chemistry', 'general_science'],
    'Group III': ['history', 'geography', 'cre', 'ire', 'hre'],
    'Group IV': [
        'agriculture', 'computer', 'arts', 'woodwork', 'metalwork', 
        'building', 'electronics', 'homescience', 'aviation',
        'drawing_design', 'power_mechanics'
    ],
    'Group V': [
        'french', 'german', 'arabic', 'kenya_sign_language', 
        'music', 'business'
    ]
}

# Subject name mapping for normalization
SUBJECT_NAME_MAP = {
    'mathematics': 'mathematics',
    'english': 'english',
    'kiswahili': 'kiswahili',
    'physics': 'physics',
    'chemistry': 'chemistry',
    'biology': 'biology',
    'geography': 'geography',
    'history': 'history',
    'cre': 'cre',
    'ire': 'ire',
    'hre': 'hre',
    'general_science': 'general_science',
    'homescience': 'homescience',
    'music': 'music',
    'french': 'french',
    'german': 'german',
    'arabic': 'arabic',
    'kenya_sign_language': 'kenya_sign_language',
    'business': 'business',
    'agriculture': 'agriculture',
    'computer': 'computer',
    'arts': 'arts',
    'woodwork': 'woodwork',
    'metalwork': 'metalwork',
    'building': 'building',
    'electronics': 'electronics',
    'aviation': 'aviation',
    'drawing_design': 'drawing_design',
    'power_mechanics': 'power_mechanics',
    'mathematics_a': 'mathematics',
    'mathematics_b': 'mathematics',
    'home_science': 'homescience',
    'art': 'arts',
    'art_and_design': 'arts',
    'building_construction': 'building',
    'electricity': 'electronics',
    'electricity_electronics': 'electronics'
}

# Cluster definitions
CLUSTERS = {
    1: {'name': 'Cluster 1', 'description': 'Law', 'requirements': []},
    2: {'name': 'Cluster 2', 'description': 'Business and Hospitality Related', 'requirements': []},
    3: {'name': 'Cluster 3', 'description': 'Social Sciences And Arts', 'requirements': []},
    4: {'name': 'Cluster 4', 'description': 'Geosciences', 'requirements': []},
    5: {'name': 'Cluster 5', 'description': 'Engineering, Technology', 'requirements': []},
    6: {'name': 'Cluster 6', 'description': 'Architecture, Building Construction', 'requirements': []},
    7: {'name': 'Cluster 7', 'description': 'Computing, IT related', 'requirements': []},
    8: {'name': 'Cluster 8', 'description': 'Agribusiness', 'requirements': []},
    9: {'name': 'Cluster 9', 'description': 'General Sciences', 'requirements': []},
    10: {'name': 'Cluster 10', 'description': 'Actuarial science', 'requirements': []},
    11: {'name': 'Cluster 11', 'description': 'Interior Design', 'requirements': []},
    12: {'name': 'Cluster 12', 'description': 'Sport Science', 'requirements': []},
    13: {'name': 'Cluster 13', 'description': 'Medicine', 'requirements': []},
    14: {'name': 'Cluster 14', 'description': 'History', 'requirements': []},
    15: {'name': 'Cluster 15', 'description': 'Agriculture', 'requirements': []},
    16: {'name': 'Cluster 16', 'description': 'Geography Focus', 'requirements': []},
    17: {'name': 'Cluster 17', 'description': 'French and German', 'requirements': []},
    18: {'name': 'Cluster 18', 'description': 'Music and Arts', 'requirements': []},
    19: {'name': 'Cluster 19', 'description': 'Education Related', 'requirements': []},
    20: {'name': 'Cluster 20', 'description': 'Religious Studies', 'requirements': []}
}

# ===== HELPER FUNCTIONS =====

def normalize_subject_name(subject):
    return SUBJECT_NAME_MAP.get(subject.lower(), subject.lower())

def get_subject_group(subject):
    normalized = normalize_subject_name(subject)
    for group, subjects in SUBJECT_GROUPS.items():
        if normalized in subjects:
            return group
    return None

def get_group_subjects(group_name):
    return SUBJECT_GROUPS.get(group_name, [])

def get_best_subjects_by_group(grades, group_name, count=1, exclude_subjects=None):
    if exclude_subjects is None:
        exclude_subjects = []
    
    group_subjects = get_group_subjects(group_name)
    subject_points = []
    
    for subject in group_subjects:
        if subject in grades and grades[subject]:
            if subject in exclude_subjects:
                continue
            points = GRADE_POINTS.get(grades[subject], 0)
            subject_points.append((subject, points, grades[subject]))
    
    subject_points.sort(key=lambda x: x[1], reverse=True)
    return subject_points[:count]

def get_aggregate_points(grades):
    all_points = []
    for subject, grade in grades.items():
        if grade:
            points = GRADE_POINTS.get(grade, 0)
            all_points.append((subject, points))
    
    all_points.sort(key=lambda x: x[1], reverse=True)
    top_7 = all_points[:7]
    total_points = sum(p for _, p in top_7)
    return total_points, top_7

def calculate_cluster_points(grades, cluster_id, debug=False):
    valid_grades = [g for g in grades.values() if g]
    if valid_grades:
        avg_grade = sum(GRADE_POINTS.get(g, 0) for g in valid_grades) / len(valid_grades)
        cluster_points = avg_grade * 4
        cluster_points = max(0.000, min(48.000, cluster_points - 3.0))
        return round(cluster_points, 3), [], []
    return 0.000, [], []

def validate_kcse_index(kcse_index):
    pattern = r'^\d{11}/\d{4}$'
    if re.match(pattern, kcse_index):
        index_part, year_part = kcse_index.split('/')
        year = int(year_part)
        current_year = datetime.now().year
        if 1980 <= year <= current_year + 1:
            return True, "Valid KCSE index"
    return False, "Invalid KCSE index format. Use: 12345678912/2024"

def validate_phone_number(phone):
    phone = str(phone).strip().replace(' ', '').replace('-', '').replace('+', '')
    
    if phone.startswith('254') and len(phone) == 12:
        return True, phone
    elif phone.startswith('07') or phone.startswith('01'):
        if len(phone) == 10:
            return True, '254' + phone[1:]
    elif phone.startswith('7') and len(phone) == 9:
        return True, '254' + phone
    
    return False, "Invalid phone number. Use format: 0712345678 or 254712345678"

def generate_access_token():
    try:
        if MPESA_CONFIG['environment'] == 'sandbox':
            url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        else:
            url = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        
        response = requests.get(
            url,
            auth=(MPESA_CONFIG['consumer_key'], MPESA_CONFIG['consumer_secret']),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['access_token']
        else:
            raise Exception(f"Failed to get access token: {response.text}")
    except Exception as e:
        logger.error(f"Access token generation error: {str(e)}")
        raise

def initiate_stk_push(phone_number, amount, account_reference, transaction_desc):
    try:
        access_token = generate_access_token()
        
        if MPESA_CONFIG['environment'] == 'sandbox':
            url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        else:
            url = 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password_str = f"{MPESA_CONFIG['business_shortcode']}{MPESA_CONFIG['passkey']}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode()
        
        payload = {
            "BusinessShortCode": MPESA_CONFIG['business_shortcode'],
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": MPESA_CONFIG['business_shortcode'],
            "PhoneNumber": phone_number,
            "CallBackURL": MPESA_CONFIG['callback_url'],
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13]
        }
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response_data = response.json()
        return response_data
        
    except Exception as e:
        logger.error(f"STK Push error: {str(e)}")
        raise

# ===== MAIN ROUTES =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'mongo_connected': db is not None,
        'environment': MPESA_CONFIG['environment'],
        'callback_url': MPESA_CONFIG['callback_url']
    })

@app.route('/test-callback', methods=['GET', 'POST'])
def test_callback():
    if request.method == 'POST':
        logger.info(f"Test POST received: {request.get_json()}")
    return jsonify({
        'status': 'ok',
        'message': 'Callback endpoint is reachable',
        'timestamp': datetime.now().isoformat(),
        'method': request.method
    })

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        
        kcse_index = data.get('kcse_index', '').strip()
        email = data.get('email', '').strip().lower()
        phone_number = data.get('phone_number', '').strip()
        
        logger.info(f"Registration attempt - Index: {kcse_index}, Email: {email}")
        
        is_valid_index, index_msg = validate_kcse_index(kcse_index)
        if not is_valid_index:
            return jsonify({'success': False, 'error': index_msg}), 400
        
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        is_valid_phone, formatted_phone = validate_phone_number(phone_number)
        if not is_valid_phone:
            return jsonify({'success': False, 'error': formatted_phone}), 400
        
        manual_user = users_collection.find_one({
            '$or': [{'kcse_index': kcse_index}, {'email': email}],
            'manual_activation': True,
            'manual_expired': {'$ne': True},
            'manual_used': {'$ne': True}
        })
        
        if manual_user:
            activated_at = manual_user.get('activated_at')
            if activated_at and (datetime.now() - activated_at).days <= 30:
                session['user_id'] = manual_user['user_id']
                session['kcse_index'] = kcse_index
                session['email'] = email
                return jsonify({
                    'success': True,
                    'message': 'Manual payment verified',
                    'user_id': manual_user['user_id'],
                    'can_calculate': True,
                    'payment_method': 'manual'
                })
        
        existing_user = users_collection.find_one({
            '$or': [{'kcse_index': kcse_index}, {'email': email}]
        })
        
        user_id = None
        
        if existing_user:
            user_id = existing_user['user_id']
            if existing_user.get('payment_status') == 'completed':
                session['user_id'] = user_id
                session['kcse_index'] = kcse_index
                session['email'] = email
                return jsonify({
                    'success': True,
                    'message': 'User already registered and paid',
                    'user_id': user_id,
                    'can_calculate': True,
                    'payment_method': 'mpesa'
                })
            else:
                users_collection.update_one(
                    {'user_id': user_id},
                    {'$set': {'phone_number': formatted_phone, 'updated_at': datetime.now()}}
                )
        else:
            user_id = str(uuid.uuid4())
            user_data = {
                'user_id': user_id,
                'kcse_index': kcse_index,
                'email': email,
                'phone_number': formatted_phone,
                'created_at': datetime.now(),
                'payment_status': 'pending',
                'last_login': datetime.now(),
                'manual_activation': False
            }
            users_collection.insert_one(user_data)
        
        session['user_id'] = user_id
        session['kcse_index'] = kcse_index
        session['email'] = email
        
        is_local = request.host_url and ('localhost' in request.host_url or '127.0.0.1' in request.host_url)
        
        if is_local or not MPESA_CONFIG['consumer_key']:
            checkout_request_id = f'SIM_{user_id}_{int(time.time())}'
            mpesa_receipt = f'SIM{random.randint(100000, 999999)}'
            
            payment_data = {
                'transaction_id': str(uuid.uuid4()),
                'user_id': user_id,
                'kcse_index': kcse_index,
                'phone_number': formatted_phone,
                'amount': PAYMENT_AMOUNT,
                'mpesa_request_id': checkout_request_id,
                'status': 'completed',
                'mpesa_receipt': mpesa_receipt,
                'created_at': datetime.now(),
                'simulated': True
            }
            payments_collection.insert_one(payment_data)
            
            users_collection.update_one(
                {'user_id': user_id},
                {'$set': {'payment_status': 'completed', 'payment_receipt': mpesa_receipt}}
            )
            
            return jsonify({
                'success': True,
                'message': 'Registration successful (Test Mode)',
                'user_id': user_id,
                'can_calculate': True,
                'simulation_mode': True
            })
        
        payment_response = initiate_stk_push(
            phone_number=formatted_phone,
            amount=PAYMENT_AMOUNT,
            account_reference=kcse_index,
            transaction_desc=PAYMENT_PURPOSE
        )
        
        if payment_response.get('ResponseCode') == '0':
            payment_data = {
                'transaction_id': str(uuid.uuid4()),
                'user_id': user_id,
                'kcse_index': kcse_index,
                'phone_number': formatted_phone,
                'amount': PAYMENT_AMOUNT,
                'mpesa_request_id': payment_response.get('CheckoutRequestID'),
                'merchant_request_id': payment_response.get('MerchantRequestID'),
                'status': 'pending',
                'created_at': datetime.now()
            }
            payments_collection.insert_one(payment_data)
            
            users_collection.update_one(
                {'user_id': user_id},
                {'$set': {'checkout_request_id': payment_response.get('CheckoutRequestID')}}
            )
            
            return jsonify({
                'success': True,
                'message': 'Payment initiated successfully',
                'user_id': user_id,
                'checkout_request_id': payment_response.get('CheckoutRequestID'),
                'can_calculate': False
            })
        else:
            return jsonify({
                'success': False,
                'error': payment_response.get('ResponseDescription', 'Payment initiation failed')
            }), 400
            
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/callback', methods=['POST'])
def mpesa_callback():
    try:
        print("=" * 80)
        print(f"📞 M-PESA CALLBACK RECEIVED at {datetime.now().isoformat()}")
        
        raw_data = request.get_data(as_text=True)
        print(f"Raw data length: {len(raw_data)}")
        print(f"Raw data: {raw_data[:500]}")
        
        callback_id = str(uuid.uuid4())
        if db is not None:
            db.raw_callbacks.insert_one({
                'callback_id': callback_id,
                'raw_data': raw_data,
                'headers': dict(request.headers),
                'received_at': datetime.now(),
                'processed': False
            })
            print(f"✅ Raw callback saved with ID: {callback_id}")
        
        data = None
        
        try:
            data = request.get_json(force=True, silent=True)
            if data:
                print("✅ Parsed JSON successfully (method 1)")
        except Exception as e:
            print(f"⚠️ Method 1 failed: {e}")
        
        if not data and raw_data:
            try:
                import re
                json_match = re.search(r'\{.*\}', raw_data, re.DOTALL)
                if json_match:
                    cleaned_data = json_match.group()
                    data = json.loads(cleaned_data)
                    print("✅ Parsed JSON after cleaning (method 2)")
            except Exception as e:
                print(f"⚠️ Method 2 failed: {e}")
        
        if not data and raw_data:
            try:
                cleaned_data = raw_data.strip()
                last_brace = cleaned_data.rfind('}')
                if last_brace > 0:
                    cleaned_data = cleaned_data[:last_brace + 1]
                    data = json.loads(cleaned_data)
                    print("✅ Parsed JSON after trimming (method 3)")
            except Exception as e:
                print(f"⚠️ Method 3 failed: {e}")
        
        if not data:
            print("❌ Could not parse callback data")
            if db is not None:
                db.failed_callbacks.insert_one({
                    'callback_id': callback_id,
                    'raw_data': raw_data,
                    'error': 'JSON parse failed',
                    'received_at': datetime.now()
                })
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Received'})
        
        callback_data = None
        if 'Body' in data and 'stkCallback' in data['Body']:
            callback_data = data['Body']['stkCallback']
        elif 'stkCallback' in data:
            callback_data = data['stkCallback']
        
        if not callback_data:
            print("❌ Could not extract stkCallback from data")
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Received'})
        
        checkout_id = callback_data.get('CheckoutRequestID')
        merchant_id = callback_data.get('MerchantRequestID')
        result_code = callback_data.get('ResultCode')
        result_desc = callback_data.get('ResultDesc')
        
        print(f"\n📋 Callback Details:")
        print(f"  CheckoutRequestID: {checkout_id}")
        print(f"  MerchantRequestID: {merchant_id}")
        print(f"  ResultCode: {result_code}")
        print(f"  ResultDesc: {result_desc}")
        
        if not checkout_id and not merchant_id:
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Received'})
        
        payment_record = None
        
        if checkout_id:
            payment_record = payments_collection.find_one({'mpesa_request_id': checkout_id})
            if payment_record:
                print(f"✅ Found payment by CheckoutRequestID: {checkout_id}")
        
        if not payment_record and merchant_id:
            payment_record = payments_collection.find_one({'merchant_request_id': merchant_id})
            if payment_record:
                print(f"✅ Found payment by MerchantRequestID: {merchant_id}")
        
        if not payment_record and callback_data.get('CallbackMetadata'):
            metadata = callback_data.get('CallbackMetadata', {})
            items = metadata.get('Item', [])
            for item in items:
                if item.get('Name') == 'PhoneNumber':
                    phone = item.get('Value', '')
                    payment_record = payments_collection.find_one({
                        'phone_number': {'$regex': phone[-9:]},
                        'status': 'pending'
                    }, sort=[('created_at', -1)])
                    if payment_record:
                        print(f"✅ Found payment by PhoneNumber: {phone}")
                        break
        
        if not payment_record:
            print(f"⚠️ Payment record not found")
            if db is not None:
                db.unmatched_callbacks.insert_one({
                    'callback_id': callback_id,
                    'checkout_request_id': checkout_id,
                    'merchant_request_id': merchant_id,
                    'result_code': result_code,
                    'result_desc': result_desc,
                    'full_data': data,
                    'raw_data': raw_data[:1000],
                    'received_at': datetime.now(),
                    'status': 'unmatched'
                })
            return jsonify({'ResultCode': 0, 'ResultDesc': 'Received'})
        
        print(f"✅ Found payment for user: {payment_record['user_id']}")
        
        if result_code == 0:
            print("💰 Processing successful payment...")
            
            metadata = callback_data.get('CallbackMetadata', {})
            items = metadata.get('Item', []) if isinstance(metadata, dict) else []
            
            payment_details = {}
            for item in items:
                if isinstance(item, dict):
                    if 'Name' in item and 'Value' in item:
                        payment_details[item['Name']] = item['Value']
            
            receipt = payment_details.get('MpesaReceiptNumber', '')
            transaction_date = str(payment_details.get('TransactionDate', ''))
            phone = str(payment_details.get('PhoneNumber', ''))
            amount = payment_details.get('Amount', PAYMENT_AMOUNT)
            
            print(f"💰 Payment Details:")
            print(f"  Receipt: {receipt}")
            print(f"  Date: {transaction_date}")
            print(f"  Phone: {phone}")
            print(f"  Amount: {amount}")
            
            payments_collection.update_one(
                {'_id': payment_record['_id']},
                {'$set': {
                    'status': 'completed',
                    'result_code': result_code,
                    'result_desc': result_desc,
                    'mpesa_receipt': receipt,
                    'transaction_date': transaction_date,
                    'phone_number': phone or payment_record.get('phone_number'),
                    'amount': amount,
                    'callback_received_at': datetime.now(),
                    'callback_id': callback_id,
                    'updated_at': datetime.now()
                }}
            )
            print(f"✅ Payment record updated")
            
            users_collection.update_one(
                {'user_id': payment_record['user_id']},
                {'$set': {
                    'payment_status': 'completed',
                    'payment_date': datetime.now(),
                    'payment_receipt': receipt,
                    'mpesa_phone': phone,
                    'updated_at': datetime.now()
                }}
            )
            print(f"✅ User {payment_record['user_id']} updated")
            
            if db is not None:
                db.raw_callbacks.update_one(
                    {'callback_id': callback_id},
                    {'$set': {
                        'processed': True,
                        'processed_at': datetime.now(),
                        'payment_id': str(payment_record['_id']),
                        'user_id': payment_record['user_id'],
                        'receipt': receipt
                    }}
                )
            
            print(f"🎉 PAYMENT COMPLETED SUCCESSFULLY!")
            print(f"   User: {payment_record['user_id']}")
            print(f"   Receipt: {receipt}")
            
        else:
            print(f"❌ Payment failed: {result_desc}")
            
            payments_collection.update_one(
                {'_id': payment_record['_id']},
                {'$set': {
                    'status': 'failed',
                    'result_code': result_code,
                    'result_desc': result_desc,
                    'callback_received_at': datetime.now(),
                    'updated_at': datetime.now()
                }}
            )
            
            if db is not None:
                db.raw_callbacks.update_one(
                    {'callback_id': callback_id},
                    {'$set': {
                        'processed': True,
                        'processed_at': datetime.now(),
                        'status': 'failed',
                        'result_desc': result_desc
                    }}
                )
        
        print("=" * 80)
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Success'})
        
    except Exception as e:
        print(f"❌ Callback error: {str(e)}")
        traceback.print_exc()
        
        if db is not None:
            db.callback_errors.insert_one({
                'error': str(e),
                'traceback': traceback.format_exc(),
                'received_at': datetime.now()
            })
        
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Received'})

@app.route('/check_payment/<checkout_request_id>')
def check_payment(checkout_request_id):
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        payment = payments_collection.find_one({
            'mpesa_request_id': checkout_request_id,
            'user_id': session['user_id']
        })
        
        if not payment:
            return jsonify({'success': False, 'error': 'Payment not found'}), 404
        
        if payment['status'] == 'completed':
            users_collection.update_one(
                {'user_id': session['user_id']},
                {'$set': {'payment_status': 'completed'}}
            )
            
            return jsonify({
                'success': True,
                'status': 'completed',
                'can_calculate': True,
                'mpesa_receipt': payment.get('mpesa_receipt', 'N/A')
            })
        
        return jsonify({
            'success': True,
            'status': payment['status'],
            'can_calculate': False
        })
        
    except Exception as e:
        logger.error(f"Check payment error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'error': 'Payment required',
                'redirect': True
            }), 402
        
        user = users_collection.find_one({'user_id': session['user_id']})
        
        if not user or user.get('payment_status') != 'completed':
            return jsonify({
                'success': False,
                'error': 'Payment required',
                'redirect': True
            }), 402
        
        data = request.json if request.is_json else request.form.to_dict()
        
        grades = {}
        subject_fields = [
            'mathematics', 'english', 'kiswahili', 'physics', 'chemistry', 'biology',
            'geography', 'history', 'cre', 'ire', 'hre', 'agriculture', 'computer',
            'arts', 'woodwork', 'metalwork', 'building', 'electronics', 'homescience',
            'french', 'german', 'arabic', 'kenya_sign_language', 'music', 'business'
        ]
        
        subjects_with_grades = 0
        for field in subject_fields:
            if field in data:
                grade = data[field]
                if grade and str(grade).strip():
                    grades[field] = str(grade).strip().upper()
                    subjects_with_grades += 1
        
        results = {}
        cluster_details = {}
        
        for cluster_id in range(1, 21):
            points, subjects_used, failures = calculate_cluster_points(grades, cluster_id)
            results[f'Cluster {cluster_id}'] = f"{points:.3f}"
            cluster_details[f'Cluster {cluster_id}'] = {
                'points': points,
                'description': CLUSTERS.get(cluster_id, {}).get('description', '')
            }
        
        aggregate_points, top_7_subjects = get_aggregate_points(grades)
        
        result_id = str(uuid.uuid4())
        result_data = {
            'result_id': result_id,
            'user_id': session['user_id'],
            'kcse_index': session.get('kcse_index'),
            'email': session.get('email'),
            'grades': grades,
            'results': results,
            'aggregate_points': aggregate_points,
            'top_7_subjects': [{'subject': s, 'points': p} for s, p in top_7_subjects],
            'calculated_at': datetime.now()
        }
        
        results_collection.insert_one(result_data)
        
        return jsonify({
            'success': True,
            'results': results,
            'details': cluster_details,
            'aggregate_points': aggregate_points,
            'top_7_subjects': result_data['top_7_subjects'],
            'result_id': result_id,
            'subjects_count': subjects_with_grades
        })
        
    except Exception as e:
        logger.error(f"Calculate error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/my_results')
def my_results():
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        user = users_collection.find_one({'user_id': session['user_id']})
        
        if not user:
            session.clear()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user_results = list(results_collection.find(
            {'user_id': session['user_id']},
            sort=[('calculated_at', -1)]
        ).limit(10))
        
        results_list = []
        for result in user_results:
            results_list.append({
                'result_id': result.get('result_id'),
                'calculated_at': result.get('calculated_at').isoformat() if result.get('calculated_at') else None,
                'aggregate_points': result.get('aggregate_points', 0)
            })
        
        return jsonify({
            'success': True,
            'kcse_index': user.get('kcse_index'),
            'email': user.get('email'),
            'payment_status': user.get('payment_status'),
            'can_calculate': user.get('payment_status') == 'completed',
            'results': results_list
        })
        
    except Exception as e:
        logger.error(f"My results error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/retrieve_results', methods=['POST'])
def retrieve_results():
    try:
        data = request.json
        kcse_index = data.get('kcse_index', '').strip()
        mpesa_receipt = data.get('mpesa_receipt', '').strip().upper()
        
        payment = payments_collection.find_one({
            'mpesa_receipt': mpesa_receipt,
            'kcse_index': kcse_index,
            'status': 'completed'
        })
        
        if not payment:
            return jsonify({
                'success': False,
                'error': 'No results found. Check your KCSE index and M-Pesa receipt.'
            }), 404
        
        latest_result = results_collection.find_one(
            {'user_id': payment['user_id']},
            sort=[('calculated_at', -1)]
        )
        
        if not latest_result:
            return jsonify({
                'success': False,
                'error': 'No calculation found. Please calculate first.'
            }), 404
        
        session['user_id'] = payment['user_id']
        session['kcse_index'] = kcse_index
        
        return jsonify({
            'success': True,
            'grades': latest_result.get('grades', {}),
            'results': latest_result.get('results', {}),
            'aggregate_points': latest_result.get('aggregate_points', 0),
            'top_7_subjects': latest_result.get('top_7_subjects', [])
        })
        
    except Exception as e:
        logger.error(f"Retrieve results error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

# ===== ADMIN ROUTES =====

ADMIN_CREDENTIALS = {
    'username': os.getenv('ADMIN_USERNAME', 'admin'),
    'password': os.getenv('ADMIN_PASSWORD', 'admin123')
}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_CREDENTIALS['username'] and password == ADMIN_CREDENTIALS['password']:
            session['admin_logged_in'] = True
            return redirect('/admin/dashboard')
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/api/stats')
@admin_required
def admin_stats():
    try:
        total_payments = payments_collection.count_documents({'status': 'completed'})
        total_amount = sum(p.get('amount', 0) for p in payments_collection.find({'status': 'completed'}))
        total_users = users_collection.count_documents({})
        paid_users = users_collection.count_documents({'payment_status': 'completed'})
        
        return jsonify({
            'success': True,
            'stats': {
                'total_payments': total_payments,
                'total_amount': total_amount,
                'total_users': total_users,
                'paid_users': paid_users,
                'pending_users': total_users - paid_users
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/users')
@admin_required
def admin_users():
    try:
        users = list(users_collection.find({}, sort=[('created_at', -1)]))
        for user in users:
            user['_id'] = str(user['_id'])
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
        
        return jsonify({'success': True, 'users': users})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/manual-payment', methods=['POST'])
@admin_required
def admin_manual_payment():
    try:
        data = request.json
        kcse_index = data.get('kcse_index', '').strip()
        email = data.get('email', '').strip().lower()
        mpesa_receipt = data.get('mpesa_receipt', '').strip().upper()
        phone_number = data.get('phone_number', '').strip()
        
        user = users_collection.find_one({
            '$or': [{'kcse_index': kcse_index}, {'email': email}]
        })
        
        if user:
            user_id = user['user_id']
            users_collection.update_one(
                {'user_id': user_id},
                {'$set': {
                    'payment_status': 'completed',
                    'payment_receipt': mpesa_receipt,
                    'manual_activation': True,
                    'activated_at': datetime.now(),
                    'phone_number': phone_number or user.get('phone_number')
                }}
            )
        else:
            user_id = str(uuid.uuid4())
            users_collection.insert_one({
                'user_id': user_id,
                'kcse_index': kcse_index,
                'email': email,
                'phone_number': phone_number,
                'created_at': datetime.now(),
                'payment_status': 'completed',
                'payment_receipt': mpesa_receipt,
                'manual_activation': True,
                'activated_at': datetime.now()
            })
        
        payments_collection.insert_one({
            'transaction_id': str(uuid.uuid4()),
            'user_id': user_id,
            'kcse_index': kcse_index,
            'mpesa_receipt': mpesa_receipt,
            'amount': data.get('amount', PAYMENT_AMOUNT),
            'status': 'completed',
            'manual_payment': True,
            'created_at': datetime.now()
        })
        
        return jsonify({'success': True, 'message': 'Manual payment added', 'user_id': user_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/user/<user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    try:
        users_collection.delete_one({'user_id': user_id})
        payments_collection.delete_many({'user_id': user_id})
        results_collection.delete_many({'user_id': user_id})
        pdfs_collection.delete_many({'user_id': user_id})
        return jsonify({'success': True, 'message': f'User {user_id} deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/failed-payments')
@admin_required
def admin_failed_payments():
    try:
        failed = list(payments_collection.find({'status': 'failed'}))
        for payment in failed:
            payment['_id'] = str(payment['_id'])
        return jsonify({'success': True, 'payments': failed})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/api/check-manual-payment', methods=['POST'])
def check_manual_payment():
    try:
        data = request.json
        identifier = data.get('identifier', '').strip().lower()
        
        if not identifier:
            return jsonify({'success': True, 'has_manual_payment': False})
        
        query = {}
        if '@' in identifier:
            query['email'] = identifier
        else:
            query['kcse_index'] = identifier
        
        query.update({
            'manual_activation': True,
            'manual_expired': {'$ne': True},
            'manual_used': {'$ne': True}
        })
        
        user = users_collection.find_one(query)
        
        if user:
            activated_at = user.get('activated_at')
            if activated_at and (datetime.now() - activated_at).days <= 30:
                return jsonify({
                    'success': True,
                    'has_manual_payment': True,
                    'user_id': user['user_id']
                })
        
        return jsonify({'success': True, 'has_manual_payment': False})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("KCSE Cluster Points Calculator - PRODUCTION READY")
    print("=" * 60)
    print(f"MongoDB: {'✅ Connected' if db is not None else '❌ Not connected'}")
    print(f"M-Pesa Environment: {MPESA_CONFIG['environment']}")
    print(f"Business Shortcode: {MPESA_CONFIG['business_shortcode']}")
    print(f"Callback URL: {MPESA_CONFIG['callback_url']}")
    print(f"Payment Amount: Ksh {PAYMENT_AMOUNT}")
    print("=" * 60)
    
    port = int(os.environ.get('PORT', 5000))
    is_render = os.environ.get('RENDER', False)
    
    if is_render:
        print("Running on Render - Use gunicorn")
    else:
        print(f"\nStarting server on http://0.0.0.0:{port}")
        print("Press CTRL+C to quit")
        print("=" * 60)
        
        try:
            from waitress import serve
            serve(app, host='0.0.0.0', port=port, threads=4)
        except ImportError:
            app.run(debug=True, host='0.0.0.0', port=port, use_reloader=False)