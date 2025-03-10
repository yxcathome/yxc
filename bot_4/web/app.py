from fastapi import FastAPI

app = FastAPI(
    title="自动化交易机器人 Web 服务",
    description="用于监控、管理交易机器人运行状态的 RESTful API",
    version="1.0.0"
)

@app.get("/")
async def read_root():
    return {"message": "欢迎使用自动化交易机器人服务"}

# 可在此继续添加更多API路由