#!/bin/bash
# 客户洞察智能体 - 一键部署脚本
set -e

PROJECT_DIR=$(pwd)
USER_NAME=$(whoami)

echo ">>> 开始部署 Customer Insight Agent..."

# 1. 安装系统依赖
echo ">>> 正在检测操作系统并安装基础环境..."
if command -v apt &> /dev/null; then
    # Debian/Ubuntu
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    sudo yum install -y python3 python3-pip
else
    echo "未识别的包管理器，请确保系统已安装 python3 和 pip。"
fi

# 2. 创建虚拟环境
echo ">>> 正在准备 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 3. 安装依赖
echo ">>> 正在安装项目依赖..."
pip install -r requirements.txt

# 4. 生成守护进程配置
echo ">>> 正在配置后台守护进程 (Systemd)..."
cat <<EOF > customer_insight.service
[Unit]
Description=Customer Insight Agent FastAPI Server
After=network.target

[Service]
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 5. 启动服务
echo ">>> 正在启动应用..."
sudo cp customer_insight.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable customer_insight.service
sudo systemctl restart customer_insight.service

echo "======================================"
echo "✅ 部署完美成功！"
echo "🚀 您的服务已经在后台 7x24 小时运行，监听端口: 8000"
echo "👀 您可以使用以下命令实时查看运行日志："
echo "   sudo journalctl -u customer_insight -f"
echo ""
echo "⚠️ 注意：请务必前往云服务器控制台的【防火墙/安全组】放行 8000 端口。"
echo "======================================"
