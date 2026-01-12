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

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-this')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# MongoDB Configuration
try:
    mongo_client = MongoClient(os.getenv('MONGODB_URI'), serverSelectionTimeoutMS=5000)
    mongo_client.server_info()  # Test connection
    db = mongo_client[os.getenv('DATABASE_NAME', 'kcse_calculator')]
    print("✅ MongoDB connected successfully!")
    users_collection = db['users']
    payments_collection = db['payments']
    results_collection = db['results']
    pdfs_collection = db['pdfs']
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
        def delete_one(self, *args, **kwargs):
            return None
    
    db = None
    users_collection = payments_collection = results_collection = pdfs_collection = DummyCollection()

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

# Subject name mapping for normalization (form fields to internal names)
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
    # Aliases
    'mathematics_a': 'mathematics',
    'mathematics_b': 'mathematics',
    'home_science': 'homescience',
    'art': 'arts',
    'art_and_design': 'arts',
    'building_construction': 'building',
    'electricity': 'electronics',
    'electricity_electronics': 'electronics'
}

# Cluster definitions - CORRECTED VERSION
CLUSTERS = {
    1: {
        'name': 'Cluster 1',
        'description': 'Law',
        'requirements': [
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    2: {
        'name': 'Cluster 2',
        'description': 'Business and Hospitality Related',
        'requirements': [
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    3: {
        'name': 'Cluster 3',
        'description': 'Social Sciences And Arts',
        'requirements': [
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    4: {
        'name': 'Cluster 4',
        'description': 'Geosciences',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['biology', 'chemistry', 'geography'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    5: {
        'name': 'Cluster 5',
        'description': 'Engineering, Technology',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['chemistry'], 'type': 'specific', 'count': 1},
            {'subjects': ['biology', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    6: {
        'name': 'Cluster 6',
        'description': 'Architecture, Building Construction',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['2nd_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    7: {
        'name': 'Cluster 7',
        'description': 'Computing, IT related',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['2nd_group_ii', 'any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    8: {
        'name': 'Cluster 8',
        'description': 'Agribusiness',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['biology'], 'type': 'specific', 'count': 1},
            {'subjects': ['physics', 'chemistry'], 'type': 'specific', 'count': 1},
            {'subjects': ['3rd_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    9: {
        'name': 'Cluster 9',
        'description': 'General Sciences',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii'], 'type': 'group', 'count': 1},
            {'subjects': ['2nd_group_ii'], 'type': 'group', 'count': 1},
            {'subjects': ['3rd_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    10: {
        'name': 'Cluster 10',
        'description': 'Actuarial science',
        'requirements': [
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['2nd_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    11: {
        'name': 'Cluster 11',
        'description': 'Interior Design',
        'requirements': [
            {'subjects': ['chemistry'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['biology', 'homescience'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    12: {
        'name': 'Cluster 12',
        'description': 'Sport Science',
        'requirements': [
            {'subjects': ['biology', 'general_science'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['english', 'kiswahili', 'any_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    13: {
        'name': 'Cluster 13',
        'description': 'Medicine',
        'requirements': [
            {'subjects': ['biology'], 'type': 'specific', 'count': 1},
            {'subjects': ['chemistry'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'physics'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili', '3rd_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    14: {
        'name': 'Cluster 14',
        'description': 'History',
        'requirements': [
            {'subjects': [], 'type': 'special', 'group': 'III', 'min_grade': 'C+', 'count': 1},  # HAG – C+
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['any_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    15: {
        'name': 'Cluster 15',
        'description': 'Agriculture',
        'requirements': [
            {'subjects': ['biology'], 'type': 'specific', 'count': 1},
            {'subjects': ['chemistry'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'physics', 'geography'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili', '3rd_group_ii', 'any_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    16: {
        'name': 'Cluster 16',
        'description': 'Geography Focus',
        'requirements': [
            {'subjects': ['geography'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics'], 'type': 'specific', 'count': 1},
            {'subjects': ['any_group_ii'], 'type': 'group', 'count': 1},
            {'subjects': ['2nd_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    17: {
        'name': 'Cluster 17',
        'description': 'French and German',
        'requirements': [
            {'subjects': ['french', 'german'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii', 'any_group_iii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii', 'any_group_iv'], 'type': 'group', 'count': 1}
        ]
    },
    18: {
        'name': 'Cluster 18',
        'description': 'Music and Arts',
        'requirements': [
            {'subjects': ['music'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii', 'any_group_iii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iii', 'any_group_iv', '2nd_group_v'], 'type': 'group', 'count': 1}
        ]
    },
    19: {
        'name': 'Cluster 19',
        'description': 'Education Related',
        'requirements': [
            {'subjects': ['english'], 'type': 'specific', 'count': 1},
            {'subjects': ['mathematics', 'any_group_ii'], 'type': 'specific_or_group', 'count': 1},
            {'subjects': ['2nd_group_ii'], 'type': 'group', 'count': 1},
            {'subjects': ['kiswahili', '3rd_group_ii', '2nd_group_iii', 'any_group_iv', 'any_group_v'], 'type': 'specific_or_group', 'count': 1}
        ]
    },
    20: {
        'name': 'Cluster 20',
        'description': 'Religious Studies',
        'requirements': [
            {'subjects': ['cre', 'ire', 'hre'], 'type': 'specific', 'count': 1},
            {'subjects': ['english', 'kiswahili'], 'type': 'specific', 'count': 1},
            {'subjects': ['2nd_group_iii'], 'type': 'group', 'count': 1},
            {'subjects': ['any_group_ii', 'any_group_iv', 'any_group_v'], 'type': 'group', 'count': 1}
        ]
    }
}

# ===== HELPER FUNCTIONS =====

def normalize_subject_name(subject):
    """Normalize subject names to match form field names"""
    return SUBJECT_NAME_MAP.get(subject.lower(), subject.lower())

def get_subject_group(subject):
    """Determine which group a subject belongs to"""
    normalized = normalize_subject_name(subject)
    for group, subjects in SUBJECT_GROUPS.items():
        if normalized in subjects:
            return group
    return None

def get_group_subjects(group_name):
    """Get all subjects in a group"""
    return SUBJECT_GROUPS.get(group_name, [])

def get_best_subjects_by_group(grades, group_name, count=1, exclude_subjects=None):
    """Get best N subjects from a specific group, excluding already used subjects"""
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
    
    # Sort by points (descending)
    subject_points.sort(key=lambda x: x[1], reverse=True)
    
    # Return top N subjects
    return subject_points[:count]

def get_aggregate_points(grades):
    """
    Calculate Aggregate Points (AGP) - sum of best 7 subjects ONLY
    This is y in the formula: Cluster Points = sqrt((x/48) * (y/84)) * 48
    """
    all_points = []
    
    # Collect all subjects with valid grades
    for subject, grade in grades.items():
        if grade:
            points = GRADE_POINTS.get(grade, 0)
            all_points.append((subject, points))
    
    # Sort by points (descending)
    all_points.sort(key=lambda x: x[1], reverse=True)
    
    # Take top 7 only - FIXED: Always take exactly top 7 or less
    top_7 = all_points[:7]
    
    # Calculate sum of points for top 7 subjects
    total_points = sum(p for _, p in top_7)
    
    return total_points, top_7

def calculate_cluster_points(grades, cluster_id, debug=False):
    """
    Calculate cluster points using the formula:
    Cluster Points = sqrt((x/48) * (y/84)) * 48
    
    Where:
    x = sum of points in the 4 required cluster subjects (must be unique subjects)
    y = Aggregate Points (AGP) = sum of the best 7 subjects (can include cluster subjects)
    48 = maximum points possible in 4 subjects (12 × 4)
    84 = maximum points possible in 7 subjects (12 × 7)
    
    Returns: (points, subjects_used, requirement_failures)
    """
    cluster = CLUSTERS.get(cluster_id)
    if not cluster:
        if debug:
            print(f"Cluster {cluster_id} not found")
        return 0.000, [], ["Cluster not found"]
    
    cluster_subjects_points = 0
    subjects_used = []
    requirement_failures = []
    
    for req_index, requirement in enumerate(cluster['requirements']):
        req_type = requirement.get('type', 'specific')
        req_subjects = requirement.get('subjects', [])
        req_count = requirement.get('count', 1)
        
        # Handle special requirements first (Cluster 14 - HAG C+)
        if req_type == 'special' and cluster_id == 14 and req_index == 0:
            # HAG – C+ requirement - best Group III subject with at least C+
            best_group_iii = get_best_subjects_by_group(grades, 'Group III', 1)
            
            if best_group_iii and best_group_iii[0][1] >= GRADE_POINTS.get('C+', 0):
                subject, points, grade = best_group_iii[0]
                cluster_subjects_points += points
                subjects_used.append({
                    'subject': subject,
                    'grade': grade,
                    'points': points,
                    'requirement': 'HAG C+ (Group III)',
                    'group': 'Group III',
                    'requirement_index': req_index + 1
                })
            else:
                requirement_failures.append(f"Requirement 1: No Group III subject with C+ or better")
                return 0.000, subjects_used, requirement_failures
            continue
        
        # For each requirement, we need to find subjects
        found_subjects = []
        found_points = 0
        
        # Track subjects that have been considered in this requirement
        considered_subjects = [s['subject'] for s in subjects_used]
        
        # Check specific subjects first
        if req_type in ['specific', 'specific_or_group']:
            for subject_option in req_subjects:
                normalized_option = normalize_subject_name(subject_option)
                
                # Check if this specific subject is available
                if normalized_option in grades and grades[normalized_option]:
                    # Check if subject is already used
                    if normalized_option in considered_subjects:
                        continue
                    
                    points = GRADE_POINTS.get(grades[normalized_option], 0)
                    found_subjects.append({
                        'subject': normalized_option,
                        'grade': grades[normalized_option],
                        'points': points,
                        'requirement': f"Specific: {subject_option}",
                        'group': get_subject_group(normalized_option),
                        'requirement_index': req_index + 1
                    })
                    found_points += points
                    considered_subjects.append(normalized_option)
                    
                    if len(found_subjects) >= req_count:
                        break
        
        # If not enough specific subjects found, check group requirements
        if len(found_subjects) < req_count and req_type in ['group', 'specific_or_group']:
            for subject_option in req_subjects:
                # Handle group patterns
                if subject_option.startswith('any_group_'):
                    parts = subject_option.split('_')
                    if len(parts) >= 3:
                        group_num = parts[2].upper()
                        group_name = f'Group {group_num}'
                        
                        # Get best subjects from this group (excluding already considered ones)
                        available = get_best_subjects_by_group(grades, group_name, 
                                                             req_count - len(found_subjects), 
                                                             considered_subjects)
                        
                        for subject, points, grade in available:
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"Group {group_num}: {subject_option}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                            
                            if len(found_subjects) >= req_count:
                                break
                        if len(found_subjects) >= req_count:
                            break
                
                elif subject_option.startswith('2nd_group_'):
                    parts = subject_option.split('_')
                    if len(parts) >= 3:
                        group_num = parts[2].upper()
                        group_name = f'Group {group_num}'
                        
                        # Get best subjects from this group
                        all_in_group = get_best_subjects_by_group(grades, group_name, 10, considered_subjects)
                        
                        if len(all_in_group) >= 2:
                            # Take the 2nd best
                            subject, points, grade = all_in_group[1]
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"2nd Group {group_num}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                        elif len(all_in_group) == 1:
                            subject, points, grade = all_in_group[0]
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"Only available from Group {group_num}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                
                elif subject_option.startswith('3rd_group_'):
                    parts = subject_option.split('_')
                    if len(parts) >= 3:
                        group_num = parts[2].upper()
                        group_name = f'Group {group_num}'
                        
                        # Get best subjects from this group
                        all_in_group = get_best_subjects_by_group(grades, group_name, 10, considered_subjects)
                        
                        if len(all_in_group) >= 3:
                            # Take the 3rd best
                            subject, points, grade = all_in_group[2]
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"3rd Group {group_num}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                        elif len(all_in_group) == 2:
                            subject, points, grade = all_in_group[1]
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"2nd best from Group {group_num}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                        elif len(all_in_group) == 1:
                            subject, points, grade = all_in_group[0]
                            found_subjects.append({
                                'subject': subject,
                                'grade': grade,
                                'points': points,
                                'requirement': f"Only available from Group {group_num}",
                                'group': group_name,
                                'requirement_index': req_index + 1
                            })
                            found_points += points
                            considered_subjects.append(subject)
                
                # If we found enough subjects, break the loop
                if len(found_subjects) >= req_count:
                    break
        
        # Check if requirement was satisfied
        if len(found_subjects) >= req_count:
            subjects_used.extend(found_subjects)
            cluster_subjects_points += found_points
        else:
            requirement_failures.append(
                f"Requirement {req_index + 1}: Could not satisfy {req_subjects}"
            )
            return 0.000, subjects_used, requirement_failures
    
    # Ensure we have exactly 4 subjects (except for Cluster 14 which has special handling)
    expected_count = 4
    
    if len(subjects_used) != expected_count:
        requirement_failures.append(f"Wrong number of subjects: {len(subjects_used)} instead of {expected_count}")
        return 0.000, subjects_used, requirement_failures
    
    # Calculate Aggregate Points (AGP) - sum of best 7 subjects
    aggregate_points, top_7_subjects = get_aggregate_points(grades)
    
    # Apply the formula
    x = cluster_subjects_points
    y = aggregate_points
    
    if x <= 0 or y <= 0:
        requirement_failures.append(f"Invalid points calculation: x={x}, y={y}")
        return 0.000, subjects_used, requirement_failures
    
    try:
        # Calculate using the formula: sqrt((x/48) * (y/84)) * 48
        cluster_points = math.sqrt((x / 48.0) * (y / 84.0)) * 48.0
        
        # Cap at 48 (maximum possible)
        cluster_points = min(cluster_points, 48.0)
        
        # Apply -3 deviation
        cluster_points_with_deviation = max(0.000, cluster_points - 3.0)
        
        # Round to 3 decimal places
        cluster_points = round(cluster_points, 3)
        cluster_points_with_deviation = round(cluster_points_with_deviation, 3)
        
        return cluster_points_with_deviation, subjects_used, []
    except Exception as e:
        requirement_failures.append(f"Calculation error: {str(e)}")
        return 0.000, subjects_used, requirement_failures

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

# ===== ROUTES =====

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

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
        
        user_id = None
        
        if existing_user:
            print(f"⚠️  User already exists: {existing_user.get('user_id')}")
            user_id = existing_user['user_id']
            
            # Check if already paid
            if existing_user.get('payment_status') == 'completed':
                session['user_id'] = user_id
                session['kcse_index'] = kcse_index
                session['email'] = email
                return jsonify({
                    'success': True,
                    'message': 'User already registered and paid',
                    'user_id': user_id,
                    'already_paid': True
                })
            else:
                # Update user with new phone number if changed
                users_collection.update_one(
                    {'user_id': user_id},
                    {'$set': {
                        'phone_number': formatted_phone,
                        'updated_at': datetime.now()
                    }}
                )
        else:
            # Create new user record
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
        
        # Store in session
        session['user_id'] = user_id
        session['kcse_index'] = kcse_index
        session['email'] = email
        
        # Check if we're running locally for testing
        is_local = request.host_url and ('localhost' in request.host_url or '127.0.0.1' in request.host_url)
        
        if is_local:
            print(f"🌐 LOCALHOST DETECTED - Using simulation mode")
            
            # Create a simulated checkout request ID
            checkout_request_id = f'LOCAL_TEST_{user_id}_{int(datetime.now().timestamp())}'
            
            # Save simulated payment record with immediate completion
            transaction_id = str(uuid.uuid4())
            mpesa_receipt = f'TEST{random.randint(100000, 999999)}'
            
            payment_data = {
                'transaction_id': transaction_id,
                'user_id': user_id,
                'kcse_index': kcse_index,
                'phone_number': formatted_phone,
                'amount': PAYMENT_AMOUNT,
                'mpesa_request_id': checkout_request_id,
                'merchant_request_id': f'LOCAL_MERCHANT_{user_id}',
                'status': 'completed',
                'result_code': 0,
                'result_desc': 'Success (Simulated for Local Testing)',
                'mpesa_receipt': mpesa_receipt,
                'transaction_date': datetime.now().strftime('%Y%m%d%H%M%S'),
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            payments_collection.insert_one(payment_data)
            
            # Update user with checkout request ID and payment status
            users_collection.update_one(
                {'user_id': user_id},
                {'$set': {
                    'checkout_request_id': checkout_request_id,
                    'payment_status': 'completed',
                    'payment_date': datetime.now(),
                    'payment_receipt': mpesa_receipt,
                    'updated_at': datetime.now()
                }}
            )
            
            session['checkout_request_id'] = checkout_request_id
            
            print(f"✅ Local payment simulation complete for user: {user_id}")
            
            return jsonify({
                'success': True,
                'message': 'Registration and payment simulation successful',
                'user_id': user_id,
                'checkout_request_id': checkout_request_id,
                'local_test_mode': True,
                'payment_simulated': True,
                'can_calculate': True
            })
        
        # PRODUCTION: Initiate actual M-Pesa payment
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
                    'payment_receipt': payment_record.get('mpesa_receipt', ''),
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
                    'payment_receipt': payment_details.get('MpesaReceiptNumber', ''),
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
    """Check if user is logged in and paid, and show saved results"""
    try:
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        
        user = users_collection.find_one({'user_id': session['user_id']})
        
        if not user:
            session.clear()
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Get user's calculation history
        user_results = list(results_collection.find(
            {'user_id': session['user_id']},
            sort=[('calculated_at', -1)]
        ).limit(10))
        
        # Get PDF history
        user_pdfs = list(pdfs_collection.find(
            {'user_id': session['user_id']},
            sort=[('created_at', -1)]
        ).limit(10))
        
        results_list = []
        for result in user_results:
            results_list.append({
                'result_id': result.get('result_id'),
                'calculated_at': result.get('calculated_at', datetime.now()).isoformat(),
                'aggregate_points': result.get('aggregate_points', 0),
                'has_pdf': any(pdf.get('result_id') == result.get('result_id') for pdf in user_pdfs)
            })
        
        return jsonify({
            'success': True,
            'kcse_index': user.get('kcse_index'),
            'email': user.get('email'),
            'payment_status': user.get('payment_status', 'pending'),
            'can_calculate': user.get('payment_status') == 'completed',
            'calculation_count': len(user_results),
            'results': results_list,
            'pdf_count': len(user_pdfs)
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
        # First, check if we have grades data
        if request.is_json:
            data = request.json
        else:
            data = request.form.to_dict()
        
        # Check if user is logged in and has paid
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'error': 'Payment required. Please register and pay first.',
                'redirect': True,
                'redirect_url': '/'
            }), 402  # Payment Required
        
        user_id = session['user_id']
        
        # Check payment status
        user = users_collection.find_one({'user_id': user_id})
        if not user or user.get('payment_status') != 'completed':
            return jsonify({
                'success': False,
                'error': 'Payment required. Please complete payment first.',
                'redirect': True,
                'redirect_url': '/'
            }), 402  # Payment Required
        
        # Process calculation (only if paid)
        grades = {}
        
        # All possible subject fields
        subject_fields = [
            'mathematics', 'english', 'kiswahili', 'physics', 'chemistry', 'biology',
            'geography', 'history', 'cre', 'ire', 'hre', 'agriculture', 'computer',
            'arts', 'woodwork', 'metalwork', 'building', 'electronics', 'homescience',
            'french', 'german', 'arabic', 'kenya_sign_language', 'music', 'business',
            'aviation', 'general_science', 'drawing_design', 'power_mechanics'
        ]
        
        # Extract and normalize grades
        subjects_with_grades = 0
        for field in subject_fields:
            if field in data:
                grade = data[field]
                if grade and str(grade).strip() and str(grade).strip().upper() != 'SELECT GRADE':
                    grades[field] = str(grade).strip().upper()
                    subjects_with_grades += 1
                else:
                    grades[field] = None
        
        # Log all grades received
        print(f"📊 Calculating for user: {user_id}")
        print(f"Subjects with grades: {subjects_with_grades}")
        print(f"Grades received: {grades}")
        
        # Calculate points for all clusters
        results = {}
        cluster_details = {}
        
        for cluster_id in range(1, 21):
            points, subjects_used, failures = calculate_cluster_points(grades, cluster_id, debug=False)
            results[f'Cluster {cluster_id}'] = f"{points:.3f}"
            
            cluster_details[f'Cluster {cluster_id}'] = {
                'points': points,
                'subjects_used': subjects_used,
                'failures': failures,
                'description': CLUSTERS[cluster_id]['description']
            }
        
        # Calculate aggregate points
        aggregate_points, top_7_subjects = get_aggregate_points(grades)
        
        # Save results to database
        result_id = str(uuid.uuid4())
        result_data = {
            'result_id': result_id,
            'user_id': user_id,
            'kcse_index': session.get('kcse_index', 'N/A'),
            'email': session.get('email', 'N/A'),
            'grades': grades,
            'results': results,
            'aggregate_points': aggregate_points,
            'top_7_subjects': [{'subject': s, 'points': p} for s, p in top_7_subjects],
            'calculated_at': datetime.now(),
            'payment_status': 'verified',
            'mpesa_receipt': user.get('payment_receipt', 'N/A')
        }
        
        results_collection.insert_one(result_data)
        
        print(f"✅ Calculation complete for user: {user_id}")
        print(f"Result ID: {result_id}")
        print(f"Aggregate Points: {aggregate_points}")
        
        return jsonify({
            'success': True,
            'results': results,
            'details': cluster_details,
            'aggregate_points': aggregate_points,
            'top_7_subjects': [{'subject': s, 'points': p} for s, p in top_7_subjects],
            'subjects_count': subjects_with_grades,
            'formula': 'Cluster Points = √((x/48) × (y/84)) × 48 - 3',
            'note': 'x = sum of 4 unique cluster subjects, y = aggregate points (best 7 subjects)',
            'deviation_note': 'A -3 deviation has been applied to all cluster points',
            'warning': 'At least 7 subjects needed for accurate calculation' if subjects_with_grades < 7 else None,
            'result_id': result_id,
            'payment_verified': True,
            'mpesa_receipt': user.get('payment_receipt', 'N/A'),
            'user_info': {
                'kcse_index': session.get('kcse_index'),
                'email': session.get('email')
            }
        })
        
    except Exception as e:
        print(f"❌ ERROR in calculate: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/retrieve_results', methods=['POST'])
def retrieve_results():
    """Retrieve results using KCSE index and M-Pesa receipt"""
    try:
        data = request.json
        
        kcse_index = data.get('kcse_index', '').strip()
        mpesa_receipt = data.get('mpesa_receipt', '').strip().upper()
        
        print(f"🔍 Retrieving results for: {kcse_index}, Receipt: {mpesa_receipt}")
        
        # Validate KCSE index
        is_valid_index, index_msg = validate_kcse_index(kcse_index)
        if not is_valid_index:
            return jsonify({'success': False, 'error': index_msg}), 400
        
        # Find payment with this receipt and KCSE index
        payment_record = payments_collection.find_one({
            'mpesa_receipt': mpesa_receipt,
            'kcse_index': kcse_index,
            'status': 'completed'
        })
        
        if not payment_record:
            return jsonify({
                'success': False, 
                'error': 'No results found. Please check your KCSE index and M-Pesa receipt number.'
            }), 404
        
        user_id = payment_record.get('user_id')
        
        # Find user
        user = users_collection.find_one({'user_id': user_id})
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Find latest results for this user
        latest_result = results_collection.find_one(
            {'user_id': user_id},
            sort=[('calculated_at', -1)]
        )
        
        if not latest_result:
            return jsonify({
                'success': False, 
                'error': 'No calculation found for this payment. Please calculate first.'
            }), 404
        
        # Store user in session
        session['user_id'] = user_id
        session['kcse_index'] = kcse_index
        session['email'] = user.get('email', '')
        
        return jsonify({
            'success': True,
            'message': 'Results retrieved successfully',
            'kcse_index': kcse_index,
            'email': user.get('email', ''),
            'user_id': user_id,
            'grades': latest_result.get('grades', {}),
            'results': latest_result.get('results', {}),
            'aggregate_points': latest_result.get('aggregate_points', 0),
            'top_7_subjects': latest_result.get('top_7_subjects', []),
            'calculated_at': latest_result.get('calculated_at').isoformat() if latest_result.get('calculated_at') else None,
            'payment_verified': True,
            'mpesa_receipt': mpesa_receipt
        })
        
    except Exception as e:
        print(f"❌ Retrieve results error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    is_local = request.host_url and ('localhost' in request.host_url or '127.0.0.1' in request.host_url)
    
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'mongo_connected': db is not None,
        'mpesa_environment': MPESA_CONFIG['environment'],
        'is_local': is_local,
        'callback_url': MPESA_CONFIG['callback_url'],
        'payment_amount': PAYMENT_AMOUNT,
        'features': {
            'pdf_generation': True,
            'mpesa_payments': True,
            'results_storage': True,
            'user_accounts': True,
            'cluster_calculation': True,
            'fixed_group_logic': True
        }
    })
# ===== ADMIN SETUP =====

# Admin credentials
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



if __name__ == '__main__':
    print("=" * 60)
    print("KCSE Cluster Points Calculator - COMPLETE FIXED VERSION")
    print("=" * 60)
    print(f"MongoDB: {'✅ Connected' if db is not None else '❌ Not connected'}")
    print(f"M-Pesa Environment: {MPESA_CONFIG['environment']}")
    print(f"Business Shortcode: {MPESA_CONFIG['business_shortcode']}")
    print(f"Callback URL: {MPESA_CONFIG['callback_url']}")
    print(f"Payment Amount: Ksh {PAYMENT_AMOUNT}")
    print("=" * 60)
    print("\n📍 NEW FLOW:")
    print("   Step 1: User enters KCSE grades")
    print("   Step 2: User enters index, email, phone")
    print("   Step 3: Payment (Ksh 100 via M-Pesa)")
    print("   Step 4: Automatic calculation and results display")
    print("=" * 60)
    print("\n📍 DATA STORED IN MONGODB:")
    print("   1. Users collection: email, index, phone, payment status")
    print("   2. Payments collection: M-Pesa receipt, amount, status")
    print("   3. Results collection: grades, cluster points, aggregate")
    print("   4. PDFs collection: Generated PDF reports")
    print("=" * 60)
    print("\n📍 ENDPOINTS:")
    print("   /                 - Home page with 4-step flow")
    print("   /register         - User registration & payment")
    print("   /calculate        - Calculate cluster points (after payment)")
    print("   /check_payment/   - Check payment status")
    print("   /retrieve_results - Retrieve results with index & receipt")
    print("   /my_results       - View calculation history")
    print("   /logout           - Logout user")
    print("   /health           - System health check")
    print("=" * 60)
    print("\nStarting server on http://0.0.0.0:5000")
    print("Press CTRL+C to quit")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)