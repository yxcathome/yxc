// 全局变量
let charts = {};
let configData = {};
let updateInterval;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    initializeDashboard();
    setupEventListeners();
    startDataUpdates();
});

// 初始化仪表板
async function initializeDashboard() {
    await Promise.all([
        initializeCharts(),
        loadStrategies(),
        loadConfig(),
        updateOverview(),
        updatePositions()
    ]);
}

// 设置事件监听器
function setupEventListeners() {
    // 导航切换
    document.querySelectorAll('nav a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = e.target.getAttribute('href').substring(1);
            switchPanel(targetId);
        });
    });

    // 配置保存
    document.getElementById('save-config').addEventListener('click', saveConfig);
    document.getElementById('reset-config').addEventListener('click', resetConfig);
}

// 开始数据更新循环
function startDataUpdates() {
    updateInterval = setInterval(() => {
        updateOverview();
        updatePositions();
        updateCharts();
    }, 5000); // 每5秒更新一次
}

// 初始化图表
async function initializeCharts() {
    const equityCtx = document.getElementById('equity-chart').getContext('2d');
    const pnlCtx = document.getElementById('pnl-chart').getContext('2d');

    charts.equity = new Chart(equityCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: '总权益',
                data: [],
                borderColor: '#1a73e8',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    charts.pnl = new Chart(pnlCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: '每日盈亏',
                data: [],
                backgroundColor: '#34a853'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });
}

// 加载策略列表
async function loadStrategies() {
    try {
        const response = await fetch('/api/strategy/list');
        const strategies = await response.json();
        
        const container = document.getElementById('strategies-container');
        container.innerHTML = strategies.map(strategy => `
            <div class="strategy-card">
                <div class="strategy-header">
                    <h3>${strategy.name}</h3>
                    <label class="switch">
                        <input type="checkbox" ${strategy.is_active ? 'checked' : ''}
                               onchange="toggleStrategy('${strategy.name}')">
                        <span class="slider"></span>
                    </label>
                </div>
                <p>${strategy.description}</p>
                <div class="strategy-stats">
                    <div>成功交易: ${strategy.performance.successful_trades}</div>
                    <div>总收益: ${strategy.performance.total_profit}</div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('加载策略失败:', error);
    }
}

// 加载配置
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        configData = await response.json();
        renderConfigForm(configData);
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

// 渲染配置表单
function renderConfigForm(config) {
    const form = document.getElementById('config-form');
    form.innerHTML = '';

    for (const [key, value] of Object.entries(config)) {
        if (typeof value === 'object') {
            form.innerHTML += `<div class="config-section">
                <h3>${key}</h3>
                ${renderConfigSection(value, key)}
            </div>`;
        } else {
            form.innerHTML += renderConfigField(key, value);
        }
    }
}

// 渲染配置字段
function renderConfigField(key, value, prefix = '') {
    const fieldId = prefix ? `${prefix}.${key}` : key;
    const fieldName = key.replace(/_/g, ' ');

    if (typeof value === 'boolean') {
        return `
            <div class="config-field">
                <label for="${fieldId}">${fieldName}</label>
                <input type="checkbox" id="${fieldId}" ${value ? 'checked' : ''}>
            </div>
        `;
    } else if (typeof value === 'number') {
        return `
            <div class="config-field">
                <label for="${fieldId}">${fieldName}</label>
                <input type="number" id="${fieldId}" value="${value}">
            </div>
        `;
    } else {
        return `
            <div class="config-field">
                <label for="${fieldId}">${fieldName}</label>
                <input type="text" id="${fieldId}" value="${value}">
            </div>
        `;
    }
}

// 更新总览数据
async function updateOverview() {
    try {
        const response = await fetch('/api/monitor/overview');
        const data = await response.json();
        
        // 更新统计卡片
        document.getElementById('total-equity').textContent = 
            `${parseFloat(data.total_equity.okx) + parseFloat(data.total_equity.binance)} USDT`;
        document.getElementById('daily-pnl').textContent = 
            `${parseFloat(data.daily_pnl).toFixed(2)} USDT`;
        document.getElementById('max-drawdown').textContent = 
            `${(parseFloat(data.max_drawdown) * 100).toFixed(2)}%`;
        document.getElementById('active-positions').textContent = 
            data.active_positions;

        // 更新状态指示器
        const statusDot = document.querySelector('.status-dot');
        const statusText = document.querySelector('.status-text');
        statusDot.className = `status-dot ${data.status}`;
        statusText.textContent = `状态: ${data.status === 'running' ? '运行中' : '已停止'}`;
        
    } catch (error) {
        console.error('更新总览数据失败:', error);
    }
}

// 更新持仓数据
async function updatePositions() {
    try {
        const response = await fetch('/api/monitor/positions');
        const positions = await response.json();
        
        const tbody = document.getElementById('positions-body');
        tbody.innerHTML = positions.map(pos => `
            <tr>
                <td>${pos.exchange}</td>
                <td>${pos.symbol}</td>
                <td class="${pos.side === 'long' ? 'text-success' : 'text-danger'}">
                    ${pos.side}
                </td>
                <td>${parseFloat(pos.amount).toFixed(4)}</td>
                <td>${parseFloat(pos.entry_price).toFixed(2)}</td>
                <td>${parseFloat(pos.current_price).toFixed(2)}</td>
                <td class="${parseFloat(pos.pnl) >= 0 ? 'text-success' : 'text-danger'}">
                    ${parseFloat(pos.pnl).toFixed(2)}
                </td>
                <td>
                    <button class="btn btn-danger btn-sm" 
                            onclick="closePosition('${pos.exchange}', '${pos.symbol}')">
                        平仓
                    </button>
                </td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('更新持仓数据失败:', error);
    }
}

// 更新图表数据
async function updateCharts() {
    try {
        const performanceResponse = await fetch('/api/monitor/performance');
        const performanceData = await performanceResponse.json();
        
        const tradesResponse = await fetch('/api/monitor/trades');
        const tradesData = await tradesResponse.json();
        
        // 更新权益曲线
        updateEquityChart(performanceData.equity_history);
        
        // 更新盈亏图表
        updatePnlChart(tradesData);
        
    } catch (error) {
        console.error('更新图表失败:', error);
    }
}

// 更新权益曲线
function updateEquityChart(equityHistory) {
    if (!equityHistory || !charts.equity) return;
    
    charts.equity.data.labels = equityHistory.map(item => item.time);
    charts.equity.data.datasets[0].data = equityHistory.map(item => item.equity);
    charts.equity.update();
}

// 更新盈亏图表
function updatePnlChart(trades) {
    if (!trades || !charts.pnl) return;
    
    const dailyPnl = {};
    trades.forEach(trade => {
        const date = trade.time.split('T')[0];
        dailyPnl[date] = (dailyPnl[date] || 0) + parseFloat(trade.profit);
    });
    
    charts.pnl.data.labels = Object.keys(dailyPnl);
    charts.pnl.data.datasets[0].data = Object.values(dailyPnl);
    charts.pnl.update();
}

// 切换策略状态
async function toggleStrategy(strategyName) {
    try {
        const response = await fetch(`/api/strategy/${strategyName}/toggle`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (result.is_active) {
            showNotification(`${strategyName} 策略已启用`, 'success');
        } else {
            showNotification(`${strategyName} 策略已禁用`, 'warning');
        }
        
        await loadStrategies(); // 刷新策略列表
        
    } catch (error) {
        console.error('切换策略状态失败:', error);
        showNotification('操作失败，请重试', 'error');
    }
}

// 保存配置
async function saveConfig() {
    try {
        const form = document.getElementById('config-form');
        const formData = {};
        
        // 收集表单数据
        form.querySelectorAll('input').forEach(input => {
            const path = input.id.split('.');
            let current = formData;
            
            for (let i = 0; i < path.length - 1; i++) {
                current[path[i]] = current[path[i]] || {};
                current = current[path[i]];
            }
            
            const value = input.type === 'checkbox' ? input.checked : 
                         input.type === 'number' ? parseFloat(input.value) : 
                         input.value;
            current[path[path.length - 1]] = value;
        });
        
        const response = await fetch('/api/config/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        showNotification('配置保存成功', 'success');
        
    } catch (error) {
        console.error('保存配置失败:', error);
        showNotification('保存配置失败，请重试', 'error');
    }
}

// 重置配置
async function resetConfig() {
    if (!confirm('确定要重置所有配置吗？此操作不可撤销。')) {
        return;
    }
    
    try {
        const response = await fetch('/api/config/reset', {
            method: 'POST'
        });
        const result = await response.json();
        
        await loadConfig(); // 重新加载配置
        showNotification('配置已重置为默认值', 'success');
        
    } catch (error) {
        console.error('重置配置失败:', error);
        showNotification('重置配置失败，请重试', 'error');
    }
}

// 显示通知
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// 切换面板
function switchPanel(panelId) {
    document.querySelectorAll('.panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.querySelectorAll('nav a').forEach(link => {
        link.classList.remove('active');
    });
    
    document.getElementById(panelId).classList.add('active');
    document.querySelector(`nav a[href="#${panelId}"]`).classList.add('active');
}

// 平仓操作
async function closePosition(exchange, symbol) {
    if (!confirm(`确定要平掉 ${exchange} 的 ${symbol} 仓位吗？`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/monitor/close-position', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ exchange, symbol })
        });
        
        const result = await response.json();
        if (result.status === 'success') {
            showNotification('平仓成功', 'success');
            await updatePositions(); // 刷新持仓数据
        } else {
            showNotification('平仓失败: ' + result.message, 'error');
        }
        
    } catch (error) {
        console.error('平仓操作失败:', error);
        showNotification('平仓操作失败，请重试', 'error');
    }
}