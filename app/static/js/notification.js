function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    const messageEl = document.getElementById('notificationMessage');
    const headerEl = notification?.querySelector('.toast-header');
    
    if (notification && messageEl && headerEl) {
        messageEl.textContent = message;
        
        // 设置通知类型样式
        if (type === 'error') {
            headerEl.className = 'toast-header bg-danger text-white';
            headerEl.querySelector('strong').textContent = '错误';
        } else {
            headerEl.className = 'toast-header bg-success text-white';
            headerEl.querySelector('strong').textContent = '成功';
        }
        
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
