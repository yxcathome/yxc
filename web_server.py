from aiohttp import web
from bot_core import ArbitrageBot
import logging

logger = logging.getLogger(__name__)

async def run_web_server(bot: ArbitrageBot, port: int):
    routes = web.RouteTableDef()

    @routes.get('/')
    async def index(request):
        html = """
        <html><head><title>套利监控</title><style>
            body {font-family: Arial; padding: 20px}
            table {border-collapse: collapse; width: 100%}
            th, td {border: 1px solid #ddd; padding: 8px; text-align: right}
            th {background-color: #f2f2f2}
        </style></head>
        <body>
            <h1>套利监控面板</h1>
            <p>接口列表：</p>
            <ul>
                <li>/api/status - 系统状态</li>
                <li>/api/logs - 最新日志</li>
                <li>/api/optimals - 套利机会</li>
                <li>/api/control - 控制指令</li>
            </ul>
        </body></html>
        """
        return web.Response(text=html, content_type='text/html')

    @routes.get('/api/status')
    async def get_status(request):
        await bot.update_balances()
        total = bot.balances['okx'] + bot.balances['binance']
        profit_rate = (bot.profits['total'] / total * 100) if total > 0 else 0
        
        return web.json_response({
            'status': {
                'running': bot.is_running,
                'paused': bot.is_paused,
                'uptime': str(datetime.now() - bot.stats['start_time']),
                'total_trades': bot.stats['successful_trades']
            },
            'balances': {
                'okx': float(bot.balances['okx']),
                'binance': float(bot.balances['binance'])
            },
            'profits': {
                'total': float(bot.profits['total']),
                'today': float(bot.profits['today']),
                'rate': float(profit_rate)
            },
            'trading': {
                'current_amount': float(bot.trade_usdt),
                'max_amount': float(bot.trade_config['max_trade_usdt'])
            },
            'opportunities': bot.optimal_opportunities[:10]
        })

    @routes.get('/api/logs')
    async def get_logs(request):
        return web.json_response({'logs': mem_handler.buffer[-100:]})

    @routes.get('/api/optimals')
    async def get_optimals(request):
        return web.json_response({'opportunities': bot.optimal_opportunities[:30]})

    @routes.post('/api/control')
    async def control(request):
        data = await request.json()
        command = data.get('command')
        if command == 'pause':
            bot.is_paused = True
            return web.json_response({'status': 'paused'})
        elif command == 'resume':
            bot.is_paused = False
            return web.json_response({'status': 'resumed'})
        elif command == 'shutdown':
            asyncio.create_task(bot.shutdown())
            return web.json_response({'status': 'shutting down'})
        else:
            return web.json_response({'error': 'invalid command'})

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web服务已启动: http://0.0.0.0:{port}")