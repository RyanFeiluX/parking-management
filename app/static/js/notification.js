function showNotification(message) {
    const notification = document.getElementById('notification');
    const messageEl = document.getElementById('notificationMessage');
    if (notification && messageEl) {
        messageEl.textContent = message;
        notification.style.display = 'block';
        
        // 3秒后自动隐藏
        setTimeout(hideNotification, 3000);
    }
}

function hideNotification() {
    const notification = document.getElementById('notification');
    if (notification) {
        notification.style.display = 'none';
    }
}
