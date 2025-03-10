:root {
    --primary-color: #1a73e8;
    --secondary-color: #5f6368;
    --background-color: #f8f9fa;
    --card-background: #ffffff;
    --text-color: #202124;
    --border-color: #dadce0;
    --success-color: #34a853;
    --warning-color: #fbbc05;
    --error-color: #ea4335;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background-color: var(--background-color);
    color: var(--text-color);
}

.dashboard-container {
    display: flex;
    min-height: 100vh;
}

/* 侧边栏样式 */
.sidebar {
    width: 250px;
    background-color: var(--card-background);
    border-right: 1px solid var(--border-color);
    padding: 20px 0;
    display: flex;
    flex-direction: column;
}

.logo {
    padding: 0 20px;
    margin-bottom: 30px;
}

.logo h2 {
    color: var(--primary-color);
}

nav ul {
    list-style: none;
}

nav ul li a {
    display: block;
    padding: 12px 20px;
    color: var(--text-color);
    text-decoration: none;
    transition: background-color 0.3s;
}

nav ul li a:hover,
nav ul li a.active {
    background-color: rgba(26, 115, 232, 0.1);
    color: var(--primary-color);
}

/* 主内容区样式 */
.main-content {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
}

.panel {
    display: none;
}

.panel.active {
    display: block;
}

.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

/* 统计卡片样式 */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background-color: var(--card-background);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.stat-card h3 {
    color: var(--secondary-color);
    font-size: 14px;
    margin-bottom: 10px;
}

.stat-value {
    font-size: 24px;
    font-weight: bold;
    color: var(--primary-color);
}

/* 图表容器样式 */
.charts-container {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 30px;
}

.chart-wrapper {
    background-color: var(--card-background);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

/* 表格样式 */
.positions-table-wrapper {
    background-color: var(--card-background);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    overflow-x: auto;
}

.positions-table {
    width: 100%;
    border-collapse: collapse;
}

.positions-table th,
.positions-table td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

.positions-table th {
    background-color: var(--background-color);
    font-weight: 500;
}

/* 按钮样式 */
.btn {
    padding: 8px 16px;
    border-radius: 4px;
    border: none;
    cursor: pointer;
    font-weight: 500;
    transition: background-color 0.3s;
}

.btn-primary {
    background-color: var(--primary-color);
    color: white;
}

.btn-secondary {
    background-color: var(--secondary-color);
    color: white;
}

/* 状态指示器 */
.status-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 8px;
}

.status-dot.running {
    background-color: var(--success-color);
}

.status-dot.stopped {
    background-color: var(--error-color);
}