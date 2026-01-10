from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, timedelta
import math
import json
import os
import re
import uuid
import requests
import base64
import random
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# MongoDB Configuration
try:
    mongo_client = MongoClient(os.getenv('MONGODB_URI'), serverSelectionTimeoutMS=5000)
    mongo_client.server_info()  # Test connection
    db = mongo_client[os.getenv('DATABASE_NAME', 'kcse_calculator')]
    print("✅ MongoDB connected successfully!")
    users_collection = db['users']
    payments_collection = db['payments']
    results_collection = db['results']
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
        def find(self, *args, **kwargs):
            return []
    
    db = None
    users_collection = payments_collection = results_collection = DummyCollection()

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

# Grade to points mapping
GRADE_POINTS = {
    'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8,
    'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3,
    'D-': 2, 'E': 1
}

# Helper functions for KCSE calculation
def validate_kcse_index(kcse_index):
    """Validate KCSE index format: 12345678912/2024"""
    pattern = r'^\d{11}/\d{4}$'
    if re.match(pattern, kcse_index):
        index_part, year_part = kcse_index.split('/')
        year = int(year_part)
        current_year = datetime.now().year
        
        if 1980 <= year <= current_year + 1:
            return True, "Valid KCSE index"
    return False, "Invalid KCSE index format. Use: 12345678912/2024"

def validate_phone_number(phone):
    """Validate Kenyan phone number"""
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
    """Generate M-Pesa access token"""
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
        
        print(f"Access token response status: {response.status_code}")
        print(f"Access token response text: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            return data['access_token']
        else:
            print(f"Access token error: {response.status_code} - {response.text}")
            raise Exception(f"Failed to get access token: {response.text}")
    except Exception as e:
        print(f"Access token generation error: {str(e)}")
        raise

def initiate_stk_push(phone_number, amount, account_reference, transaction_desc):
    """Initiate STK Push payment"""
    try:
        access_token = generate_access_token()
        print(f"✅ Access token obtained: {access_token[:20]}...")
        
        if MPESA_CONFIG['environment'] == 'sandbox':
            url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        else:
            url = 'https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
        
        # Generate timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Generate password
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
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc
        }
        
        print(f"📤 STK Push payload to {url}:")
        print(json.dumps(payload, indent=2))
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response_data = response.json()
        
        print(f"📥 STK Push response:")
        print(json.dumps(response_data, indent=2))
        
        return response_data
        
    except Exception as e:
        print(f"❌ STK Push error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        
        # Validate input
        kcse_index = data.get('kcse_index', '').strip()
        email = data.get('email', '').strip().lower()
        phone_number = data.get('phone_number', '').strip()
        
        print(f"📝 Registration attempt:")
        print(f"  KCSE Index: {kcse_index}")
        print(f"  Email: {email}")
        print(f"  Phone: {phone_number}")
        
        # Validate KCSE index
        is_valid_index, index_msg = validate_kcse_index(kcse_index)
        if not is_valid_index:
            print(f"❌ Invalid KCSE index: {index_msg}")
            return jsonify({'success': False, 'error': index_msg}), 400
        
        # Validate email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            print(f"❌ Invalid email: {email}")
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        # Validate phone number
        is_valid_phone, formatted_phone = validate_phone_number(phone_number)
        if not is_valid_phone:
            print(f"❌ Invalid phone: {formatted_phone}")
            return jsonify({'success': False, 'error': formatted_phone}), 400
        
        print(f"✅ Input validation passed")
        
        # Check if user already exists
        existing_user = users_collection.find_one({
            '$or': [
                {'kcse_index': kcse_index},
                {'email': email}
            ]
        })
        
        if existing_user:
            print(f"⚠️  User already exists: {existing_user.get('user_id')}")
            # Check if already paid
            if existing_user.get('payment_status') == 'completed':
                session['user_id'] = existing_user['user_id']
                session['kcse_index'] = kcse_index
                session['email'] = email
                return jsonify({
                    'success': True,
                    'message': 'User already registered and paid',
                    'user_id': existing_user['user_id'],
                    'already_paid': True
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'User exists but payment not completed'
                }), 400
        
        # Create user record
        user_id = str(uuid.uuid4())
        user_data = {
            'user_id': user_id,
            'kcse_index': kcse_index,
            'email': email,
            'phone_number': formatted_phone,
            'created_at': datetime.now(),
            'payment_status': 'pending',
            'last_login': datetime.now()
        }
        
        users_collection.insert_one(user_data)
        print(f"✅ User created: {user_id}")
        
        # Initiate payment
        try:
            print(f"💰 Initiating STK Push payment...")
            payment_response = initiate_stk_push(
                phone_number=formatted_phone,
                amount=PAYMENT_AMOUNT,
                account_reference=kcse_index,
                transaction_desc=PAYMENT_PURPOSE
            )
            
            if payment_response.get('ResponseCode') == '0':
                # Save payment record
                transaction_id = str(uuid.uuid4())
                payment_data = {
                    'transaction_id': transaction_id,
                    'user_id': user_id,
                    'kcse_index': kcse_index,
                    'phone_number': formatted_phone,
                    'amount': PAYMENT_AMOUNT,
                    'mpesa_request_id': payment_response.get('CheckoutRequestID'),
                    'merchant_request_id': payment_response.get('MerchantRequestID'),
                    'status': 'pending',
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }
                
                payments_collection.insert_one(payment_data)
                print(f"✅ Payment record created: {transaction_id}")
                
                # Update user with checkout request ID
                users_collection.update_one(
                    {'user_id': user_id},
                    {'$set': {
                        'checkout_request_id': payment_response.get('CheckoutRequestID'),
                        'updated_at': datetime.now()
                    }}
                )
                
                # Store in session
                session['user_id'] = user_id
                session['kcse_index'] = kcse_index
                session['email'] = email
                session['checkout_request_id'] = payment_response.get('CheckoutRequestID')
                
                return jsonify({
                    'success': True,
                    'message': 'Payment initiated successfully',
                    'user_id': user_id,
                    'checkout_request_id': payment_response.get('CheckoutRequestID'),
                    'merchant_request_id': payment_response.get('MerchantRequestID'),
                    'response_description': payment_response.get('ResponseDescription')
                })
            else:
                error_msg = payment_response.get('ResponseDescription', 'Payment initiation failed')
                print(f"❌ Payment failed: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': f'Payment failed: {error_msg}'
                }), 400
                
        except Exception as e:
            print(f"❌ Payment initiation error: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'Payment initiation failed: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"❌ Registration error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check_payment/<checkout_request_id>')
def check_payment(checkout_request_id):
    """Check payment status"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        print(f"🔍 Checking payment status for: {checkout_request_id}")
        
        # Check in payments collection
        payment_record = payments_collection.find_one({
            'mpesa_request_id': checkout_request_id,
            'user_id': session['user_id']
        })
        
        if not payment_record:
            print(f"❌ Payment record not found")
            return jsonify({'success': False, 'error': 'Payment not found'}), 404
        
        print(f"📊 Payment status: {payment_record['status']}")
        
        if payment_record['status'] == 'completed':
            # Update user payment status
            users_collection.update_one(
                {'user_id': session['user_id']},
                {'$set': {
                    'payment_status': 'completed',
                    'payment_date': datetime.now(),
                    'updated_at': datetime.now()
                }}
            )
            
            return jsonify({
                'success': True,
                'status': 'completed',
                'message': 'Payment verified successfully',
                'can_calculate': True,
                'mpesa_receipt': payment_record.get('mpesa_receipt', 'N/A')
            })
        elif payment_record['status'] == 'failed':
            return jsonify({
                'success': False,
                'status': 'failed',
                'error': 'Payment failed. Please try again.'
            })
        else:
            return jsonify({
                'success': True,
                'status': 'pending',
                'message': 'Payment still pending...',
                'can_calculate': False
            })
            
    except Exception as e:
        print(f"❌ Check payment error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/callback', methods=['POST'])
def mpesa_callback():
    """M-Pesa payment callback endpoint"""
    try:
        data = request.get_json()
        print(f"📞 Callback received:")
        print(json.dumps(data, indent=2))
        
        if not data or 'Body' not in data or 'stkCallback' not in data['Body']:
            print("❌ Invalid callback data structure")
            return jsonify({'ResultCode': 1, 'ResultDesc': 'Invalid callback data'})
        
        callback_data = data['Body']['stkCallback']
        checkout_request_id = callback_data.get('CheckoutRequestID')
        result_code = callback_data.get('ResultCode')
        result_desc = callback_data.get('ResultDesc')
        
        print(f"📋 Callback details:")
        print(f"  CheckoutRequestID: {checkout_request_id}")
        print(f"  ResultCode: {result_code}")
        print(f"  ResultDesc: {result_desc}")
        
        if not checkout_request_id:
            print("❌ No CheckoutRequestID in callback")
            return jsonify({'ResultCode': 1, 'ResultDesc': 'Missing CheckoutRequestID'})
        
        # Find payment record
        payment_record = payments_collection.find_one({
            'mpesa_request_id': checkout_request_id
        })
        
        if not payment_record:
            print(f"❌ Payment record not found for CheckoutRequestID: {checkout_request_id}")
            return jsonify({'ResultCode': 1, 'ResultDesc': 'Payment record not found'})
        
        if result_code == 0:
            # Payment successful
            callback_metadata = callback_data.get('CallbackMetadata', {}).get('Item', [])
            
            # Extract payment details
            payment_details = {}
            for item in callback_metadata:
                if 'Name' in item and 'Value' in item:
                    payment_details[item['Name']] = item['Value']
            
            payment_update = {
                'status': 'completed',
                'result_code': result_code,
                'result_desc': result_desc,
                'mpesa_receipt': payment_details.get('MpesaReceiptNumber', ''),
                'transaction_date': payment_details.get('TransactionDate', ''),
                'phone_number': payment_details.get('PhoneNumber', ''),
                'amount': payment_details.get('Amount', PAYMENT_AMOUNT),
                'updated_at': datetime.now()
            }
            
            # Update payment record
            payments_collection.update_one(
                {'mpesa_request_id': checkout_request_id},
                {'$set': payment_update}
            )
            
            # Update user status
            users_collection.update_one(
                {'user_id': payment_record['user_id']},
                {'$set': {
                    'payment_status': 'completed',
                    'payment_date': datetime.now(),
                    'updated_at': datetime.now()
                }}
            )
            
            print(f"✅ Payment completed for user: {payment_record['user_id']}")
            print(f"   M-Pesa Receipt: {payment_details.get('MpesaReceiptNumber', 'N/A')}")
            
        else:
            # Payment failed
            payment_update = {
                'status': 'failed',
                'result_code': result_code,
                'result_desc': result_desc,
                'updated_at': datetime.now()
            }
            
            payments_collection.update_one(
                {'mpesa_request_id': checkout_request_id},
                {'$set': payment_update}
            )
            
            users_collection.update_one(
                {'user_id': payment_record['user_id']},
                {'$set': {
                    'payment_status': 'failed',
                    'updated_at': datetime.now()
                }}
            )
            
            print(f"❌ Payment failed for user: {payment_record['user_id']}")
            print(f"   Reason: {result_desc}")
        
        # Always return success to M-Pesa
        return jsonify({'ResultCode': 0, 'ResultDesc': 'Success'})
        
    except Exception as e:
        print(f"❌ Callback processing error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'ResultCode': 1, 'ResultDesc': f'Error: {str(e)}'})

@app.route('/my_results')
def my_results():
    """Check if user is logged in and paid"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        user = users_collection.find_one({'user_id': session['user_id']})
        
        if not user:
            session.clear()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'kcse_index': user.get('kcse_index'),
            'email': user.get('email'),
            'payment_status': user.get('payment_status', 'pending'),
            'can_calculate': user.get('payment_status') == 'completed'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/calculate', methods=['POST'])
def calculate():
    """Calculate cluster points (requires payment)"""
    try:
        # Check if user is authenticated
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Please register first'}), 401
        
        user_id = session['user_id']
        
        # Check payment status
        user = users_collection.find_one({'user_id': user_id})
        if not user or user.get('payment_status') != 'completed':
            return jsonify({
                'success': False,
                'error': 'Payment required. Please complete payment first.'
            }), 402  # Payment Required
        
        # Process calculation (simplified for testing)
        if request.is_json:
            data = request.json
        else:
            data = request.form.to_dict()
        
        print(f"🧮 Calculating cluster points for user: {user_id}")
        
        # Your cluster calculation logic here
        # For now, return mock results
        mock_results = {
            'success': True,
            'results': {},
            'details': {},
            'aggregate_points': 73,
            'top_7_subjects': [
                {'subject': 'mathematics', 'points': 12},
                {'subject': 'english', 'points': 10},
                {'subject': 'physics', 'points': 11},
                {'subject': 'chemistry', 'points': 10},
                {'subject': 'biology', 'points': 9},
                {'subject': 'history', 'points': 7},
                {'subject': 'geography', 'points': 6}
            ],
            'formula': 'Cluster Points = √((x/48) × (y/84)) × 48 - 3',
            'note': 'Payment verified. Results saved to your account.'
        }
        
        # Generate cluster results
        for i in range(1, 21):
            cluster_points = random.uniform(0, 48)
            mock_results['results'][f'Cluster {i}'] = f"{cluster_points:.3f}"
            mock_results['details'][f'Cluster {i}'] = {
                'description': f'Cluster {i} Description',
                'subjects_used': [
                    {'subject': 'mathematics', 'grade': 'A', 'points': 12},
                    {'subject': 'english', 'grade': 'B+', 'points': 10},
                    {'subject': 'physics', 'grade': 'A-', 'points': 11},
                    {'subject': 'chemistry', 'grade': 'B+', 'points': 10}
                ]
            }
        
        # Save results to database
        result_id = str(uuid.uuid4())
        result_data = {
            'result_id': result_id,
            'user_id': user_id,
            'kcse_index': session['kcse_index'],
            'email': session['email'],
            'results': mock_results['results'],
            'aggregate_points': mock_results['aggregate_points'],
            'top_7_subjects': mock_results['top_7_subjects'],
            'calculated_at': datetime.now(),
            'payment_status': 'verified'
        }
        
        results_collection.insert_one(result_data)
        
        # Update user with last calculation
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'last_calculation': datetime.now(),
                'calculation_count': user.get('calculation_count', 0) + 1,
                'updated_at': datetime.now()
            }}
        )
        
        print(f"✅ Calculation completed for user: {user_id}")
        
        return jsonify(mock_results)
        
    except Exception as e:
        print(f"❌ Calculation error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'mongo_connected': db is not None
    })

if __name__ == '__main__':
    print("=" * 60)
    print("KCSE Cluster Points Calculator")
    print("=" * 60)
    print(f"MongoDB: {'✅ Connected' if db is not None else '❌ Not connected'}")
    print(f"M-Pesa Environment: {MPESA_CONFIG['environment']}")
    print(f"Business Shortcode: {MPESA_CONFIG['business_shortcode']}")
    print(f"Callback URL: {MPESA_CONFIG['callback_url']}")
    print(f"Payment Amount: Ksh {PAYMENT_AMOUNT}")
    print("=" * 60)
    
    # Test M-Pesa credentials
    try:
        print("🔐 Testing M-Pesa access token...")
        token = generate_access_token()
        print(f"✅ M-Pesa access token test: SUCCESS")
        print(f"   Token prefix: {token[:20]}...")
    except Exception as e:
        print(f"❌ M-Pesa access token test: FAILED")
        print(f"   Error: {str(e)}")
        print("\n⚠️  IMPORTANT: M-Pesa integration may not work!")
        print("   Possible issues:")
        print("   1. Incorrect consumer key/secret")
        print("   2. IP not whitelisted in Daraja portal")
        print("   3. Invalid business shortcode")
        print("   4. Account not active")
    
    print("=" * 60)
    print("Starting server on http://0.0.0.0:5000")
    print("Press CTRL+C to quit")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)