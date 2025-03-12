const app = new Vue({
    el: '#app',
    data: {
        // 页面状态
        currentPage: 'dashboard',
        sidebarCollapsed: false,
        showModal: false,
        modalTitle: '',
        modalConfirmText: '确定',
        modalCallback: null,
        
        // 账户统计
        accountStats: {
            totalValue: 0,
            dayChange: 0,
            dayPnL: 0,
            dayPnLPercent: 0,
            totalPositions: 0,
            availableMargin: 0,
            riskLevel: 'low',
            leverage: 0
        },
        
        // 策略管理
        strategies: [],
        strategyFilter: {
            type: '',
            status: '',
            search: ''
        },
        
        // 持仓管理
        positions: [],
        positionStats: {
            totalValue: 0,
            positionCount: 0,
            unrealizedPnL: 0,
            unrealizedPnLPercent: 0,
            marginUsage: 0,
            availableMargin: 0,
            riskLevel: 'low',
            leverage: 0
        },
        
        // 风控监控
        riskMetrics: {
            overall: {
                score: 0,
                level: 'low',
                updateTime: null
            },
            position: {
                leverage: 0,
                concentration: 0,
                volatility: 0
            },
            capital: {
                marginUsage: 0,
                dailyLoss: 0,
                drawdown: 0
            }
        },
        riskAlerts: [],
        riskSettings: {
            maxLossPerTrade: 2,
            maxDailyLoss: 5,
            maxLeverage: 5,
            maxSinglePosition: 20,
            drawdownAlert: 10,
            volatilityAlert: 3
        },
        
        // 系统设置
        exchanges: [
            {
                id: 'binance',
                name: 'Binance',
                apiKey: '',
                secretKey: '',
                enabled: false,
                status: 'DISCONNECTED'
            },
            {
                id: 'okx',
                name: 'OKX',
                apiKey: '',
                secretKey: '',
                enabled: false,
                status: 'DISCONNECTED'
            }
        ],
        notificationSettings: {
            smtp: {
                server: '',
                email: '',
                password: ''
            },
            telegram: {
                token: '',
                chatId: ''
            }
        },
        systemSettings: {
            database: {
                type: 'sqlite',
                host: 'localhost',
                port: 3306,
                name: 'trading_bot',
                username: '',
                password: ''
            },
            logging: {
                level: 'INFO',
                retention: 30,
                console: true
            }
        }
    },
    
    computed: {
        filteredStrategies() {
            return this.strategies.filter(strategy => {
                if (this.strategyFilter.type && strategy.type !== this.strategyFilter.type) {
                    return false;
                }
                if (this.strategyFilter.status && strategy.status !== this.strategyFilter.status) {
                    return false;
                }
                if (this.strategyFilter.search) {
                    const searchTerm = this.strategyFilter.search.toLowerCase();
                    return strategy.name.toLowerCase().includes(searchTerm);
                }
                return true;
            });
        }
    },
    
    methods: {
        // 页面导航
        changePage(page) {
            this.currentPage = page;
            this.loadPageData(page);
        },
        
        toggleSidebar() {
            this.sidebarCollapsed = !this.sidebarCollapsed;
        },
        
        // 数据加载
        async loadPageData(page) {
            switch (page) {
                case 'dashboard':
                    await this.loadDashboardData();
                    break;
                case 'strategies':
                    await this.loadStrategies();
                    break;
                case 'positions':
                    await this.loadPositions();
                    break;
                case 'risk':
                    await this.loadRiskData();
                    break;
                case 'settings':
                    await this.loadSettings();
                    break;
            }
        },
        
        async loadDashboardData() {
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();
                this.accountStats = data.accountStats;
                this.updateCharts(data);
            } catch (error) {
                console.error('加载仪表盘数据失败:', error);
                this.showError('加载仪表盘数据失败');
            }
        },
        
        async loadStrategies() {
            try {
                const response = await fetch('/api/strategies');
                const data = await response.json();
                this.strategies = data.strategies;
            } catch (error) {
                console.error('加载策略数据失败:', error);
                this.showError('加载策略数据失败');
            }
        },
        
        async loadPositions() {
            try {
                const response = await fetch('/api/positions');
                const data = await response.json();
                this.positions = data.positions;
                this.positionStats = data.stats;
            } catch (error) {
                console.error('加载持仓数据失败:', error);
                this.showError('加载持仓数据失败');
            }
        },
        
        async loadRiskData() {
            try {
                const response = await fetch('/api/risk/metrics');
                const data = await response.json();
                this.riskMetrics = data.metrics;
                this.riskAlerts = data.alerts;
            } catch (error) {
                console.error('加载风控数据失败:', error);
                this.showError('加载风控数据失败');
            }
        },
        
        async loadSettings() {
            try {
                const response = await fetch('/api/settings');
                const data = await response.json();
                this.exchanges = data.exchanges;
                this.notificationSettings = data.notification;
                this.systemSettings = data.system;
            } catch (error) {
                console.error('加载设置失败:', error);
                this.showError('加载设置失败');
            }
        },
        
        // 策略操作
        async toggleStrategy(strategy) {
            try {
                const action = strategy.status === 'active' ? 'pause' : 'start';
                await fetch(`/api/strategies/${strategy.id}/${action}`, {
                    method: 'POST'
                });
                await this.loadStrategies();
            } catch (error) {
                console.error('策略操作失败:', error);
                this.showError('策略操作失败');
            }
        },
        
        showNewStrategyModal() {
            this.modalTitle = '新增策略';
            this.modalConfirmText = '创建';
            this.showModal = true;
            this.modalCallback = this.createStrategy;
        },
        
        async createStrategy(strategyData) {
            try {
                await fetch('/api/strategies', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(strategyData)
                });
                await this.loadStrategies();
                this.closeModal();
            } catch (error) {
                console.error('创建策略失败:', error);
                this.showError('创建策略失败');
            }
        },
        
        // 持仓操作
        async closePosition(position) {
            try {
                await fetch(`/api/positions/${position.id}/close`, {
                    method: 'POST'
                });
                await this.loadPositions();
            } catch (error) {
                console.error('平仓失败:', error);
                this.showError('平仓失败');
            }
        },
        
        // 风控操作
        async handleAlert(alert) {
            try {
                await fetch(`/api/risk/alerts/${alert.id}/handle`, {
                    method: 'POST'
                });
                await this.loadRiskData();
            } catch (error) {
                console.error('处理警报失败:', error);
                this.showError('处理警报失败');
            }
        },
        
        async saveRiskSettings() {
            try {
                await fetch('/api/risk/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(this.riskSettings)
                });
                this.showSuccess('风控设置保存成功');
            } catch (error) {
                console.error('保存风控设置失败:', error);
                this.showError('保存风控设置失败');
            }
        },
        
        // 系统设置操作
        async testExchangeConnection(exchange) {
            try {
                const response = await fetch(`/api/exchanges/${exchange.id}/test`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        apiKey: exchange.apiKey,
                        secretKey: exchange.secretKey
                    })
                });
                const data = await response.json();
                exchange.status = data.status;
                this.showSuccess(`${exchange.name} 连接测试${data.status === 'CONNECTED' ? '成功' : '失败'}`);
            } catch (error) {
                console.error('测试连接失败:', error);
                this.showError('测试连接失败');
            }
        },
        
        async saveSettings() {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        exchanges: this.exchanges,
                        notification: this.notificationSettings,
                        system: this.systemSettings
                    })
                });
                this.showSuccess('设置保存成功');
            } catch (error) {
                console.error('保存设置失败:', error);
                this.showError('保存设置失败');
            }
        },
        
        // 工具方法
        formatMoney(value) {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD'
            }).format(value);
        },
        
        formatPercent(value) {
            return new Intl.NumberFormat('en-US', {
                style: 'percent',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        },
        
        formatNumber(value) {
            return new Intl.NumberFormat('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        },
        
        formatTime(timestamp) {
            return new Date(timestamp).toLocaleString();
        },
        
        formatDuration(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        },
        
        getRiskClass(value) {
            if (value < 0.5) return 'low-risk';
            if (value < 0.8) return 'medium-risk';
            return 'high-risk';
        },
        
        showError(message) {
            // TODO: 实现错误提示
            console.error(message);
        },
        
        showSuccess(message) {
            // TODO: 实现成功提示
            console.log(message);
        },
        
        closeModal() {
            this.showModal = false;
            this.modalCallback = null;
        }
    },
    
    mounted() {
        // 初始加载仪表盘数据
        this.loadPageData('dashboard');
        
        // 启动定时更新
        setInterval(() => {
            this.loadPageData(this.currentPage);
        }, 30000); // 每30秒更新一次
    }
});