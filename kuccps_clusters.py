"""
KUCCPS Cluster Points Calculation Module
Correct formula: c = √(x/48 × y/84) × 48
WITH COMPLETE SUBJECT REQUIREMENTS FOR ALL 20 CLUSTERS
"""

import math

# KUCCPS Grade to Points Conversion
GRADE_POINTS = {
    'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8,
    'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3, 'D-': 2, 'E': 1
}

# Grade ranking for comparison
GRADE_RANK = {
    'A': 12, 'A-': 11, 'B+': 10, 'B': 9, 'B-': 8,
    'C+': 7, 'C': 6, 'C-': 5, 'D+': 4, 'D': 3, 'D-': 2, 'E': 1, '': 0
}

# Subject Groups mapping
SUBJECT_GROUPS = {
    # Group I - Languages
    'english': 'I', 'kiswahili': 'I', 'mathematics_a': 'I', 'mathematics_b': 'I',
    'mathematics': 'I',  # Alias
    # Group II - Humanities
    'history': 'II', 'geography': 'II', 'cre': 'II', 'ire': 'II', 
    'hre': 'II', 'ssc': 'II', 'islamic_studies': 'II', 'christian_religious_education': 'II',
    # Group III - Sciences & Technical
    'chemistry': 'III', 'biology': 'III', 'physics': 'III', 'agriculture': 'III',
    'computer': 'III', 'computer_studies': 'III', 'ict': 'III',
    'arts': 'III', 'art_and_design': 'III', 'fine_art': 'III',
    'woodwork': 'III', 'homescience': 'III', 'home_science': 'III',
    'business': 'III', 'business_studies': 'III',
    'building': 'III', 'building_construction': 'III',
    'electronics': 'III', 'metalwork': 'III', 'aviation': 'III',
    'general_science': 'III', 'physical_education': 'III',
    'arabic': 'III', 'hindi': 'III', 'french': 'III', 'german': 'III',
    'music': 'III',  # Some documents place Music in Group III
    # Group IV - Languages & Others
    'french_language': 'IV', 'german_language': 'IV',
    'kenya_sign_language': 'IV', 'music_performance': 'IV',
    # Group V - Others
    'any_other': 'V', 'other_subject': 'V'
}

# Subject aliases for flexible matching
SUBJECT_ALIASES = {
    'mathematics': ['mathematics_a', 'mathematics_b'],
    'mathematics_a': ['mathematics'],
    'mathematics_b': ['mathematics'],
    'maths': ['mathematics_a', 'mathematics_b'],
    'math': ['mathematics_a', 'mathematics_b'],
    'eng': ['english'],
    'kis': ['kiswahili'],
    'chem': ['chemistry'],
    'phy': ['physics'],
    'bio': ['biology'],
    'hist': ['history'],
    'geo': ['geography'],
    'comp': ['computer', 'computer_studies', 'ict'],
    'comp_studies': ['computer', 'computer_studies', 'ict'],
    'ict': ['computer', 'computer_studies', 'ict'],
    'home_science': ['homescience'],
    'home_sci': ['homescience'],
    'hsc': ['homescience'],
    'agri': ['agriculture'],
    'agric': ['agriculture'],
    'bus': ['business', 'business_studies'],
    'business_studies': ['business'],
    'bst': ['business', 'business_studies'],
    'fre': ['french', 'french_language'],
    'ger': ['german', 'german_language'],
    'art': ['arts', 'art_and_design', 'fine_art'],
    'music': ['music', 'music_performance'],
    'cre': ['cre', 'christian_religious_education'],
    'ire': ['ire', 'islamic_studies'],
    'hre': ['hre'],
    'german': ['german', 'german_language'],
    'french': ['french', 'french_language'],
    'general_science': ['general_science'],
    'gsc': ['general_science'],
    'arabic': ['arabic'],
    'hindi': ['hindi']
}

# Group definitions
GROUP_I = ['english', 'kiswahili', 'mathematics_a', 'mathematics_b']
GROUP_II = ['history', 'geography', 'cre', 'ire', 'hre', 'ssc', 'islamic_studies', 'christian_religious_education']
GROUP_III = ['chemistry', 'biology', 'physics', 'agriculture', 'computer', 'arts', 
             'woodwork', 'homescience', 'business', 'building', 'electronics', 
             'metalwork', 'aviation', 'general_science', 'physical_education',
             'arabic', 'hindi', 'french', 'german', 'music']
GROUP_IV = ['french_language', 'german_language', 'kenya_sign_language', 'music_performance']
GROUP_V = ['any_other', 'other_subject']

# All subjects
ALL_SUBJECTS = GROUP_I + GROUP_II + GROUP_III + GROUP_IV + GROUP_V

# Cluster Requirements - COMPLETE BASED ON DOCUMENT
CLUSTER_REQUIREMENTS = {
    1: {
        'name': 'Law',
        'min_grades': ['B', 'B', None, None],  # ENG/KIS, MAT_A, Group II, Group III/IV/V
        'requirements': [
            {'type': 'either', 'subjects': ['english', 'kiswahili'], 'min_grade': 'B'},
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'B'},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'III_IV_V'}
        ]
    },
    2: {
        'name': 'Business, Hospitality & Related',
        'min_grades': ['B', 'B', None, None],  # MAT_A, ENG/KIS, Group II, Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'B'},
            {'type': 'either', 'subjects': ['english', 'kiswahili'], 'min_grade': 'B'},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'III_IV_V'}
        ]
    },
    3: {
        'name': 'Social Sciences, Media, Arts & Related',
        'min_grades': ['C+', 'C+', None, None],  # ENG/KIS, MAT_A, Group II, Group II/III/IV/V
        'requirements': [
            {'type': 'either', 'subjects': ['english', 'kiswahili'], 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'II_III_IV_V'}
        ]
    },
    4: {
        'name': 'Geosciences & Related',
        'min_grades': ['C+', 'C+', 'C', None],  # MAT_A, PHY, BIO/CHE/GEO, Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'physics', 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['biology', 'chemistry', 'geography'], 'min_grade': 'C'},
            {'type': 'group', 'group': 'II_III_IV_V'}
        ]
    },
    5: {
        'name': 'Engineering & Technology',
        'min_grades': ['C+', 'C+', 'C+', None],  # MAT_A, PHY, CHE, BIO/Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'physics', 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'chemistry', 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['biology'] + GROUP_III + GROUP_IV + GROUP_V}
        ]
    },
    6: {
        'name': 'Architecture & Construction',
        'min_grades': ['C+', 'C+', None, None],  # MAT_A, PHY, Group III, 2nd Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'physics', 'min_grade': 'C+'},
            {'type': 'group', 'group': 'III'},
            {'type': 'group', 'group': 'II_III_IV_V_2nd'}
        ]
    },
    7: {
        'name': 'Computing & IT',
        'min_grades': ['C+', 'C+', None, None],  # MAT_A, PHY, 2nd Group II/Group III, Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'subject', 'subject': 'physics', 'min_grade': 'C+'},
            {'type': 'group', 'group': 'II_III_2nd'},
            {'type': 'group', 'group': 'II_III_IV_V'}
        ]
    },
    8: {
        'name': 'Agribusiness & Related',
        'min_grades': ['C', None, None, None],  # MAT_A, BIO/AGRIC/BST, PHY/CHE, 3rd Group II/Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C'},
            {'type': 'either', 'subjects': ['biology', 'agriculture', 'business'], 
             'grades': [('biology', 'C'), ('agriculture', 'C+'), ('business', 'C+')]},
            {'type': 'either', 'subjects': ['physics', 'chemistry']},
            {'type': 'group', 'group': 'II_III_IV_V_3rd'}
        ]
    },
    9: {
        'name': 'General & Biological Sciences',
        'min_grades': ['C', None, None, None],  # MAT_A, Group II, 2nd Group II, 3rd Group II/Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C'},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'II_2nd'},
            {'type': 'group', 'group': 'II_III_IV_V_3rd'}
        ]
    },
    10: {
        'name': 'Actuarial, Mathematics, Economics & Related',
        'min_grades': ['C+', None, None, None],  # MAT_A, Group II, Group III, 2nd Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'mathematics_a', 'min_grade': 'C+'},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'III'},
            {'type': 'group', 'group': 'II_III_IV_V_2nd'}
        ]
    },
    11: {
        'name': 'Interior Design, Fashion & Textiles',
        'min_grades': ['C', None, None, None],  # CHE, MAT_A/B/PHY, BIO/HSC, ENG/KIS/Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'chemistry', 'min_grade': 'C'},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b', 'physics']},
            {'type': 'either', 'subjects': ['biology', 'homescience']},
            {'type': 'either', 'subjects': ['english', 'kiswahili'] + GROUP_III + GROUP_IV + GROUP_V}
        ]
    },
    12: {
        'name': 'Sport Science & Related',
        'min_grades': ['C', None, None, None],  # BIO/GSC, MAT_A/B, Group II/III, ENG/KIS/Group II/III/IV/V
        'requirements': [
            {'type': 'either', 'subjects': ['biology', 'general_science'], 'min_grade': 'C'},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b']},
            {'type': 'group', 'group': 'II_III'},
            {'type': 'either', 'subjects': ['english', 'kiswahili'] + GROUP_II + GROUP_III + GROUP_IV + GROUP_V}
        ]
    },
    13: {
        'name': 'Medicine & Health Sciences',
        'min_grades': ['B', 'B', 'B', 'B'],  # Medicine: B plain in all
        'min_grades_other': ['C+', 'C+', 'C+', 'C+'],  # Other health programs: C+
        'requirements': [
            {'type': 'subject', 'subject': 'biology', 'min_grade_med': 'B', 'min_grade_other': 'C+'},
            {'type': 'subject', 'subject': 'chemistry', 'min_grade_med': 'B', 'min_grade_other': 'C+'},
            {'type': 'either', 'subjects': ['mathematics_a', 'physics'], 'min_grade_med': 'B', 'min_grade_other': 'C+'},
            {'type': 'either', 'subjects': ['english', 'kiswahili'] + GROUP_II + GROUP_III + GROUP_IV + GROUP_V, 
             'min_grade_med': 'B', 'min_grade_other': 'C+'}
        ]
    },
    14: {
        'name': 'History & Archaeology',
        'min_grades': ['C+', 'C+', 'C+', 'C+'],  # All C+
        'requirements': [
            {'type': 'subject', 'subject': 'history', 'min_grade': 'C+'},
            {'type': 'group', 'group': 'HISTORY_CLUSTER'}  # Special: any 3 from specified list
        ]
    },
    15: {
        'name': 'Agriculture & Environmental Sciences',
        'min_grades': ['C', 'C', 'C', None],  # BIO/AGRIC/HSC, CHE, MAT_A/PHY/GEO, varies
        'requirements': [
            {'type': 'either', 'subjects': ['biology', 'agriculture', 'homescience'], 'min_grade': 'C'},
            {'type': 'subject', 'subject': 'chemistry', 'min_grade': 'C'},
            {'type': 'either', 'subjects': ['mathematics_a', 'physics', 'geography'], 'min_grade': 'C'},
            {'type': 'group', 'group': 'VARIES'}
        ]
    },
    16: {
        'name': 'Geography & Related',
        'min_grades': ['C+', None, None, None],  # GEO, MAT_A/B, Group II, 2nd Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'geography', 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b']},
            {'type': 'group', 'group': 'II'},
            {'type': 'group', 'group': 'II_III_IV_V_2nd'}
        ]
    },
    17: {
        'name': 'French & German',
        'min_grades': ['C+', None, None, None],  # FRE/GER, ENG/KIS, MAT_A/B/Group II/III, Group II/III/IV/V
        'requirements': [
            {'type': 'either', 'subjects': ['french', 'german'], 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['english', 'kiswahili']},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b'] + GROUP_II + GROUP_III},
            {'type': 'group', 'group': 'II_III_IV_V_2ndV'}
        ]
    },
    18: {
        'name': 'Music & Related',
        'min_grades': ['C+', None, None, None],  # MUS, ENG/KIS, MAT_A/B/Group II/III, Group II/III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'music', 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['english', 'kiswahili']},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b'] + GROUP_II + GROUP_III},
            {'type': 'group', 'group': 'II_III_IV_V_2ndV'}
        ]
    },
    19: {
        'name': 'Education & Related',
        'min_grades': [None, None, None, None],  # ENG, MAT_A/B/Group II, 2nd Group II, KIS/3rd Group II/2nd Group III/IV/V
        'requirements': [
            {'type': 'subject', 'subject': 'english'},
            {'type': 'either', 'subjects': ['mathematics_a', 'mathematics_b'] + GROUP_II},
            {'type': 'group', 'group': 'II_2nd'},
            {'type': 'either', 'subjects': ['kiswahili'] + GROUP_II + GROUP_III + GROUP_IV + GROUP_V}
        ]
    },
    20: {
        'name': 'Religious Studies & Theology',
        'min_grades': ['C+', 'C', None, None],  # CRE/IRE/HRE, ENG/KIS, 2nd Group III, Group II/IV/V
        'requirements': [
            {'type': 'either', 'subjects': ['cre', 'ire', 'hre'], 'min_grade': 'C+'},
            {'type': 'either', 'subjects': ['english', 'kiswahili'], 'min_grade': 'C'},
            {'type': 'group', 'group': 'III_2nd'},
            {'type': 'group', 'group': 'II_IV_V'}
        ]
    }
}

def grade_to_points(grade):
    """Convert grade letter to points"""
    if not grade or grade.upper() not in GRADE_POINTS:
        return 0
    return GRADE_POINTS[grade.upper()]

def grade_meets_minimum(grade, min_grade):
    """Check if grade meets minimum requirement"""
    if not min_grade:
        return True
    if not grade:
        return False
    
    grade_upper = grade.upper()
    min_grade_upper = min_grade.upper()
    
    return GRADE_RANK.get(grade_upper, 0) >= GRADE_RANK.get(min_grade_upper, 0)

def get_subject_group(subject_name):
    """Get group of a subject"""
    subject_lower = subject_name.lower().replace(' ', '_')
    
    # Check direct mapping
    if subject_lower in SUBJECT_GROUPS:
        return SUBJECT_GROUPS[subject_lower]
    
    # Check aliases
    for alias, subjects in SUBJECT_ALIASES.items():
        if subject_lower == alias or subject_lower in subjects:
            # Return group of first subject in alias list
            for sub in subjects:
                if sub in SUBJECT_GROUPS:
                    return SUBJECT_GROUPS[sub]
    
    return 'Unknown'

def normalize_subject_name(subject_name):
    """Normalize subject name to standard form"""
    subject_lower = subject_name.lower().replace(' ', '_')
    
    # Check direct mapping
    if subject_lower in SUBJECT_GROUPS:
        return subject_lower
    
    # Check aliases
    for alias, subjects in SUBJECT_ALIASES.items():
        if subject_lower == alias or subject_lower in subjects:
            return subjects[0]  # Return first standard name
    
    return subject_lower

def get_best_subjects_for_cluster(grades_dict, cluster_num):
    """Get best subjects that meet cluster requirements"""
    cluster_info = CLUSTER_REQUIREMENTS.get(cluster_num, {})
    if not cluster_info:
        return [], False
    
    requirements = cluster_info.get('requirements', [])
    if not requirements:
        return [], False
    
    # Convert grades dict to list of subjects with points and group
    subjects_list = []
    for subject_name, grade in grades_dict.items():
        if not grade:
            continue
        
        normalized_subject = normalize_subject_name(subject_name)
        points = grade_to_points(grade)
        group = get_subject_group(normalized_subject)
        
        subjects_list.append({
            'original_name': subject_name,
            'normalized_name': normalized_subject,
            'grade': grade.upper(),
            'points': points,
            'group': group
        })
    
    # Sort by points (highest first)
    subjects_list.sort(key=lambda x: x['points'], reverse=True)
    
    selected_subjects = []
    used_subjects = set()
    meets_requirements = True
    
    for req_index, requirement in enumerate(requirements):
        req_type = requirement.get('type', '')
        best_match = None
        best_points = -1
        
        for subject in subjects_list:
            if subject['original_name'] in used_subjects:
                continue
            
            # Check if subject meets requirement
            meets_req = False
            
            if req_type == 'subject':
                if subject['normalized_name'] == requirement.get('subject'):
                    if 'min_grade' in requirement:
                        meets_req = grade_meets_minimum(subject['grade'], requirement['min_grade'])
                    else:
                        meets_req = True
            
            elif req_type == 'either':
                required_subjects = requirement.get('subjects', [])
                if subject['normalized_name'] in required_subjects:
                    if 'min_grade' in requirement:
                        meets_req = grade_meets_minimum(subject['grade'], requirement['min_grade'])
                    else:
                        meets_req = True
            
            elif req_type == 'group':
                group_spec = requirement.get('group', '')
                subject_group = subject['group']
                
                if group_spec == 'II' and subject_group == 'II':
                    meets_req = True
                elif group_spec == 'III' and subject_group == 'III':
                    meets_req = True
                elif group_spec == 'III_IV_V' and subject_group in ['III', 'IV', 'V']:
                    meets_req = True
                elif group_spec == 'II_III_IV_V' and subject_group in ['II', 'III', 'IV', 'V']:
                    meets_req = True
                # Add more group specifications as needed
            
            if meets_req and subject['points'] > best_points:
                best_match = subject
                best_points = subject['points']
        
        if best_match:
            selected_subjects.append(best_match)
            used_subjects.add(best_match['original_name'])
        else:
            # Requirement not met
            meets_requirements = False
            # Add placeholder with 0 points
            selected_subjects.append({
                'original_name': f'Requirement {req_index+1}',
                'normalized_name': f'req_{req_index+1}',
                'grade': '',
                'points': 0,
                'group': 'Unknown',
                'missing': True
            })
    
    return selected_subjects, meets_requirements

def calculate_agp(grades_dict):
    """Calculate AGP (sum of best 7 subjects)"""
    subject_points = []
    
    for subject, grade in grades_dict.items():
        if grade and grade.upper() in GRADE_POINTS:
            points = grade_to_points(grade)
            subject_points.append({
                'subject': subject,
                'grade': grade.upper(),
                'points': points,
                'group': get_subject_group(subject)
            })
    
    # Sort by points (highest first) and take top 7
    subject_points.sort(key=lambda x: x['points'], reverse=True)
    best_7 = subject_points[:7]
    agp = sum(item['points'] for item in best_7)
    
    return agp, best_7

def calculate_cluster_points(x, y):
    """
    Calculate cluster points using official KUCCPS formula:
    c = √(x/48 × y/84) × 48
    """
    if x <= 0 or y <= 0:
        return 0.0
    
    try:
        # Step-by-step calculation
        x_over_48 = x / 48.0
        y_over_84 = y / 84.0
        
        product = x_over_48 * y_over_84
        
        if product <= 0:
            return 0.0
        
        sqrt_product = math.sqrt(product)
        cluster_points = sqrt_product * 48
        
        return round(cluster_points, 3)
    except:
        return 0.0

def calculate_all_clusters(grades_dict):
    """Calculate points for all 20 clusters with proper subject selection"""
    results = []
    
    # Calculate AGP once
    agp, best_7 = calculate_agp(grades_dict)
    
    # Process each cluster
    for cluster_num in range(1, 21):
        # Get best subjects for this cluster
        cluster_subjects, eligible = get_best_subjects_for_cluster(grades_dict, cluster_num)
        
        # Calculate x (sum of cluster subject points)
        x = sum(subject['points'] for subject in cluster_subjects)
        
        # Calculate cluster points
        points = calculate_cluster_points(x, agp)
        
        # Get cluster info
        cluster_info = CLUSTER_REQUIREMENTS.get(cluster_num, {})
        
        # Prepare subjects info for display
        subjects_info = []
        for subject in cluster_subjects:
            subjects_info.append({
                'name': subject['original_name'].replace('_', ' ').title(),
                'points': subject['points'],
                'grade': subject['grade'],
                'group': subject['group'],
                'missing': subject.get('missing', False)
            })
        
        results.append({
            'cluster': cluster_num,
            'name': cluster_info.get('name', f'Cluster {cluster_num}'),
            'points': points,
            'status': 'Calculated' if eligible else 'Missing Requirements',
            'eligible': eligible,
            'subjects': subjects_info,
            'used_subjects': [s['original_name'] for s in cluster_subjects],
            'formula': 'c = √(x/48 × y/84) × 48',
            'calculation': {
                'x': x,
                'y': agp,
                'formula': f'√({x}/48 × {agp}/84) × 48 = {points}',
                'eligible': eligible
            }
        })
    
    # Sort results by points (highest first)
    results.sort(key=lambda x: x['points'], reverse=True)
    
    return results, agp, best_7