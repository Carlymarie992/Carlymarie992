// Main JavaScript for the Secure Document Processing System

// Global variables
let authToken = localStorage.getItem('authToken');
let currentUser = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    if (authToken) {
        // Verify token and load user data
        fetch('/api/auth/profile', {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (response.ok) {
                return response.json();
            } else {
                throw new Error('Token invalid');
            }
        })
        .then(data => {
            currentUser = data.user;
            showAuthenticatedView();
            loadDashboardData();
        })
        .catch(error => {
            console.error('Authentication failed:', error);
            logout();
        });
    } else {
        showUnauthenticatedView();
    }
}

function showAuthenticatedView() {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
    document.getElementById('loginAlert').style.display = 'none';
}

function showUnauthenticatedView() {
    document.getElementById('authSection').style.display = 'block';
    document.getElementById('dashboardSection').style.display = 'none';
    document.getElementById('loginAlert').style.display = 'block';
}

function showLoginModal() {
    const modal = new bootstrap.Modal(document.getElementById('loginModal'));
    modal.show();
}

function showRegisterModal() {
    const modal = new bootstrap.Modal(document.getElementById('registerModal'));
    modal.show();
}

function login() {
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    if (!username || !password) {
        showAlert('Please enter both username and password', 'danger');
        return;
    }

    fetch('/api/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.access_token) {
            authToken = data.access_token;
            currentUser = data.user;
            localStorage.setItem('authToken', authToken);
            
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('loginModal'));
            modal.hide();
            
            // Clear form
            document.getElementById('loginForm').reset();
            
            showAuthenticatedView();
            loadDashboardData();
            showAlert('Login successful!', 'success');
        } else {
            showAlert(data.error || 'Login failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Login error:', error);
        showAlert('Login failed. Please try again.', 'danger');
    });
}

function register() {
    const username = document.getElementById('regUsername').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;

    if (!username || !email || !password) {
        showAlert('Please fill in all registration fields', 'danger');
        return;
    }

    fetch('/api/auth/register', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, email, password })
    })
    .then(response => response.json())
    .then(data => {
        if (data.user) {
            // Close modal
            const modal = bootstrap.Modal.getInstance(document.getElementById('registerModal'));
            modal.hide();
            
            // Clear form
            document.getElementById('registerForm').reset();
            
            showAlert('Registration successful! Please log in.', 'success');
            
            // Pre-fill login form
            document.getElementById('username').value = username;
            showLoginModal();
        } else {
            showAlert(data.error || 'Registration failed', 'danger');
        }
    })
    .catch(error => {
        console.error('Registration error:', error);
        showAlert('Registration failed. Please try again.', 'danger');
    });
}

function logout() {
    if (authToken) {
        fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        })
        .then(() => {
            localStorage.removeItem('authToken');
            authToken = null;
            currentUser = null;
            showUnauthenticatedView();
            showAlert('Logged out successfully', 'info');
        })
        .catch(error => {
            console.error('Logout error:', error);
            // Still clear local storage even if request fails
            localStorage.removeItem('authToken');
            authToken = null;
            currentUser = null;
            showUnauthenticatedView();
        });
    } else {
        showUnauthenticatedView();
    }
}

function loadDashboardData() {
    if (!authToken) return;

    fetch('/api/dashboard', {
        headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.statistics) {
            document.getElementById('docCount').textContent = data.statistics.total_documents;
            document.getElementById('processedCount').textContent = data.statistics.processed_documents;
            document.getElementById('chatCount').textContent = data.statistics.total_chats;
            document.getElementById('processRate').textContent = data.statistics.processing_rate.toFixed(1) + '%';
        }
    })
    .catch(error => {
        console.error('Dashboard data error:', error);
    });
}

function showAlert(message, type = 'info') {
    // Create alert element
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // Insert at top of container
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleString();
}

// Utility function to make authenticated API calls
function apiCall(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Authorization': `Bearer ${authToken}`,
            'Content-Type': 'application/json'
        }
    };

    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers
        }
    };

    return fetch(url, mergedOptions)
        .then(response => {
            if (response.status === 401) {
                // Token expired or invalid
                logout();
                throw new Error('Authentication expired');
            }
            return response;
        });
}

// Export functions for use in other scripts
window.apiCall = apiCall;
window.showAlert = showAlert;
window.formatFileSize = formatFileSize;
window.formatDate = formatDate;