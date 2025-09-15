// script.js (corrected)

/* Config */
const API_URL = "http://127.0.0.1:8000";

/* DOM refs */
const uploadInput = document.getElementById('csv-upload'),
      ingestBtn = document.getElementById('ingest-btn'),
      clearDbBtn = document.getElementById('clear-db-btn'),
      modelSelector = document.getElementById('model-selector'),
      detectBtn = document.getElementById('detect-btn'),
      downloadReportBtn = document.getElementById('download-report-btn'),
      logBtn = document.getElementById('log-btn'),
      retrainBtn = document.getElementById('retrain-btn'),
      statusArea = document.getElementById('status-area'),
      progressArea = document.getElementById('progress-area'),
      progressBar = document.getElementById('progress-bar'),
      progressText = document.getElementById('progress-text'),
      reportArea = document.getElementById('report-area'),
      logArea = document.getElementById('log-area'),
      loginModal = document.getElementById('login-modal'),
      loginView = document.getElementById('login-view'),
      signupView = document.getElementById('signup-view'),
      showSignup = document.getElementById('show-signup'),
      showLogin = document.getElementById('show-login'),
      loginForm = document.getElementById('login-form'),
      signupForm = document.getElementById('signup-form'),
      loginError = document.getElementById('login-error'),
      signupError = document.getElementById('signup-error'),
      userInfo = document.getElementById('user-info'),
      usernameDisplay = document.getElementById('username-display'),
      logoutBtn = document.getElementById('logout-btn'),
      loginBtnHeader = document.getElementById('login-btn-header'),
      signupBtnHeader = document.getElementById('signup-btn-header');

let uploadedFile = null;
let progressMonitorInterval = null;

/* --- Event Listeners --- */
document.addEventListener('DOMContentLoaded', checkLoginState);

uploadInput && uploadInput.addEventListener('change', (e) => {
    uploadedFile = e.target.files[0];
    if (uploadedFile) {
        if (getToken()) ingestBtn.disabled = false;
        showStatus(`✅ File "${uploadedFile.name}" selected. Ready to ingest.`, 'success');
    }
});

ingestBtn && ingestBtn.addEventListener('click', handleIngest);
clearDbBtn && clearDbBtn.addEventListener('click', handleClearDatabase);
detectBtn && detectBtn.addEventListener('click', handleDetect);
downloadReportBtn && downloadReportBtn.addEventListener('click', handleDownloadReport);
logBtn && logBtn.addEventListener('click', handleViewLog);
retrainBtn && retrainBtn.addEventListener('click', handleRetrain);

showSignup && showSignup.addEventListener('click', (e) => { e.preventDefault(); toggleAuthView(true); });
showLogin && showLogin.addEventListener('click', (e) => { e.preventDefault(); toggleAuthView(false); });

signupForm && signupForm.addEventListener('submit', handleSignup);
loginForm && loginForm.addEventListener('submit', handleLogin);
loginBtnHeader && loginBtnHeader.addEventListener('click', () => { toggleAuthView(false); loginModal.classList.remove('hidden'); });
signupBtnHeader && signupBtnHeader.addEventListener('click', () => { toggleAuthView(true); loginModal.classList.remove('hidden'); });
logoutBtn && logoutBtn.addEventListener('click', handleLogout);

/* --- Auth Helpers --- */
function getToken() { return sessionStorage.getItem('accessToken'); }
function saveToken(token) { sessionStorage.setItem('accessToken', token); }
function getUsername() { return sessionStorage.getItem('username'); }
function saveUsername(name) { sessionStorage.setItem('username', name); }

function getAuthHeaders() {
    const token = getToken();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

/* --- UI State --- */
function checkLoginState() {
    const token = getToken();
    const buttons = [ingestBtn, detectBtn, downloadReportBtn, logBtn, retrainBtn, clearDbBtn];
    if (token) {
        loginModal && loginModal.classList.add('hidden');
        userInfo && userInfo.classList.remove('hidden');
        logoutBtn && logoutBtn.classList.remove('hidden');
        loginBtnHeader && loginBtnHeader.classList.add('hidden');
        signupBtnHeader && signupBtnHeader.classList.add('hidden');
        usernameDisplay && (usernameDisplay.innerText = getUsername() || "");
        buttons.forEach(b => b && (b.disabled = false));
        if (!uploadedFile) ingestBtn && (ingestBtn.disabled = true);
        showStatus('⬅️ Please upload a CSV file or ingest the selected one.', 'info');
    } else {
        loginModal && loginModal.classList.remove('hidden');
        userInfo && userInfo.classList.add('hidden');
        logoutBtn && logoutBtn.classList.add('hidden');
        loginBtnHeader && loginBtnHeader.classList.remove('hidden');
        signupBtnHeader && signupBtnHeader.classList.remove('hidden');
        buttons.forEach(b => b && (b.disabled = true));
        showStatus('Please log in to use the application.', 'info');
    }
}

/* --- Ingest Handler --- */
async function handleIngest() {
    if (!uploadedFile) return showStatus('⚠️ Please select a CSV file first.', 'error');
    ingestBtn.disabled = true;
    showProgress('Ingesting transactions...', '5%');

    Papa.parse(uploadedFile, {
        header: true,
        skipEmptyLines: true,
        complete: async function (results) {
            try {
                const rows = results.data
                    .map(row => ({
                        card_number: (row.card_number || row.CardNumber || row.card || "").trim(),
                        amount: parseFloat(row.amount || row.Amount || row.transaction_amount || row.value || 0)
                    }))
                    .filter(r => r.card_number && !Number.isNaN(r.amount)); // filter invalid rows

                if (!rows.length) {
                    showStatus("⚠️ No valid rows found in CSV.", "error");
                    hideProgress();
                    ingestBtn.disabled = false;
                    return;
                }

                const response = await fetch(`${API_URL}/ingest_batch/`, {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ transactions: rows })
                });

                if (!response.ok) {
                    const err = await response.json().catch(() => ({}));
                    throw new Error(err.detail || `Server returned ${response.status}`);
                }

                const data = await response.json().catch(() => ({}));
                hideProgress();
                ingestBtn.disabled = false;
                showStatus(`✅ Appended ${rows.length} new transactions to the database.`, 'success');

            } catch (error) {
                hideProgress();
                ingestBtn.disabled = false;
                showStatus(`❌ Ingest failed: ${error.message}`, 'error');
            }
        },
        error: function(err) {
            hideProgress();
            ingestBtn.disabled = false;
            showStatus(`❌ CSV parse error: ${err.message}`, 'error');
        }
    });
}

/* --- Clear DB --- */
async function handleClearDatabase() {
    if (!confirm("Are you sure you want to delete ALL transaction data? This cannot be undone.")) return;
    clearDbBtn.disabled = true;
    showStatus('Clearing all transaction data...', 'info');

    try {
        const response = await fetch(`${API_URL}/transactions/clear`, {
            method: 'POST',
            headers: getAuthHeaders()
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server returned ${response.status}`);
        }

        const data = await response.json();
        showStatus(`✅ ${data.message}`, 'success');
        reportArea.classList.add('hidden');
        logArea.classList.add('hidden');
        handleViewLog();
    } catch (error) {
        showStatus(`❌ Error: ${error.message}`, 'error');
    } finally {
        clearDbBtn.disabled = false;
    }
}

/* --- Detection --- */
async function handleDetect() {
    const model_name = modelSelector.value;
    detectBtn.disabled = true;
    showProgress(`Starting fraud detection with ${model_name}...`, '5%');

    try {
        const response = await fetch(`${API_URL}/detection/start`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ model_name })
        });

        if (response.status === 404) {
            hideProgress();
            detectBtn.disabled = false;
            showStatus("⚠️ No unprocessed transactions to analyze.", 'error');
            return;
        }

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server returned ${response.status}`);
        }

        showStatus("🚀 Fraud detection started. Monitoring progress...", 'info');
        monitorProgress();
    } catch (err) {
        hideProgress();
        detectBtn.disabled = false;
        showStatus(`⚠️ Error starting detection: ${err.message}`, 'error');
    }
}

function monitorProgress() {
    if (progressMonitorInterval) clearInterval(progressMonitorInterval);

    progressMonitorInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_URL}/detection/progress`, { headers: getAuthHeaders() });
            if (!response.ok) throw new Error(`Progress endpoint returned ${response.status}`);
            const data = await response.json();

            if (data.status === "completed") {
                clearInterval(progressMonitorInterval);
                progressMonitorInterval = null;
                hideProgress();
                detectBtn.disabled = false;
                showStatus(`🎉 Detection complete. Fraudulent: ${data.fraudulent}/${data.total}`, 'success');
            } else if (data.status === "error") {
                clearInterval(progressMonitorInterval);
                progressMonitorInterval = null;
                hideProgress();
                detectBtn.disabled = false;
                showStatus("❌ Detection failed. Check server logs.", 'error');
            } else {
                const percent = data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;
                showProgress(`Analyzing transactions... (${data.processed}/${data.total})`, `${percent}%`);
            }
        } catch (error) {
            if (progressMonitorInterval) {
                clearInterval(progressMonitorInterval);
                progressMonitorInterval = null;
            }
            hideProgress();
            detectBtn.disabled = false;
            showStatus(`❌ Progress monitoring failed: ${error.message}`, 'error');
        }
    }, 2000);
}

/* --- Fraud Report Display --- */
async function handleReport() {
    reportArea.classList.remove('hidden');
    try {
        const response = await fetch(`${API_URL}/fraud/report`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error(`Failed to fetch report: ${response.status}`);
        const data = await response.json();

        document.getElementById('metric-total').innerHTML = `<h3>${data.summary.total_transactions}</h3><p>Total Transactions</p>`;
        document.getElementById('metric-fraud').innerHTML = `<h3>${data.summary.fraudulent}</h3><p>Fraudulent</p>`;
        document.getElementById('metric-legit').innerHTML = `<h3>${data.summary.legit}</h3><p>Legitimate</p>`;
        document.getElementById('metric-percent').innerHTML = `<h3>${data.summary.fraud_percentage}%</h3><p>Fraud Rate</p>`;

        const tbody = document.querySelector('#fraud-table tbody');
        tbody.innerHTML = "";
        data.fraud_cases.forEach(tx => {
            const row = `<tr><td>${tx.id}</td><td>${tx.masked_card_number}</td><td>${tx.amount}</td><td>${tx.timestamp}</td><td>${tx.explanation || 'N/A'}</td></tr>`;
            tbody.innerHTML += row;
        });
        showStatus("📊 Fraud report generated.", 'info');
    } catch (error) {
        showStatus(`❌ Failed to load report: ${error.message}`, 'error');
    }
}

/* --- Download Report --- */
async function handleDownloadReport() {
    showStatus('🚀 Preparing your report for download...', 'info');

    try {
        const response = await fetch(`${API_URL}/fraud/report/download`, {
            headers: { "Authorization": `Bearer ${getToken()}` }
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server returned ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;

        const disposition = response.headers.get('content-disposition');
        let filename = 'fraud_report.csv';
        if (disposition && disposition.indexOf('attachment') !== -1) {
            const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
            const matches = filenameRegex.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
        showStatus('✅ Report downloaded successfully.', 'success');

    } catch (error) {
        showStatus(`❌ Download failed: ${error.message}`, 'error');
    }
}

/* --- Audit Log --- */
async function handleViewLog() {
    logArea.classList.remove('hidden');
    try {
        const response = await fetch(`${API_URL}/audit_log/`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error(`Failed to fetch logs: ${response.status}`);
        const logs = await response.json();
        const tbody = document.querySelector('#log-table tbody');
        tbody.innerHTML = "";
        logs.forEach(log => {
            const isRetrain = (log.action || "").toLowerCase().includes("retrain");
            const rowClass = isRetrain ? "retrain-row" : "";
            const icon = isRetrain ? "🎯 " : "";
            tbody.innerHTML += `<tr class="${rowClass}"><td>${log.timestamp}</td><td>${log.username}</td><td>${icon}${log.action}</td></tr>`;
        });
    } catch (error) {
        showStatus(`❌ Failed to load audit log: ${error.message}`, 'error');
    }
}

/* --- Retrain --- */
async function handleRetrain() {
    const model_name = modelSelector.value;
    retrainBtn.disabled = true;
    showProgress(`Retraining ${model_name} model...`, '5%');

    try {
        const response = await fetch(`${API_URL}/model/retrain`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ model_name })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server returned ${response.status}`);
        }

        const data = await response.json();
        showStatus(`🎉 ${data.message}`, 'success');
        handleViewLog();
    } catch (error) {
        showStatus(`❌ Error during retraining: ${error.message}`, 'error');
    } finally {
        hideProgress();
        retrainBtn.disabled = false;
    }
}

/* --- Signup --- */
async function handleSignup(e) {
    e.preventDefault();
    const username = document.getElementById('signup-username').value;
    const password = document.getElementById('signup-password').value;
    signupError.innerText = "";

    try {
        const response = await fetch(`${API_URL}/users/`, {
            method: 'POST',
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            signupError.innerText = data.detail || "Signup failed. Username may already exist.";
            return;
        }

        toggleAuthView(false);
        showStatus("✅ Signup successful. Please login.", 'success');
    } catch (err) {
        signupError.innerText = "⚠️ Network error. Please try again.";
    }
}

/* --- Login --- */
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    loginError.innerText = "";

    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    try {
        const response = await fetch(`${API_URL}/token`, {
            method: 'POST',
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });

        if (!response.ok) {
            sessionStorage.clear();
            const data = await response.json().catch(() => ({}));
            loginError.innerText = data.detail || "❌ Login failed. Invalid credentials.";
            return;
        }

        const data = await response.json();
        saveToken(data.access_token);
        saveUsername(username);
        loginModal.classList.add('hidden');
        checkLoginState();
        showStatus("✅ Login successful.", 'success');
    } catch (err) {
        sessionStorage.clear();
        loginError.innerText = "⚠️ Network error. Please try again.";
    }
}

/* --- Logout / Auth view toggle --- */
function handleLogout() {
    sessionStorage.clear();
    checkLoginState();
    showStatus("👋 Logged out successfully.", 'info');
}

function toggleAuthView(showSignupForm) {
    if (showSignupForm) {
        signupView.classList.remove('hidden');
        loginView.classList.add('hidden');
    } else {
        signupView.classList.add('hidden');
        loginView.classList.remove('hidden');
    }
}

/* --- UI helpers --- */
function showStatus(message, type) {
    statusArea.innerHTML = `<p class="${type || 'info'}">${message}</p>`;
}

function showProgress(message, percent) {
    progressArea.classList.remove('hidden');
    progressText.innerText = message;
    progressBar.style.width = percent;
}

function hideProgress() {
    progressArea.classList.add('hidden');
    progressBar.style.width = '0%';
}
