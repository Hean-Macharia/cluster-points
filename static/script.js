// script.js
function showLoading(show = true) {
    const spinner = document.getElementById('loadingSpinner');
    spinner.style.display = show ? 'flex' : 'none';
}

function resetForm() {
    document.getElementById('gradesForm').reset();
    document.getElementById('resultsSection').style.display = 'none';
}

function loadSampleData() {
    // Sample grades for testing
    const sampleData = {
        'mathematics': 'A',
        'english': 'B+',
        'kiswahili': 'B',
        'physics': 'A-',
        'chemistry': 'B+',
        'biology': 'B',
        'history': 'C+',
        'geography': 'B-',
        'cre': 'B',
        'computer': 'A',
        'business': 'A-',
        'agriculture': 'B+'
    };

    // Set the values in the form
    Object.keys(sampleData).forEach(field => {
        const element = document.getElementById(field);
        if (element) {
            element.value = sampleData[field];
        }
    });

    // Show success message
    alert('Sample data loaded! Click "Calculate Cluster Points" to see results.');
}

function formatClusterPoints(points) {
    const num = parseFloat(points);
    if (num >= 30) return '<span class="points-high">' + points + '</span>';
    if (num >= 15) return '<span class="points-medium">' + points + '</span>';
    if (num > 0) return points;
    return '<span class="points-zero">0.000</span>';
}

function showClusterDetails(clusterId, clusterName, points, subjectsUsed) {
    const modalTitle = document.getElementById('modalTitle');
    const modalContent = document.getElementById('modalContent');
    
    modalTitle.textContent = `${clusterName} Details`;
    
   
    
    if (subjectsUsed && subjectsUsed.length > 0) {
        html += `<h6 class="mb-3"><i class="fas fa-book"></i> Subjects Used:</h6>
        <div class="subject-details">`;
        
        let totalPoints = 0;
        subjectsUsed.forEach((subject, index) => {
            const gradeClass = `grade-${subject.grade.charAt(0)}`;
            html += `<div class="subject-detail-item">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <span class="subject-grade">${subject.subject.replace('_', ' ').toUpperCase()}</span>
                        <span class="badge ${gradeClass} subject-badge">${subject.grade}</span>
                        ${subject.requirement ? `<span class="requirement-badge">${subject.requirement}</span>` : ''}
                    </div>
                    <div class="subject-points">${subject.points} points</div>
                </div>
            </div>`;
            totalPoints += subject.points;
        });
        
        html += `</div>
        <div class="mt-3 p-3 bg-light rounded">
            <strong>Total Cluster Points (x):</strong> ${totalPoints} / 48
        </div>`;
    }
    
    modalContent.innerHTML = html;
    
    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('clusterDetailsModal'));
    modal.show();
}

function displayResults(data) {
    const resultsSection = document.getElementById('resultsSection');
    const clusterGrid = document.getElementById('clusterGrid');
    const aggregateDisplay = document.getElementById('aggregateDisplay');
    const topClustersSection = document.getElementById('topClustersSection');
    const topClustersGrid = document.getElementById('topClustersGrid');
    
    // Show results section
    resultsSection.style.display = 'block';
    
    // Display aggregate points
    if (data.aggregate_points) {
        aggregateDisplay.innerHTML = `
            <div>Aggregate Points (y): <strong>${data.aggregate_points} / 84</strong></div>
            <div>Top 7 Subjects: ${data.top_7_subjects.map(s => `${s.subject.replace('_', ' ')} (${s.points})`).join(', ')}</div>
        `;
    }
    
    // Clear previous results
    clusterGrid.innerHTML = '';
    topClustersGrid.innerHTML = '';
    
    // Sort clusters by points (descending) for display
    const clusters = [];
    for (let i = 1; i <= 20; i++) {
        const clusterKey = `Cluster ${i}`;
        if (data.results && data.results[clusterKey]) {
            const points = parseFloat(data.results[clusterKey]);
            clusters.push({
                id: i,
                name: clusterKey,
                points: points,
                pointsFormatted: data.results[clusterKey],
                description: data.details[clusterKey]?.description || ''
            });
        }
    }
    
    // Sort by points descending
    clusters.sort((a, b) => b.points - a.points);
    
    // Get top 3 clusters
    const topClusters = clusters.slice(0, 3);
    
    // Display all clusters
    clusters.forEach((cluster, index) => {
        const cardClass = cluster.points === 0 ? 'zero' : (cluster.points >= 30 ? 'highlight' : '');
        const pointsDisplay = formatClusterPoints(cluster.pointsFormatted);
        
        const clusterCard = document.createElement('div');
        clusterCard.className = `cluster-card ${cardClass}`;
        clusterCard.onclick = () => {
            const details = data.details[`Cluster ${cluster.id}`];
            if (details) {
                showClusterDetails(
                    cluster.id,
                    cluster.name,
                    cluster.pointsFormatted,
                    details.subjects_used
                );
            }
        };
        
        clusterCard.innerHTML = `
            <div class="cluster-header">
                <div class="cluster-number">${cluster.id}</div>
                <div class="cluster-points">${pointsDisplay}</div>
            </div>
            <div class="cluster-name">${cluster.name}</div>
            <div class="cluster-description">${cluster.description}</div>
            <div class="cluster-subjects" id="subjects-${cluster.id}"></div>
        `;
        
        clusterGrid.appendChild(clusterCard);
    });
    
    // Display top clusters if any
    if (topClusters.length > 0) {
        topClustersSection.style.display = 'block';
        topClusters.forEach(cluster => {
            const pointsDisplay = formatClusterPoints(cluster.pointsFormatted);
            
            const clusterCard = document.createElement('div');
            clusterCard.className = 'cluster-card highlight';
            clusterCard.onclick = () => {
                const details = data.details[`Cluster ${cluster.id}`];
                if (details) {
                    showClusterDetails(
                        cluster.id,
                        cluster.name,
                        cluster.pointsFormatted,
                        details.subjects_used
                    );
                }
            };
            
            clusterCard.innerHTML = `
                <div class="cluster-header">
                    <div class="cluster-number">${cluster.id}</div>
                    <div class="cluster-points">${pointsDisplay}</div>
                </div>
                <div class="cluster-name">${cluster.name}</div>
                <div class="cluster-description">${cluster.description}</div>
                <div class="text-center mt-2">
                    <span class="badge bg-success"><i class="fas fa-trophy me-1"></i> Top ${clusters.indexOf(cluster) + 1}</span>
                </div>
            `;
            
            topClustersGrid.appendChild(clusterCard);
        });
    } else {
        topClustersSection.style.display = 'none';
    }
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

function sortClusters(sortType) {
    const clusterGrid = document.getElementById('clusterGrid');
    const clusters = Array.from(clusterGrid.getElementsByClassName('cluster-card'));
    const sortButtons = document.querySelectorAll('.sort-btn');
    
    // Update active button
    sortButtons.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    clusters.sort((a, b) => {
        const aId = parseInt(a.querySelector('.cluster-number').textContent);
        const bId = parseInt(b.querySelector('.cluster-number').textContent);
        const aPoints = parseFloat(a.querySelector('.cluster-points').textContent.replace(/[^\d.]/g, '') || 0);
        const bPoints = parseFloat(b.querySelector('.cluster-points').textContent.replace(/[^\d.]/g, '') || 0);
        
        switch (sortType) {
            case 'number':
                return aId - bId;
            case 'points':
                return bPoints - aPoints;
            case 'non-zero':
                if (aPoints === 0 && bPoints > 0) return 1;
                if (aPoints > 0 && bPoints === 0) return -1;
                return bPoints - aPoints;
            default:
                return aId - bId;
        }
    });
    
    // Reorder clusters
    clusters.forEach(cluster => clusterGrid.appendChild(cluster));
    
    // For non-zero filter, hide/show
    if (sortType === 'non-zero') {
        clusters.forEach(cluster => {
            const points = parseFloat(cluster.querySelector('.cluster-points').textContent.replace(/[^\d.]/g, '') || 0);
            cluster.style.display = points === 0 ? 'none' : 'block';
        });
    } else {
        clusters.forEach(cluster => cluster.style.display = 'block');
    }
}

// Handle form submission
document.getElementById('gradesForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    // Collect form data
    const formData = new FormData(this);
    const grades = {};
    
    // Convert FormData to object
    formData.forEach((value, key) => {
        if (value && value !== 'Select Grade') {
            grades[key] = value.toUpperCase();
        }
    });
    
    // Check if at least Mathematics and English are filled
    if (!grades.mathematics || !grades.english) {
        alert('Please enter grades for at least Mathematics and English.');
        return;
    }
    
    // Show loading spinner
    showLoading(true);
    
    try {
        // Send data to backend
        const response = await fetch('/calculate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(grades)
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayResults(data);
            
            // Show warning if not enough subjects
            if (data.warning) {
                const warningAlert = document.createElement('div');
                warningAlert.className = 'alert alert-warning mt-3';
                warningAlert.innerHTML = `
                    <i class="fas fa-exclamation-triangle"></i> 
                    <strong>Note:</strong> ${data.warning}
                `;
                document.getElementById('resultsSection').prepend(warningAlert);
            }
        } else {
            alert('Error calculating points: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Network error: ' + error.message);
        console.error('Error:', error);
    } finally {
        showLoading(false);
    }
});

// Initialize sort buttons
document.addEventListener('DOMContentLoaded', function() {
    // Set up sort buttons
    const sortButtons = document.querySelectorAll('.sort-btn');
    sortButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            sortButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
        });
    });
});